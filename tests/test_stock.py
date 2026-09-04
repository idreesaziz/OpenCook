from pathlib import Path

from opencook.stock import SQLiteStock, import_stock


def test_sqlite_stock_stream_import_and_provenance(tmp_path: Path) -> None:
    source = tmp_path / "catalog.smi"
    source.write_text("CC(=O)OC(C)=O ZINC1\nO=C(O)c1ccccc1O ZINC2\ninvalid ZINC3\n", encoding="utf-8")
    stock = SQLiteStock(tmp_path / "stock.sqlite")

    report = import_stock(source, stock, source="test catalog", version="2026-09")

    assert report["records_read"] == 3
    assert report["records_rejected"] == 1
    assert stock.count() == 2
    assert stock.contains("CC(=O)OC(C)=O")
    assert stock.describe("O=C(O)c1ccccc1O")[1] == ("test catalog",)
    assert stock.version == "2026-09"


def test_duplicate_catalog_assertions_are_not_duplicated(tmp_path: Path) -> None:
    source = tmp_path / "catalog.smi"
    source.write_text("O water\nO water\n", encoding="utf-8")
    stock = SQLiteStock(tmp_path / "stock.sqlite")

    report = import_stock(source, stock, source="test", version="1")

    assert report["molecules"] == 1
    assert report["assertions"] == 1
    assert report["duplicate_assertions"] == 1
