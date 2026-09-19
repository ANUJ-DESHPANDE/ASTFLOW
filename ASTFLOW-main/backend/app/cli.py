import json
from pathlib import Path

import typer

from backend.app.agent.investigate import investigate
from backend.app.config import Settings
from backend.app.indexing.service import IndexService
from backend.app.versions.compare import compare_indexes

cli = typer.Typer(help="ASTFLOW · Source-backed repository investigation", no_args_is_help=True)


def output(value):
    typer.echo(json.dumps(value, indent=2, ensure_ascii=True))


@cli.command()
def index(path: Path, version: str = "working-tree"):
    output(IndexService().index(str(path), version).manifest)


@cli.command()
def search(path: Path, query: str, version: str = "working-tree", top_k: int = 10, agentic: bool = True):
    service = IndexService()
    snapshot = service.index(str(path), version)
    output(investigate(snapshot, query, version, top_k, agentic))


@cli.command()
def compare(path: Path, query: str, version_a: str, version_b: str):
    service = IndexService()
    a, b = service.index(str(path), version_a), service.index(str(path), version_b)
    output(compare_indexes(a, b, query, version_a, version_b))


@cli.command()
def serve(path: Path | None = typer.Argument(None), port: int = 8000):
    import uvicorn
    from backend.app.main import create_app
    app = create_app()
    if path:
        app.state.service.index(str(path))
    uvicorn.run(app, host="127.0.0.1", port=port)


@cli.command()
def model_download():
    """Explicitly download the configured CPU model. Never executes repository code."""
    from backend.app.retrieval.embeddings import Embedder
    embedder = Embedder(Settings())
    model = embedder.load(download=True)
    output(embedder.status)
    if model is None:
        raise typer.Exit(1)


@cli.command()
def demo(port: int = 8000):
    """Prepare the bundled Git fixture, index its snapshots, and start the UI."""
    import uvicorn
    from scripts.setup_demo import setup
    from backend.app.config import ROOT
    from backend.app.main import create_app
    setup()
    app = create_app()
    service = app.state.service
    for version in ["v1", "v2", "working-tree"]:
        manifest = service.index(str(ROOT / "examples/demo-repo"), version).manifest
        typer.echo(f"{version}: {manifest['chunk_count']} snippets, {manifest['edge_count']} relationships")
    uvicorn.run(app, host="127.0.0.1", port=port)


@cli.command()
def benchmark():
    from benchmark.evaluate import main
    main([])


if __name__ == "__main__":
    cli()
