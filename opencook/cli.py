from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

import typer

from . import __version__
from .availability import AvailabilityGateway
from .chemistry import normalize
from .runtime import demo_runtime, model_runtime
from .search import BestFirstPlanner, BreadthFirstPlanner, SearchConfig
from .stock import SQLiteStock, import_stock
from .store import ReactionStore, load_fixture

app = typer.Typer(help="OpenCook — reaction-data retrosynthesis")
data_app = typer.Typer(help="Manage reaction corpora")
stock_app = typer.Typer(help="Manage starting-material stocks")
app.add_typer(data_app, name="data")
app.add_typer(stock_app, name="stock")


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json")) -> None:
    store, stock = demo_runtime()
    result = {
        "status": "ok",
        "version": __version__,
        "rdkit": __import__("rdkit").__version__,
        "database": store.counts(),
        "stock_version": stock.version,
        "stock_molecules": stock.count(),
    }
    typer.echo(
        json.dumps(result, indent=2) if json_output else "\n".join(f"{k}: {v}" for k, v in result.items())
    )


@data_app.command("list")
def data_list() -> None:
    typer.echo("fixture\t1\tbundled\tCC0-1.0\nord\tcurrent\toptional\tCC-BY-SA-4.0")


@data_app.command("import")
def data_import(path: Path, database: Path = Path("opencook.sqlite")) -> None:
    store = ReactionStore(database)
    typer.echo(json.dumps(load_fixture(store, path), indent=2))


@data_app.command("import-ord")
def import_ord_dataset(
    path: Path,
    database: Path = Path("data/opencook.sqlite"),
    start_at: int = typer.Option(0, min=0, help="Resume after this zero-based ORD row offset."),
) -> None:
    """Import an official ORD .parquet or .pb.gz dataset."""
    from .ord_import import import_ord

    def progress(read: int, total: int) -> None:
        typer.echo(f"ORD import: {read:,}/{total:,} records ({read / total:.1%})")

    typer.echo(
        json.dumps(
            import_ord(path, ReactionStore(database), progress=progress, start_at=start_at),
            indent=2,
        )
    )


@data_app.command("download")
def data_download(dataset_id: str, output: Path = Path("data/downloads")) -> None:
    if dataset_id.lower() == "ord":
        raise typer.BadParameter(
            "Specify an ORD dataset ID; enumerate IDs at the official ord-data repository."
        )
    try:
        from ord_schema import huggingface
    except ImportError as exc:
        raise typer.BadParameter("Install the ORD extra: uv sync --extra ord") from exc
    output.mkdir(parents=True, exist_ok=True)
    path = huggingface.fetch_dataset(dataset_id, cache_dir=output)
    typer.echo(str(path))


@stock_app.command("import")
def stock_import(
    path: Path,
    database: Path = Path("data/stock.sqlite"),
    source: str = typer.Option(..., help="Catalog or dataset asserting availability."),
    version: str = typer.Option(..., help="Immutable source snapshot/version."),
    profile: str = typer.Option("building_blocks"),
    delimiter: str | None = typer.Option(None, help="Use 'tab' or 'comma'; default is whitespace."),
    smiles_column: int = 0,
    id_column: int | None = 1,
    name_column: int | None = None,
    skip_header: bool = False,
    max_records: int | None = typer.Option(None, min=1, help="Optional bounded import size."),
) -> None:
    """Stream a SMILES, TSV, CSV, or gzip-compressed catalog into local stock."""
    separators = {"tab": "\t", "comma": ",", None: None}
    if delimiter not in separators:
        raise typer.BadParameter("delimiter must be 'tab' or 'comma'")
    report = import_stock(
        path,
        SQLiteStock(database),
        source=source,
        version=version,
        profile=profile,
        delimiter=separators[delimiter],
        smiles_column=smiles_column,
        id_column=id_column,
        name_column=name_column,
        skip_header=skip_header,
        max_records=max_records,
    )
    typer.echo(json.dumps(report, indent=2))


@stock_app.command("status")
def stock_status(database: Path = Path("data/stock.sqlite")) -> None:
    catalog = SQLiteStock(database)
    typer.echo(
        json.dumps(
            {
                "database": str(database),
                "version": catalog.version,
                "molecules": catalog.count(),
                "assertions": catalog.assertion_count(),
            },
            indent=2,
        )
    )


@stock_app.command("verify")
def stock_verify(
    structure: str,
    country: str = typer.Option(..., min=2, max=2),
    url: list[str] | None = None,
    service: str = typer.Option("http://127.0.0.1:8787"),
    database: Path = Path("data/stock.sqlite"),
    buyer_class: str = typer.Option("ordinary_individual"),
) -> None:
    """Verify exact availability through AvailEvidence and update a stock snapshot."""
    result = AvailabilityGateway(service).verify_into_snapshot(
        SQLiteStock(database),
        structure,
        country=country,
        supplied_urls=url,
        buyer_class=buyer_class,
    )
    typer.echo(json.dumps(asdict(result), indent=2))


@app.command()
def search(
    target: str,
    planner: str = "andor_best_first",
    routes: int = 5,
    max_depth: int = 8,
    model_fallback: bool = typer.Option(False, "--model-fallback"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    store, stock = demo_runtime()
    cls = BreadthFirstPlanner if planner == "breadth_first_baseline" else BestFirstPlanner
    found, stats = cls(store, stock, model_runtime()).search(
        target,
        SearchConfig(routes=routes, max_depth=max_depth, model_fallback=model_fallback),
    )
    result = {
        "target": asdict(normalize(target)),
        "planner": cls.name,
        "routes": [r.to_dict() for r in found],
        "stats": asdict(stats),
    }
    if json_output:
        typer.echo(json.dumps(result, indent=2))
        return
    typer.echo(
        f"{len(found)} complete route(s); {stats.molecules_expanded} expansions "
        f"in {stats.elapsed_seconds:.4f}s"
    )
    for i, route in enumerate(found, 1):
        typer.echo(
            f"{i}. score={route.metrics.total_score:.3f} "
            f"steps={route.metrics.transformations} reactions={route.signature}"
        )
    if not found:
        typer.echo(
            "No complete route found under the current search configuration and available reaction corpus."
        )


@app.command()
def benchmark(iterations: int = 20, json_output: bool = typer.Option(False, "--json")) -> None:
    store, stock = demo_runtime()
    target = "CC(=O)OCCO"
    rows = []
    for cls in (BreadthFirstPlanner, BestFirstPlanner):
        durations = []
        result_count = expansions = 0
        for _ in range(iterations):
            started = time.perf_counter()
            found, stats = cls(store, stock).search(target)
            durations.append(time.perf_counter() - started)
            result_count, expansions = len(found), stats.molecules_expanded
        rows.append(
            {
                "planner": cls.name,
                "iterations": iterations,
                "routes": result_count,
                "expansions": expansions,
                "mean_ms": round(sum(durations) * 1000 / iterations, 3),
                "min_ms": round(min(durations) * 1000, 3),
            }
        )
    typer.echo(json.dumps(rows, indent=2) if json_output else "\n".join(str(r) for r in rows))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run("opencook.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
