"""Repeatable P001 product walkthrough; uses the locally installed GTE model."""

import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path

from backend.app.agent.investigate import investigate
from backend.app.config import FROZEN_MODEL, FROZEN_MODEL_REVISION, ROOT, Settings
from backend.app.indexing.service import IndexService


OUT = ROOT / "benchmark" / "results" / "P001-incremental-indexing"
MODEL_DIR = ROOT / ".astflow" / "models" / FROZEN_MODEL.replace("/", "--")


def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_index(service, repo, name):
    started = time.perf_counter()
    index = service.index(str(repo))
    record = {"wall_ms": round((time.perf_counter() - started) * 1000, 2),
              "operation": service.status["operation"],
              "changes": service.status["changes"],
              "embedding_cache": service.status["embedding_cache"],
              "documents": len(index.chunks), "files": len(index.files),
              "version_key": index.manifest["version_key"],
              "timings_ms": service.status.get("timings_ms", {})}
    write(name + ".json", record)
    return index, record


def search(index, query):
    return investigate(index, query, "working-tree", agentic=False)["results"]


def source(path, word):
    path.write_text(f"export function {word}() {{ return '{word}'; }}\n", encoding="utf-8")


def main():
    if not (MODEL_DIR / "modules.json").exists():
        raise RuntimeError("Accepted GTE model is not installed locally")
    with tempfile.TemporaryDirectory(prefix="astflow-p001-") as temporary:
        workspace = Path(temporary)
        repo = workspace / "demo-copy"
        shutil.copytree(ROOT / "examples" / "demo-repo", repo, ignore=shutil.ignore_patterns(".git"))
        cache = workspace / "cache"
        local_model = cache / "models" / FROZEN_MODEL.replace("/", "--")
        local_model.parent.mkdir(parents=True)
        shutil.copytree(MODEL_DIR, local_model)
        settings = Settings(cache=cache, ts_enrich=False)
        service = IndexService(settings)
        write("baseline_state.json", {"model": FROZEN_MODEL, "revision": FROZEN_MODEL_REVISION,
                                       "retrieval": settings.retrieval, "schema": settings.schema,
                                       "repository": "copied examples/demo-repo"})
        write("fixture_manifest.json", {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in sorted(repo.rglob("*.js"))})

        fresh, full = run_index(service, repo, "fresh_index")
        assert any("BluetoothAgent.js" in r["file_path"] for r in search(fresh, "BluetoothAgent"))
        noop, same = run_index(service, repo, "noop_update")
        assert same["operation"] == "noop" and same["embedding_cache"]["computed"] == 0

        file = repo / "p001_feature.js"
        source(file, "p001aurora")
        added, add = run_index(service, repo, "add_update")
        assert any(r["file_path"] == file.name for r in search(added, "p001aurora"))

        source(file, "p001nebula")
        modified, mod = run_index(service, repo, "modify_update")
        assert any(r["file_path"] == file.name for r in search(modified, "p001nebula"))
        assert all("p001aurora" not in r["snippet"] for r in search(modified, "p001aurora"))
        # A fair warm comparison uses the same loaded model and an empty index
        # cache, then embeds every document in the modified snapshot.
        warm = IndexService(Settings(cache=workspace / "warm-cache", ts_enrich=False))
        warm.embedder.model = service.embedder.model
        warm.embedder.attempted = True
        warm_started = time.perf_counter()
        warm_full = warm.index(str(repo))
        warm_full_ms = round((time.perf_counter() - warm_started) * 1000, 2)
        assert warm_full.manifest["embedding_cache"]["computed"] == len(warm_full.chunks)

        renamed_file = repo / "p001_renamed.js"
        file.rename(renamed_file)
        renamed, rename = run_index(service, repo, "rename_update")
        assert any(r["file_path"] == renamed_file.name for r in search(renamed, "p001nebula"))
        assert all(r["file_path"] != file.name for r in search(renamed, "p001nebula"))

        renamed_file.unlink()
        deleted, delete = run_index(service, repo, "delete_update")
        assert all(r["file_path"] != renamed_file.name for r in search(deleted, "p001nebula"))

        source(repo / "p001_mixed_add.js", "p001comet")
        source(repo / "p001_mixed_modify.js", "p001old")
        source(repo / "p001_mixed_delete.js", "p001gone")
        source(repo / "p001_mixed_move.js", "p001move")
        service.index(str(repo))
        source(repo / "p001_mixed_modify.js", "p001new")
        (repo / "p001_mixed_delete.js").unlink()
        (repo / "p001_mixed_move.js").rename(repo / "p001_mixed_moved.js")
        source(repo / "p001_mixed_extra.js", "p001extra")
        mixed, mixed_record = run_index(service, repo, "mixed_update")
        assert all(mixed_record["changes"][k] == 1 for k in
                   ("files_added", "files_modified", "files_deleted", "files_renamed"))

        clean = IndexService(Settings(cache=workspace / "clean-cache", semantic="off", ts_enrich=False))
        rebuilt = clean.index(str(repo))
        logical = lambda idx: [(c.chunk_id, c.file_path, c.content_hash, c.search_text) for c in idx.chunks]
        assert logical(mixed) == logical(rebuilt)
        assert [(e.source_symbol_id, e.target_symbol_id) for e in mixed.edges] == [
            (e.source_symbol_id, e.target_symbol_id) for e in rebuilt.edges]
        write("rebuild_equivalence.json", {"passed": True, "documents": len(mixed.chunks),
                                           "files": len(mixed.files), "vectors_compared": False,
                                           "note": "Logical documents and graph compared; vector equivalence uses deterministic automated fixture."})

        restarted = IndexService(settings)
        loaded = restarted.get()
        assert logical(loaded) == logical(mixed)
        assert search(loaded, "BluetoothAgent")
        write("restart_test.json", {"passed": True, "version_key": loaded.manifest["version_key"],
                                    "no_rebuild": True})

        source(repo / "p001_failure.js", "p001failure")
        old_key = restarted.get().manifest["version_key"]
        original = restarted.embedder.encode
        restarted.embedder.encode = lambda texts, **kwargs: (_ for _ in ()).throw(RuntimeError("controlled failure"))
        failed = False
        try:
            restarted.index(str(repo))
        except RuntimeError:
            failed = True
        assert failed and restarted.get().manifest["version_key"] == old_key
        restarted.embedder.encode = original
        recovered = restarted.index(str(repo))
        assert recovered.manifest["version_key"] != old_key
        write("failure_recovery.json", {"controlled_failure": True, "old_key_preserved": old_key,
                                        "retry_key": recovered.manifest["version_key"], "retry_passed": True})

        ratio = round(mod["wall_ms"] / warm_full_ms, 4)
        write("performance.json", {"repository": "copied examples/demo-repo", "initial_files": full["files"],
                                   "initial_documents": full["documents"], "full_cold_ms": full["wall_ms"],
                                   "full_warm_ms": warm_full_ms,
                                   "noop_ms": same["wall_ms"], "add_ms": add["wall_ms"],
                                   "modify_ms": mod["wall_ms"], "delete_ms": delete["wall_ms"],
                                   "rename_ms": rename["wall_ms"], "mixed_ms": mixed_record["wall_ms"],
                                   "modify_warm_full_ratio": ratio,
                                   "modify_documents_computed": mod["embedding_cache"]["computed"],
                                   "modify_total_documents": mod["documents"]})
        write("real_repo_walkthrough.json", {"repository": "isolated copy of examples/demo-repo",
                                            "fresh": True, "noop": True, "add": True, "modify": True,
                                            "rename": True, "delete": True, "mixed": True,
                                            "restart": True, "controlled_failure": True, "overall": "PASS"})

    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(OUT.glob("*.json")) if p.name != "artifact_hashes.json"}
    write("artifact_hashes.json", hashes)
    print(json.dumps({"result": "PASS", "performance": json.loads((OUT / "performance.json").read_text())}, indent=2))


if __name__ == "__main__":
    main()
