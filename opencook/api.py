from __future__ import annotations

import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from . import __version__
from .availability import AvailabilityGateway
from .chemistry import MoleculeError, depict_svg, normalize
from .names import PubChemNameProvider
from .runtime import ROOT, demo_runtime, model_runtime
from .search import BestFirstPlanner, BreadthFirstPlanner, SearchConfig
from .stock import OverlayStock, StockProvider

app = FastAPI(
    title="OpenCook API", version=__version__, description="Deterministic reaction-data retrosynthesis API"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
store, stock = demo_runtime()
model_provider = model_runtime()
name_provider = PubChemNameProvider(ROOT / "data" / "cache" / "chemical-names.sqlite")
availability_gateway = AvailabilityGateway(os.getenv("OPENCOOK_AVAILABILITY_URL", "http://127.0.0.1:8787"))
jobs: dict[str, dict[str, Any]] = {}
logger = logging.getLogger(__name__)


class MoleculeInput(BaseModel):
    structure: str = Field(min_length=1)
    format: str = "auto"


class SearchInput(MoleculeInput):
    planner: str = "andor_best_first"
    max_depth: int = Field(8, ge=1, le=30)
    max_expansions: int = Field(10_000, ge=1, le=1_000_000)
    # A local CPU model expansion takes roughly 30-40 seconds. This allows ORD
    # search plus several fallback calls while remaining cancelable.
    timeout_seconds: float = Field(180, gt=0, le=3600)
    routes: int = Field(5, ge=1, le=50)
    heuristic: str = "complexity"
    objective: str = "deepest_supported"
    model_fallback: bool = True
    model_candidate_limit: int = Field(5, ge=1, le=10)
    max_model_calls: int = Field(25, ge=0, le=250)
    model_min_heavy_atoms: int = Field(6, ge=1, le=100)
    availability_enabled: bool = False
    availability_country: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    availability_buyer_class: str = Field(
        "ordinary_individual",
        pattern="^(ordinary_individual|professional|organization)$",
    )
    availability_candidate_limit: int = Field(8, ge=1, le=30)

    @model_validator(mode="after")
    def require_availability_market(self) -> SearchInput:
        if self.availability_enabled and self.availability_country is None:
            raise ValueError("availability_country is required when availability checking is enabled")
        return self


@app.exception_handler(MoleculeError)
async def molecule_error(_request: Any, exc: MoleculeError) -> Any:
    return Response(content='{"detail":"' + str(exc) + '"}', status_code=422, media_type="application/json")


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    counts = store.counts()
    return {
        "status": "ok",
        "version": __version__,
        "database": counts,
        "corpus_mode": "fixture_only" if counts["reaction"] <= 4 else "imported",
        "stock_version": stock.version,
        "stock_molecules": stock.count(),
        "network_required": False,
        "model_provider": model_provider.name,
        "model_version": model_provider.version,
    }


@app.get("/api/v1/availability/health")
def availability_health() -> dict[str, Any]:
    try:
        result = availability_gateway.health()
        return {"status": "connected", "service": result}
    except Exception as exc:
        return {"status": "unavailable", "detail": f"{type(exc).__name__}: {exc}"}


@app.post("/api/v1/molecules/normalize")
def normalize_molecule(body: MoleculeInput) -> dict[str, Any]:
    return asdict(normalize(body.structure, body.format))


@app.post("/api/v1/molecules/depict")
def depict(body: MoleculeInput) -> Response:
    mol = normalize(body.structure, body.format)
    return Response(depict_svg(mol.smiles), media_type="image/svg+xml")


@app.get("/api/v1/molecules/depict-image")
def depict_image(smiles: str) -> Response:
    """Image endpoint for browser graph nodes; same deterministic depiction engine."""
    return Response(depict_svg(normalize(smiles).smiles), media_type="image/svg+xml")


@app.get("/api/v1/molecules/names")
def molecule_names(structure: str) -> dict[str, Any]:
    name = name_provider.lookup(structure)
    return asdict(name) if name else {"preferred_name": None, "source": None}


def _enrich_names(routes: list[dict[str, Any]]) -> None:
    nodes: list[dict[str, Any]] = []

    def collect(node: dict[str, Any]) -> None:
        nodes.append(node)
        for precursor in node["precursors"]:
            collect(precursor)

    for route in routes:
        collect(route["root"])
    # Preserve route order so targets and the highest-ranked precursors receive
    # names first. Remote naming is auxiliary and must not add minutes after a
    # completed chemistry search.
    structures = list(dict.fromkeys(node["molecule"] for node in nodes))[:24]

    def safe_lookup(structure: str) -> Any:
        try:
            return name_provider.lookup(structure)
        except Exception:
            logger.exception("Chemical-name lookup failed", extra={"structure": structure})
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        names = dict(zip(structures, pool.map(safe_lookup, structures), strict=True))
    for node in nodes:
        name = names.get(node["molecule"])
        if name:
            node["display_name"] = name.preferred_name
            node["name_record"] = asdict(name)


def _unresolved_leaves(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    leaves: dict[str, dict[str, Any]] = {}

    def visit(node: dict[str, Any]) -> None:
        if not node["in_stock"] and not node["reaction"]:
            leaves.setdefault(str(node["molecule"]), node)
        for precursor in node["precursors"]:
            visit(precursor)

    for route in routes:
        visit(route["root"])
    return list(leaves.values())


def _attach_availability(routes: list[dict[str, Any]], verdicts: dict[str, dict[str, Any]]) -> None:
    def visit(node: dict[str, Any]) -> None:
        if verdict := verdicts.get(str(node["molecule"])):
            node["availability"] = verdict
        for precursor in node["precursors"]:
            visit(precursor)

    for route in routes:
        visit(route["root"])


def _check_availability(
    job_id: str,
    body: SearchInput,
    serialized_routes: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], StockProvider]:
    if not body.availability_enabled or not body.availability_country:
        return {}, stock
    leaves = _unresolved_leaves(serialized_routes)[: body.availability_candidate_limit]
    verdicts: dict[str, dict[str, Any]] = {}
    additions: dict[str, tuple[str | None, tuple[str, ...]]] = {}
    observation_ids: list[str] = []
    jobs[job_id]["availability"] = {
        "enabled": True,
        "status": "running",
        "checked": 0,
        "total": len(leaves),
        "verified": 0,
        "candidate_listings": 0,
        "country": body.availability_country,
        "buyer_class": body.availability_buyer_class,
    }
    try:
        availability_gateway.health()
    except Exception as exc:
        jobs[job_id]["availability"].update(
            status="unavailable",
            error=f"{type(exc).__name__}: {exc}",
        )
        return {}, stock
    for index, leaf in enumerate(leaves, start=1):
        if jobs[job_id].get("cancel_requested"):
            break
        molecule = str(leaf["molecule"])
        jobs[job_id]["progress"] = {
            **jobs[job_id]["progress"],
            "stage": "checking real-world availability evidence",
            "availability_current": molecule,
            "availability_checked": index - 1,
            "availability_total": len(leaves),
        }
        try:
            verdict = availability_gateway.evaluate(
                molecule,
                name=leaf.get("display_name"),
                country=body.availability_country,
                buyer_class=body.availability_buyer_class,
            )
        except Exception as exc:
            verdict = {
                "state": "unknown",
                "terminal": False,
                "confidence": 0,
                "reasons": [f"AvailEvidence unavailable: {type(exc).__name__}: {exc}"],
                "observations": [],
                "provider_errors": {"service": str(exc)},
            }
        verdicts[molecule] = verdict
        observations = verdict.get("observations", [])
        observation_ids.extend(str(item["id"]) for item in observations if item.get("id"))
        if verdict.get("terminal") is True:
            additions[molecule] = (
                leaf.get("display_name"),
                ("AvailEvidence verified public offer",),
            )
        candidate_count = sum(
            1 for item in observations if item.get("state") in {"listed_in_stock", "professional_catalog"}
        )
        jobs[job_id]["availability"].update(
            checked=index,
            verified=len(additions),
            candidate_listings=jobs[job_id]["availability"]["candidate_listings"] + candidate_count,
        )
    snapshot_digest = uuid.uuid5(uuid.NAMESPACE_URL, "|".join(sorted(observation_ids))).hex[:12]
    version = (
        f"{stock.version}+availability:{body.availability_country}:"
        f"{body.availability_buyer_class}:{snapshot_digest}"
    )
    jobs[job_id]["availability"].update(
        status="completed",
        snapshot_version=version,
        verdicts=verdicts,
    )
    return verdicts, OverlayStock(stock, additions, version) if additions else stock


def _run(job_id: str, body: SearchInput) -> None:
    try:
        jobs[job_id]["status"] = "running"
        planner_cls = BreadthFirstPlanner if body.planner == "breadth_first_baseline" else BestFirstPlanner
        config = SearchConfig(
            max_depth=body.max_depth,
            max_expansions=body.max_expansions,
            timeout_seconds=body.timeout_seconds,
            routes=body.routes,
            heuristic=body.heuristic,
            objective=body.objective,
            model_fallback=body.model_fallback,
            model_candidate_limit=body.model_candidate_limit,
            max_model_calls=body.max_model_calls,
            model_min_heavy_atoms=body.model_min_heavy_atoms,
        )

        def progress(update: dict[str, object]) -> None:
            jobs[job_id]["progress"] = {**jobs[job_id]["progress"], **update}

        routes, stats = planner_cls(store, stock, model_provider).search(
            body.structure,
            config,
            progress=progress,
            should_cancel=lambda: bool(jobs[job_id].get("cancel_requested")),
        )
        if jobs[job_id].get("cancel_requested"):
            jobs[job_id]["status"] = "canceled"
            return
        serialized_routes = [route.to_dict() for route in routes]
        jobs[job_id]["progress"] = {
            **jobs[job_id]["progress"],
            "stage": "resolving molecule names",
        }
        try:
            _enrich_names(serialized_routes)
        except Exception:
            # Names are presentation metadata, never part of route validity.
            logger.exception("Name enrichment failed for search job %s", job_id)
        verdicts, verified_stock = _check_availability(job_id, body, serialized_routes)
        if jobs[job_id].get("cancel_requested"):
            jobs[job_id]["status"] = "canceled"
            return
        if verified_stock is not stock:
            jobs[job_id]["progress"] = {
                **jobs[job_id]["progress"],
                "stage": "verified leaves found; resuming retrosynthesis",
                "availability_checked": jobs[job_id]["availability"]["checked"],
                "availability_total": jobs[job_id]["availability"]["total"],
            }
            routes, stats = planner_cls(store, verified_stock, model_provider).search(
                body.structure,
                config,
                progress=progress,
                should_cancel=lambda: bool(jobs[job_id].get("cancel_requested")),
            )
            serialized_routes = [route.to_dict() for route in routes]
            try:
                _enrich_names(serialized_routes)
            except Exception:
                logger.exception("Name enrichment failed after availability resume for %s", job_id)
        _attach_availability(serialized_routes, verdicts)
        jobs[job_id].update(
            status="completed",
            routes=serialized_routes,
            stats=asdict(stats),
            progress={
                **jobs[job_id]["progress"],
                "stage": f"search {stats.termination}",
            },
            message=None
            if stats.complete_routes
            else (
                "No complete route found under the current search configuration and available "
                f"reaction corpus ({store.counts()['reaction']} indexed reactions). Supported "
                "partial routes are shown with unresolved precursors."
            ),
        )
        jobs[job_id]["reproducibility"]["stock_version"] = verified_stock.version
    except Exception as exc:
        logger.exception("Search job %s failed", job_id)
        jobs[job_id].update(status="failed", error=str(exc))


@app.post("/api/v1/searches", status_code=202)
def create_search(body: SearchInput) -> dict[str, str]:
    job_id = str(uuid.uuid4())
    target = asdict(normalize(body.structure, body.format))
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "target": target,
        "configuration": body.model_dump(),
        "progress": {
            "stage": "queued",
            "current_molecule": target["smiles"],
            "current_depth": 0,
            "elapsed_seconds": 0,
            "molecules_discovered": 1,
            "molecules_expanded": 0,
            "unique_reactions_examined": 0,
            "frontier_size": 1,
            "complete_routes_discovered": 0,
            "deepest_complete_route": 0,
            "model_calls": 0,
            "model_reactions_generated": 0,
            "model_failures": 0,
            "recent_reactions": [],
            "availability_checked": 0,
            "availability_total": 0,
            "availability_current": None,
        },
        "availability": {
            "enabled": body.availability_enabled,
            "status": "pending" if body.availability_enabled else "disabled",
            "checked": 0,
            "total": 0,
            "verified": 0,
            "candidate_listings": 0,
            "country": body.availability_country,
            "buyer_class": body.availability_buyer_class,
        },
        "reproducibility": {
            "opencook_version": __version__,
            "dataset_versions": ["fixture-1"],
            "stock_version": stock.version,
        },
    }
    threading.Thread(target=_run, args=(job_id, body), daemon=True).start()
    return {"id": job_id, "status": "queued"}


@app.get("/api/v1/searches/{job_id}")
def search_status(job_id: str) -> dict[str, Any]:
    if job_id not in jobs:
        raise HTTPException(404, "Search not found")
    return jobs[job_id]


@app.delete("/api/v1/searches/{job_id}", status_code=202)
def cancel_search(job_id: str) -> dict[str, str]:
    if job_id not in jobs:
        raise HTTPException(404, "Search not found")
    jobs[job_id]["cancel_requested"] = True
    return {"id": job_id, "status": "cancel_requested"}


@app.get("/api/v1/reactions/{reaction_id}")
def reaction_evidence(reaction_id: str) -> dict[str, Any]:
    reaction = store.reaction(reaction_id)
    if not reaction:
        raise HTTPException(404, "Reaction not found")
    return asdict(reaction)
