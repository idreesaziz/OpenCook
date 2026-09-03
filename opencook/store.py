from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .chemistry import canonical_identity
from .domain import EvidenceClass, Provenance, Reaction

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS molecule(id TEXT PRIMARY KEY, smiles TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reaction(id TEXT PRIMARY KEY, product_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS reaction_product_idx ON reaction(product_id);
CREATE TABLE IF NOT EXISTS precursor(reaction_id TEXT NOT NULL, molecule_id TEXT NOT NULL,
  PRIMARY KEY(reaction_id,molecule_id));
CREATE INDEX IF NOT EXISTS precursor_molecule_idx ON precursor(molecule_id);
"""


class ReactionStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA temp_store=MEMORY")
        self.db.executescript(SCHEMA)

    def put_reaction(self, reaction: Reaction, *, commit: bool = True) -> None:
        product_id, product_smiles = canonical_identity(reaction.product)
        reactants = tuple(canonical_identity(s) for s in reaction.reactants)
        for molecule_id, smiles in ((product_id, product_smiles), *reactants):
            self.db.execute(
                "INSERT OR IGNORE INTO molecule VALUES(?,?,?)",
                (molecule_id, smiles, json.dumps({"id": molecule_id, "smiles": smiles})),
            )
        canonical = Reaction(
            reaction.id,
            tuple(smiles for _, smiles in reactants),
            product_smiles,
            reaction.evidence,
            reaction.confidence,
            reaction.validation,
            reaction.provenance,
            reaction.template_id,
            reaction.conditions_summary,
            reaction.yield_percent,
        )
        self.db.execute(
            "INSERT OR REPLACE INTO reaction VALUES(?,?,?)",
            (canonical.id, product_id, json.dumps(asdict(canonical))),
        )
        self.db.execute("DELETE FROM precursor WHERE reaction_id=?", (canonical.id,))
        self.db.executemany(
            "INSERT INTO precursor VALUES(?,?)",
            [(canonical.id, molecule_id) for molecule_id, _ in reactants],
        )
        if commit:
            self.db.commit()

    def commit(self) -> None:
        self.db.commit()

    def reactions_producing(self, smiles: str) -> list[Reaction]:
        mid, _ = canonical_identity(smiles)
        rows = self.db.execute(
            "SELECT payload FROM reaction WHERE product_id=? ORDER BY id", (mid,)
        ).fetchall()
        return [self._decode(r[0]) for r in rows]

    def reaction(self, reaction_id: str) -> Reaction | None:
        row = self.db.execute("SELECT payload FROM reaction WHERE id=?", (reaction_id,)).fetchone()
        return self._decode(row[0]) if row else None

    def counts(self) -> dict[str, int]:
        return {
            t: self.db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("molecule", "reaction")
        }

    @staticmethod
    def _decode(payload: str) -> Reaction:
        d = json.loads(payload)
        d["reactants"] = tuple(d["reactants"])
        d["evidence"] = EvidenceClass(d["evidence"])
        d["provenance"] = tuple(Provenance(**p) for p in d["provenance"])
        return Reaction(**d)


def load_fixture(store: ReactionStore, path: Path) -> dict[str, int]:
    records = json.loads(path.read_text(encoding="utf-8"))
    read = rejected = 0
    for item in records:
        read += 1
        try:
            prov = tuple(Provenance(**p) for p in item.pop("provenance"))
            store.put_reaction(
                Reaction(provenance=prov, evidence=EvidenceClass(item.pop("evidence")), **item)
            )
        except Exception:
            rejected += 1
    return {"records_read": read, "records_indexed": read - rejected, "records_rejected": rejected}
