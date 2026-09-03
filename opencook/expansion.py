from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from .chemistry import MoleculeError, normalize
from .domain import EvidenceClass, Provenance, Reaction


class ExpansionProvider(Protocol):
    """Optional source of computational disconnections for an unresolved molecule."""

    name: str
    version: str

    def expand(self, product: str, limit: int) -> list[Reaction]: ...


class NoExpansionProvider:
    name = "disabled"
    version = "none"

    def expand(self, product: str, limit: int) -> list[Reaction]:
        return []


class RetroChimeraProvider:
    """Lazy local RetroChimera adapter through its native Syntheseus interface.

    Model output is deliberately classified as computational evidence. Structural
    parsing is validation, not proof of reaction feasibility.
    """

    name = "retrochimera"
    version = "1.2-denovo"

    def __init__(self, model_dir: Path | None = None, worker_python: Path | None = None) -> None:
        self.model_dir = model_dir
        self.worker_python = worker_python
        self._model: object | None = None
        self._worker: subprocess.Popen[str] | None = None
        self._lock = Lock()

    def _worker_expand(self, product: str, limit: int) -> Sequence[object]:
        if self._worker is None or self._worker.poll() is not None:
            command = [str(self.worker_python), "-m", "opencook.model_worker"]
            if self.model_dir:
                command.extend(["--model-dir", str(self.model_dir)])
            self._worker = subprocess.Popen(
                command,
                cwd=Path(__file__).resolve().parent.parent,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None,
                text=True,
                bufsize=1,
            )
        assert self._worker.stdin is not None and self._worker.stdout is not None
        self._worker.stdin.write(json.dumps({"product": product, "limit": limit}) + "\n")
        self._worker.stdin.flush()
        for line in self._worker.stdout:
            if line.startswith("OPENCOOK_RESULT "):
                payload = json.loads(line.removeprefix("OPENCOOK_RESULT "))
                if "error" in payload:
                    raise RuntimeError(f"RetroChimera worker failed: {payload['error']}")
                return cast(Sequence[object], payload["predictions"])
        raise RuntimeError("RetroChimera worker exited without returning a result")

    def _load(self) -> object:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                try:
                    from retrochimera import RetroChimeraDeNovoModel  # type: ignore[import-not-found]
                except ImportError as exc:
                    raise RuntimeError(
                        "RetroChimera is not installed; run `uv sync --extra models`"
                    ) from exc
                kwargs = {"model_dir": str(self.model_dir)} if self.model_dir else {}
                self._model = RetroChimeraDeNovoModel(**kwargs)
        return self._model

    def expand(self, product: str, limit: int) -> list[Reaction]:
        canonical_product = normalize(product).smiles
        with self._lock:
            if self.worker_python:
                predictions = self._worker_expand(canonical_product, limit)
            else:
                from syntheseus import Molecule as SyntheseusMolecule  # type: ignore[import-not-found]

                model = self._load()
                batches = model(  # type: ignore[operator]
                    [SyntheseusMolecule(canonical_product)], num_results=limit
                )
                predictions = batches[0]
        reactions: list[Reaction] = []
        seen: set[tuple[str, ...]] = set()
        for rank, prediction in enumerate(predictions, 1):
            try:
                reactants = tuple(
                    sorted(
                        {
                            normalize(mol["smiles"] if isinstance(mol, dict) else mol.smiles).smiles
                            for mol in (
                                prediction["reactants"]
                                if isinstance(prediction, dict)
                                else prediction.reactants  # type: ignore[attr-defined]
                            )
                        }
                    )
                )
                if not reactants or reactants == (canonical_product,) or reactants in seen:
                    continue
                seen.add(reactants)
                metadata = dict(
                    prediction.get("metadata", {})
                    if isinstance(prediction, dict)
                    else getattr(prediction, "metadata", {})
                )
                raw_probability = metadata.get("probability", metadata.get("score", 0.0))
                probability = float(raw_probability) if raw_probability is not None else 0.0
                probability = min(1.0, max(0.0, probability))
                digest = hashlib.sha256(
                    f"{canonical_product}>{'.'.join(reactants)}".encode()
                ).hexdigest()[:20]
                reactions.append(
                    Reaction(
                        id=f"model:retrochimera:{digest}",
                        reactants=reactants,
                        product=canonical_product,
                        evidence=EvidenceClass.COMPUTATIONAL,
                        confidence=probability,
                        validation="structurally_valid_not_forward_verified",
                        provenance=(
                            Provenance(
                                dataset="RetroChimera model prediction",
                                dataset_version=self.version,
                                record_id=f"rank-{rank}",
                                source="https://github.com/microsoft/retrochimera",
                                license="See model checkpoint license",
                            ),
                        ),
                    )
                )
            except (MoleculeError, AttributeError, TypeError, ValueError):
                continue
        return reactions
