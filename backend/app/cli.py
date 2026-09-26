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
def snippets(query: str = typer.Argument(None, help="Natural-language query; omit to use --query-file or stdin"),
             corpus: list[str] = typer.Option(["apps"], "--corpus", "-c",
                                              help="'apps' (CoIR Apps), 'name=file.jsonl' or 'file.jsonl'; repeat for versions"),
             query_file: Path | None = typer.Option(None, help="Read the query (e.g. a full problem statement) from a file"),
             top_k: int = 10, mode: str = "hybrid", lines: int = 12, as_json: bool = typer.Option(False, "--json")):
    """Rank code snippets from a snippet corpus (the AppsRetrieval setting). Several --corpus values = versions."""
    import sys
    from backend.app.corpus import SnippetIndex, read_corpus, resolve
    text = query_file.read_text(encoding="utf-8") if query_file else query if query else sys.stdin.read()
    if not text.strip():
        raise typer.BadParameter("Provide a query, --query-file, or text on stdin")
    versions = {}
    for spec in corpus:
        name, path = resolve(spec)
        versions[name] = read_corpus(path)
    index = SnippetIndex(versions)
    found = index.search(text.strip(), top_k, mode)
    if as_json:
        return output({"index": index.stats, **found})
    typer.echo(f"{index.stats['distinct_snippets']} distinct snippets · versions {index.stats['versions']} · "
               f"embeddings {index.stats['embedding_cache']} · index {index.stats['index_seconds']} s · "
               f"{index.stats['semantic']['message']}")
    typer.echo(f"mode {found['mode']} · {found['latency_ms']} ms\n")
    for r in found["results"]:
        typer.echo(f"#{r['rank']}  {', '.join(r['occurrences'][:4])}{' …' if len(r['occurrences']) > 4 else ''}  "
                   f"score {r['score']}  (lexical rank {r['evidence']['lexical_rank']}, semantic rank {r['evidence']['semantic_rank']})")
        body = r["snippet"].splitlines()
        typer.echo("\n".join("    " + line for line in body[:lines]) + (f"\n    … {len(body) - lines} more lines" if len(body) > lines else ""))
        typer.echo("")


@cli.command()
def benchmark():
    from benchmark.evaluate import main
    main([])


if __name__ == "__main__":
    cli()
