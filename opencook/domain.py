from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class EvidenceClass(StrEnum):
    EXACT = "exact_experimental_precedent"
    ANALOGUE = "analogue_supported_transformation"
    TEMPLATE = "reaction_template_application"
    COMPUTATIONAL = "computational_proposal"


@dataclass(frozen=True, slots=True)
class Molecule:
    id: str
    smiles: str
    inchi: str
    inchikey: str
    formula: str
    molecular_weight: float
    formal_charge: int
    heavy_atoms: int
    rings: int
    stereocenters: int


@dataclass(frozen=True, slots=True)
class Provenance:
    dataset: str
    dataset_version: str
    record_id: str
    source: str
    license: str
    doi: str | None = None
    patent: str | None = None


@dataclass(frozen=True, slots=True)
class Reaction:
    id: str
    reactants: tuple[str, ...]
    product: str
    evidence: EvidenceClass
    confidence: float
    validation: str
    provenance: tuple[Provenance, ...]
    template_id: str | None = None
    conditions_summary: str | None = None
    yield_percent: float | None = None


@dataclass(slots=True)
class RouteNode:
    molecule: str
    in_stock: bool
    display_name: str | None = None
    common_sources: tuple[str, ...] = ()
    reaction: Reaction | None = None
    precursors: list[RouteNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "molecule": self.molecule,
            "in_stock": self.in_stock,
            "display_name": self.display_name,
            "common_sources": list(self.common_sources),
            "reaction": asdict(self.reaction) if self.reaction else None,
            "precursors": [p.to_dict() for p in self.precursors],
        }


@dataclass(frozen=True, slots=True)
class RouteMetrics:
    transformations: int
    longest_linear_sequence: int
    stock_leaves: int
    average_confidence: float
    evidence_score: float
    total_score: float
    unresolved_leaves: int = 0


@dataclass(slots=True)
class Route:
    root: RouteNode
    metrics: RouteMetrics
    signature: str
    complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root.to_dict(),
            "metrics": asdict(self.metrics),
            "signature": self.signature,
            "complete": self.complete,
        }
