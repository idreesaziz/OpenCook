from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx

from .chemistry import normalize
from .stock import SQLiteStock


@dataclass(frozen=True, slots=True)
class AvailabilityImportResult:
    terminal: bool
    state: str
    reasons: tuple[str, ...]
    observations: int
    imported: bool
    snapshot_version: str | None


class AvailabilityGateway:
    """Versioned HTTP boundary to the independent AvailEvidence service."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8787",
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def evaluate(
        self,
        smiles: str,
        *,
        country: str,
        supplied_urls: list[str] | None = None,
        buyer_class: str = "ordinary_individual",
    ) -> dict[str, Any]:
        molecule = normalize(smiles)
        payload = {
            "identity": {
                "domain": "chemical",
                "name": None,
                "identifiers": {"inchikey": molecule.inchikey},
                "attributes": {"canonical_smiles": molecule.smiles},
            },
            "buyer": {"buyer_class": buyer_class},
            "market": {"country": country.upper()},
            "supplied_urls": supplied_urls or [],
        }
        with httpx.Client(transport=self.transport, timeout=30) as client:
            response = client.post(f"{self.base_url}/v1/availability/check", json=payload)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

    def verify_into_snapshot(
        self,
        stock: SQLiteStock,
        smiles: str,
        *,
        country: str,
        supplied_urls: list[str] | None = None,
        buyer_class: str = "ordinary_individual",
    ) -> AvailabilityImportResult:
        result = self.evaluate(
            smiles,
            country=country,
            supplied_urls=supplied_urls,
            buyer_class=buyer_class,
        )
        observations = result.get("observations", [])
        terminal = result.get("terminal") is True
        if not terminal:
            return AvailabilityImportResult(
                terminal=False,
                state=str(result.get("state", "unknown")),
                reasons=tuple(str(reason) for reason in result.get("reasons", [])),
                observations=len(observations),
                imported=False,
                snapshot_version=None,
            )
        observation_ids = sorted(str(item["id"]) for item in observations if item.get("id"))
        digest = hashlib.sha256("\n".join(observation_ids).encode()).hexdigest()[:12]
        version = f"availevidence-0.1:{country.upper()}:{buyer_class}:{digest}"
        urls = [str(item["offer_url"]) for item in observations if item.get("offer_url")]
        added = stock.add(
            smiles,
            source="AvailEvidence verified public offer",
            catalog_id=digest,
            profile=f"verified:{buyer_class}:{country.upper()}",
            url=urls[0] if urls else None,
            updated_at=str(result.get("evaluated_at", "")),
        )
        stock.set_metadata("version", version)
        return AvailabilityImportResult(
            terminal=True,
            state=str(result["state"]),
            reasons=tuple(str(reason) for reason in result.get("reasons", [])),
            observations=len(observations),
            imported=added,
            snapshot_version=version,
        )
