from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from .chemistry import normalize


@dataclass(frozen=True, slots=True)
class ChemicalName:
    preferred_name: str
    systematic_name: str | None
    source: str
    source_id: str
    match_type: str
    retrieved_at: str


class PubChemNameProvider:
    """Exact-InChIKey PubChem names with a persistent local cache."""

    def __init__(self, cache_path: Path) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(cache_path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS chemical_name (inchikey TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self.lock = threading.Lock()

    def lookup(self, structure: str) -> ChemicalName | None:
        molecule = normalize(structure)
        # RDKit can return no InChIKey for structures outside InChI's supported
        # domain. Naming is optional metadata, so these must not fail a search.
        if not molecule.inchikey:
            return None
        with self.lock:
            row = self.db.execute(
                "SELECT payload FROM chemical_name WHERE inchikey=?", (molecule.inchikey,)
            ).fetchone()
        if row:
            return ChemicalName(**json.loads(row[0])) if row[0] != "null" else None
        if os.getenv("OPENCOOK_NAME_PROVIDER", "pubchem").lower() != "pubchem":
            return None
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/"
            f"{quote(str(molecule.inchikey))}/property/Title,IUPACName/JSON"
        )
        try:
            response = httpx.get(url, timeout=4.0, headers={"User-Agent": "OpenCook/0.1"})
            response.raise_for_status()
            item = response.json()["PropertyTable"]["Properties"][0]
            name = ChemicalName(
                preferred_name=item.get("Title") or item.get("IUPACName") or molecule.smiles,
                systematic_name=item.get("IUPACName"),
                source="PubChem",
                source_id=f"CID:{item['CID']}",
                match_type="exact_standard_inchikey",
                retrieved_at=response.headers.get("date", "unknown"),
            )
            payload = json.dumps(asdict(name))
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO chemical_name VALUES(?,?)", (molecule.inchikey, payload))
            self.db.commit()
        return name
