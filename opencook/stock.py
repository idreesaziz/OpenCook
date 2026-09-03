from __future__ import annotations

import csv
import gzip
import io
import json
import sqlite3
import tarfile
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Protocol, TextIO

from .chemistry import canonical_identity


class StockProvider(Protocol):
    @property
    def version(self) -> str: ...

    def contains(self, smiles: str) -> bool: ...
    def describe(self, smiles: str) -> tuple[str | None, tuple[str, ...]]: ...
    def count(self) -> int: ...


class SQLiteStock:
    """Disk-backed, stereochemistry-aware, provenance-preserving stock."""

    def __init__(self, path: str | Path, version: str | None = None) -> None:
        self.path = str(path)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS stock_molecule(
              molecule_id TEXT PRIMARY KEY, smiles TEXT UNIQUE NOT NULL, preferred_name TEXT
            );
            CREATE TABLE IF NOT EXISTS stock_assertion(
              molecule_id TEXT NOT NULL, source TEXT NOT NULL, catalog_id TEXT NOT NULL DEFAULT '',
              profile TEXT NOT NULL DEFAULT 'building_blocks', url TEXT, updated_at TEXT,
              PRIMARY KEY(molecule_id, source, catalog_id),
              FOREIGN KEY(molecule_id) REFERENCES stock_molecule(molecule_id)
            );
            CREATE INDEX IF NOT EXISTS stock_assertion_profile_idx
              ON stock_assertion(profile, molecule_id);
            """
        )
        if version is not None:
            self.set_metadata("version", version)

    @property
    def version(self) -> str:
        row = self.db.execute("SELECT value FROM metadata WHERE key='version'").fetchone()
        return str(row[0]) if row else "unversioned"

    def set_metadata(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES(?, ?)", (key, value))
        self.db.commit()

    def add(
        self,
        smiles: str,
        *,
        source: str,
        catalog_id: str = "",
        name: str | None = None,
        profile: str = "building_blocks",
        url: str | None = None,
        updated_at: str | None = None,
        commit: bool = True,
    ) -> bool:
        molecule_id, canonical = canonical_identity(smiles)
        self.db.execute(
            """INSERT INTO stock_molecule VALUES(?, ?, ?)
               ON CONFLICT(molecule_id) DO UPDATE SET
                 preferred_name=COALESCE(stock_molecule.preferred_name, excluded.preferred_name)""",
            (molecule_id, canonical, name),
        )
        before = self.db.total_changes
        self.db.execute(
            """INSERT OR IGNORE INTO stock_assertion
               (molecule_id, source, catalog_id, profile, url, updated_at)
               VALUES(?, ?, ?, ?, ?, ?)""",
            (molecule_id, source, catalog_id, profile, url, updated_at),
        )
        inserted = self.db.total_changes > before
        if commit:
            self.db.commit()
        return inserted

    def contains(self, smiles: str) -> bool:
        molecule_id, _ = canonical_identity(smiles)
        return self.db.execute(
            "SELECT 1 FROM stock_assertion WHERE molecule_id=? LIMIT 1", (molecule_id,)
        ).fetchone() is not None

    def describe(self, smiles: str) -> tuple[str | None, tuple[str, ...]]:
        molecule_id, _ = canonical_identity(smiles)
        row = self.db.execute(
            "SELECT preferred_name FROM stock_molecule WHERE molecule_id=?", (molecule_id,)
        ).fetchone()
        sources = self.db.execute(
            "SELECT DISTINCT source FROM stock_assertion WHERE molecule_id=? ORDER BY source", (molecule_id,)
        ).fetchall()
        return (str(row[0]) if row and row[0] else None, tuple(str(r[0]) for r in sources))

    def count(self) -> int:
        return int(self.db.execute("SELECT count(*) FROM stock_molecule").fetchone()[0])

    def assertion_count(self) -> int:
        return int(self.db.execute("SELECT count(*) FROM stock_assertion").fetchone()[0])

    def commit(self) -> None:
        self.db.commit()


def _open_text(path: Path) -> TextIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def _handle_rows(handle: TextIO, delimiter: str | None) -> Iterator[list[str]]:
    if delimiter:
        yield from csv.reader(handle, delimiter=delimiter)
    else:
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                yield stripped.split()


def _rows(path: Path, delimiter: str | None) -> Iterator[list[str]]:
    if path.name.lower().endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                raw = archive.extractfile(member)
                if raw is not None:
                    with io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as handle:
                        yield from _handle_rows(handle, delimiter)
        return
    with _open_text(path) as handle:
        yield from _handle_rows(handle, delimiter)


def import_stock(
    path: Path,
    stock: SQLiteStock,
    *,
    source: str,
    version: str,
    profile: str = "building_blocks",
    delimiter: str | None = None,
    smiles_column: int = 0,
    id_column: int | None = 1,
    name_column: int | None = None,
    skip_header: bool = False,
    commit_interval: int = 10_000,
    max_records: int | None = None,
) -> dict[str, object]:
    """Stream SMILES/TSV/CSV while retaining provenance and rejection counts."""
    from rdkit import RDLogger

    RDLogger.DisableLog("rdApp.warning")  # type: ignore[attr-defined]
    RDLogger.DisableLog("rdApp.error")  # type: ignore[attr-defined]
    report: Counter[str] = Counter()
    rejections: Counter[str] = Counter()
    rows: Iterable[list[str]] = _rows(path, delimiter)
    iterator = iter(rows)
    if skip_header:
        next(iterator, None)
    for fields in iterator:
        if max_records is not None and report["records_read"] >= max_records:
            break
        report["records_read"] += 1
        try:
            structure = fields[smiles_column].strip()
            catalog_id = (
                fields[id_column].strip() if id_column is not None and len(fields) > id_column else ""
            )
            name = (
                fields[name_column].strip()
                if name_column is not None and len(fields) > name_column
                else None
            )
            if stock.add(
                structure, source=source, catalog_id=catalog_id, name=name or None,
                profile=profile, commit=False,
            ):
                report["assertions_indexed"] += 1
            else:
                report["duplicate_assertions"] += 1
            if report["records_read"] % commit_interval == 0:
                stock.commit()
        except (IndexError, ValueError) as exc:
            rejections[type(exc).__name__] += 1
    stock.set_metadata("version", version)
    stock.set_metadata("source", source)
    stock.set_metadata("profile", profile)
    stock.set_metadata("import_report", json.dumps(dict(report), sort_keys=True))
    stock.commit()
    return {
        **dict(report), "records_rejected": sum(rejections.values()),
        "rejection_reasons": dict(rejections), "molecules": stock.count(),
        "assertions": stock.assertion_count(), "version": stock.version,
    }


class SetStock:
    """Small fixture provider retained for isolated tests."""

    def __init__(self, smiles: list[str], version: str = "user",
                 metadata: dict[str, tuple[str | None, tuple[str, ...]]] | None = None) -> None:
        self.version = version
        self._ids = {canonical_identity(s)[0] for s in smiles}
        self._metadata = {
            canonical_identity(structure)[0]: details for structure, details in (metadata or {}).items()
        }

    def contains(self, smiles: str) -> bool:
        return canonical_identity(smiles)[0] in self._ids

    def describe(self, smiles: str) -> tuple[str | None, tuple[str, ...]]:
        return self._metadata.get(canonical_identity(smiles)[0], (None, ()))

    def count(self) -> int:
        return len(self._ids)

    @classmethod
    def from_file(cls, path: Path, version: str = "file") -> SetStock:
        structures: list[str] = []
        metadata: dict[str, tuple[str | None, tuple[str, ...]]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split("\t")]
            structures.append(parts[0])
            if len(parts) > 1:
                sources = tuple(filter(None, parts[2].split("|"))) if len(parts) > 2 else ()
                metadata[parts[0]] = (parts[1] or None, sources)
        return cls(structures, version, metadata)
