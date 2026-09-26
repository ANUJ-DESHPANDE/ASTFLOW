"""P1 check for the frozen retrieval model: three real express releases as Git versions, indexed with that model.

For each version: cold/incremental index time, embedding reuse, and the top results for a query whose code changed
between releases. Every returned snippet is compared with the file content *at that version* (`git show`), so a
result from the wrong version, file or line range fails the check.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.agent.investigate import investigate
from backend.app.config import Settings
from backend.app.indexing.service import IndexService
from backend.app.retrieval.embeddings import Embedder

VERSIONS = ["4.18.2", "4.19.2", "4.21.2"]
QUERY = "where is the redirect location URL encoded"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def build_repo(root: Path) -> Path:
    repo = root / "express"
    repo.mkdir()
    git(repo, "init", "-q")
    for version in VERSIONS:
        tarball = subprocess.run(["npm", "pack", f"express@{version}", "--silent"], cwd=root, check=True,
                                 capture_output=True, text=True).stdout.strip().splitlines()[-1]
        subprocess.run(["rm", "-rf", "lib", "index.js"], cwd=repo, check=True)
        subprocess.run(["tar", "xzf", str(root / tarball), "--strip-components=1", "package/lib", "package/index.js"],
                       cwd=repo, check=True)
        git(repo, "add", "-A")
        git(repo, "-c", "user.name=p1", "-c", "user.email=p1@example.invalid", "commit", "-q", "-m", f"express {version}")
        git(repo, "tag", f"v{version}")
    return repo


def main():
    model = sys.argv[1]
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = Settings(model=model, cache=root / "cache", ts_enrich=False)
        Embedder(settings).load(download=True)  # explicit model download into this cache
        repo = build_repo(root)
        service = IndexService(settings)
        rows, ok = [], True
        for tag in [f"v{v}" for v in VERSIONS]:
            started = time.perf_counter()
            snapshot = service.index(str(repo), tag)
            index_s = time.perf_counter() - started
            started = time.perf_counter()
            result = investigate(snapshot, QUERY, tag, 3, True)
            query_ms = (time.perf_counter() - started) * 1000
            top = []
            for r in result["results"][:3]:
                lines = git(repo, "show", f"{tag}:{r['file_path']}").splitlines()
                exact = "\n".join(lines[r["start_line"] - 1:r["end_line"]]).strip() == r["snippet"].strip()
                ok &= exact
                top.append({"file": r["file_path"], "lines": [r["start_line"], r["end_line"]], "symbol": r["qualified_name"],
                            "matches_version_source": exact})
            rows.append({"version": tag, "index_s": round(index_s, 1), "embedding_cache": snapshot.manifest.get("embedding_cache"),
                         "chunks": snapshot.manifest["chunk_count"], "semantic": snapshot.manifest.get("semantic"),
                         "query_ms": round(query_ms, 1), "top": top})
        report = {"model": model, "query": QUERY, "versions": rows, "all_snippets_match_their_version": ok}
        (out / "p1.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        lines = [f"# P1 with {model}: {'PASS' if ok else 'FAIL'}", "", f"Query: {QUERY!r}", "",
                 "| Version | Index s | Embeddings reused/computed | Query ms | Top result | Matches that version's source |",
                 "|---|---:|---|---:|---|---|"]
        for r in rows:
            c, t = r["embedding_cache"] or {}, r["top"][0]
            lines.append(f"| {r['version']} | {r['index_s']} | {c.get('reused')}/{c.get('computed')} | {r['query_ms']} | "
                         f"{t['file']}:{t['lines'][0]}-{t['lines'][1]} {t['symbol']} | {all(x['matches_version_source'] for x in r['top'])} |")
        text = "\n".join(lines) + "\n"
        print(text)
        import os
        if os.getenv("GITHUB_STEP_SUMMARY"):
            Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8").write(text)
        if not ok:
            raise SystemExit("P1 FAIL: a snippet does not match its version's source")


if __name__ == "__main__":
    main()
