from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

from .domain import EvidenceClass, Provenance, Reaction
from .store import ReactionStore


def import_ord(
    path: Path,
    store: ReactionStore,
    *,
    commit_interval: int = 10_000,
    start_at: int = 0,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, object]:
    """Stream an official ORD protobuf/Parquet dataset into the exact index."""
    from ord_schema import datasets
    from ord_schema.proto import reaction_pb2
    from rdkit import RDLogger

    # Normalization warnings are expected in heterogeneous public corpora. They
    # are accounted for as rejected records below; emitting millions of RDKit
    # warning lines makes long imports effectively unusable.
    RDLogger.DisableLog("rdApp.warning")

    dataset = datasets.load_dataset(path)
    report: Counter[str] = Counter()
    rejections: Counter[str] = Counter()

    def smiles(identifiers: object) -> str | None:
        for identifier in identifiers:  # type: ignore[union-attr]
            if identifier.type == reaction_pb2.CompoundIdentifier.SMILES:
                return str(identifier.value)
        return None

    for position, record in enumerate(dataset.reactions):
        if position < start_at:
            continue
        report["records_read"] += 1
        absolute_read = start_at + report["records_read"]
        if progress and absolute_read % 10_000 == 0:
            progress(absolute_read, len(dataset.reactions))
        try:
            reactants: list[str] = []
            for reaction_input in record.inputs.values():
                for component in reaction_input.components:
                    if reaction_pb2.ReactionRole.ReactionRoleType.Name(component.reaction_role) == "REACTANT":
                        value = smiles(component.identifiers)
                        if value:
                            reactants.append(value)
            products: list[str] = []
            for outcome in record.outcomes:
                for product in outcome.products:
                    role = reaction_pb2.ReactionRole.ReactionRoleType.Name(product.reaction_role)
                    value = smiles(product.identifiers)
                    if value and (product.is_desired_product or role == "PRODUCT"):
                        products.append(value)
            if not reactants:
                rejections["no_structured_reactants"] += 1
                continue
            if not products:
                rejections["no_desired_product_smiles"] += 1
                continue
            report["records_accepted"] += 1
            provenance = Provenance(
                dataset=dataset.name or "Open Reaction Database",
                dataset_version=dataset.dataset_id,
                record_id=record.reaction_id,
                source=record.provenance.publication_url or "Open Reaction Database",
                license="CC-BY-SA-4.0",
                doi=record.provenance.doi or None,
            )
            for index, product in enumerate(dict.fromkeys(products)):
                store.put_reaction(
                    Reaction(
                        id=f"{record.reaction_id}:p{index}",
                        reactants=tuple(dict.fromkeys(reactants)),
                        product=product,
                        evidence=EvidenceClass.EXACT,
                        confidence=1.0,
                        validation="ord_structured_record",
                        provenance=(provenance,),
                    ),
                    commit=False,
                )
                report["records_indexed"] += 1
                if report["records_indexed"] % commit_interval == 0:
                    store.commit()
        except Exception as exc:
            rejections[type(exc).__name__] += 1
    store.commit()
    report["records_rejected"] = report["records_read"] - report["records_accepted"]
    return {
        **dict(report),
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.name,
        "rejection_reasons": dict(rejections),
        "database": store.counts(),
    }
