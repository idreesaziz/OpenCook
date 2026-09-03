import os
from pathlib import Path

from .expansion import ExpansionProvider, NoExpansionProvider, RetroChimeraProvider
from .stock import SQLiteStock, StockProvider, import_stock
from .store import ReactionStore, load_fixture

ROOT = Path(__file__).resolve().parent.parent


def model_runtime() -> ExpansionProvider:
    provider = os.environ.get("OPENCOOK_MODEL_PROVIDER", "none").strip().lower()
    if provider in {"", "none", "disabled"}:
        return NoExpansionProvider()
    if provider == "retrochimera":
        configured = os.environ.get("OPENCOOK_RETROCHIMERA_MODEL_DIR")
        worker = os.environ.get("OPENCOOK_MODEL_PYTHON")
        default_worker = ROOT / ".model-venv" / "Scripts" / "python.exe"
        worker_path = Path(worker) if worker else (default_worker if default_worker.exists() else None)
        return RetroChimeraProvider(
            Path(configured) if configured else None,
            worker_python=worker_path,
        )
    raise RuntimeError(f"Unknown OPENCOOK_MODEL_PROVIDER: {provider}")


def demo_runtime(db_path: str | None = None) -> tuple[ReactionStore, StockProvider]:
    selected_path = (
        db_path
        if db_path is not None
        else os.environ.get("OPENCOOK_DATABASE", str(ROOT / "data" / "opencook.sqlite"))
    )
    store = ReactionStore(selected_path)
    if store.counts()["reaction"] == 0:
        load_fixture(store, ROOT / "data" / "fixtures" / "reactions.json")
    stock_path = Path(os.environ.get("OPENCOOK_STOCK_DATABASE", ROOT / "data" / "stock.sqlite"))
    stock = SQLiteStock(stock_path)
    if stock.count() == 0:
        import_stock(
            ROOT / "data" / "fixtures" / "stock.smi", stock,
            source="OpenCook benign fixture", version="fixture-1",
            delimiter="\t", id_column=None, name_column=1,
        )
    return store, stock
