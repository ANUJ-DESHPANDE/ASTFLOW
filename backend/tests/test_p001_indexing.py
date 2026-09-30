"""P001 lifecycle tests use the real index and search path with a cheap deterministic encoder."""

import hashlib
import subprocess
import threading

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.agent.investigate import investigate
from backend.app.config import Settings
from backend.app.indexing.discovery import read_snapshot
from backend.app.indexing.service import IndexService
from backend.app.main import create_app


def fake_encoder(calls):
    def encode(texts, kind="document"):
        calls.extend(texts if kind != "query" else [])
        vectors = []
        for text in texts:
            values = np.zeros(128, dtype=np.float32)
            for word in text.lower().split():
                values[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 128] += 1
            vectors.append(values / max(np.linalg.norm(values), 1))
        return np.stack(vectors)
    return encode


def service_for(repo, cache):
    service = IndexService(Settings(cache=cache, ts_enrich=False))
    calls = []
    service.embedder.model = object()
    service.embedder.attempted = True
    service.embedder.encode = fake_encoder(calls)
    return service, calls


def write(repo, name, term):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"export function {term}() {{ return '{term}'; }}\n", encoding="utf-8")


def signature(index):
    return ([(c.chunk_id, c.file_path, c.content_hash, c.search_text) for c in index.chunks],
            sorted(index.files), [(e.source_symbol_id, e.target_symbol_id) for e in index.edges])


def paths(index, term):
    return [r["file_path"] for r in investigate(index, term, "working-tree", agentic=False)["results"]]


def test_incremental_lifecycle_restart_failure_and_rebuild(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo, "a.js", "alphaunique")
    write(repo, "b.js", "betaunique")
    write(repo, "gone.js", "goneunique")
    write(repo, "move.js", "moveunique")
    service, calls = service_for(repo, tmp_path / "cache")
    first = service.index(str(repo))
    assert first.manifest["index_operation"] == "full"
    assert first.manifest["embedding_cache"]["computed"] == 4
    first_key = first.manifest["version_key"]

    calls.clear()
    assert service.index(str(repo)).manifest["version_key"] == first_key
    assert service.status["operation"] == "noop"
    assert service.status["embedding_cache"]["computed"] == 0 and not calls

    write(repo, "new.js", "newunique")
    added = service.index(str(repo))
    assert added.manifest["changes"]["files_added"] == 1
    assert added.manifest["embedding_cache"] == {"reused": 4, "computed": 1}
    assert len(calls) == 1
    assert any(c.file_path == "new.js" for c in added.chunks)
    assert "new.js" in paths(added, "newunique")

    calls.clear()
    write(repo, "b.js", "changedunique")
    modified = service.index(str(repo))
    assert modified.manifest["changes"]["files_modified"] == 1
    assert modified.manifest["embedding_cache"] == {"reused": 4, "computed": 1}
    assert len(calls) == 1
    assert all("betaunique" not in c.text for c in modified.chunks)
    assert any("changedunique" in c.text for c in modified.chunks)
    assert "b.js" in paths(modified, "changedunique")
    assert "b.js" not in paths(modified, "betaunique")
    assert service.get(first_key).manifest["version_key"] == first_key

    calls.clear()
    (repo / "gone.js").unlink()
    deleted = service.index(str(repo))
    assert deleted.manifest["changes"]["files_deleted"] == 1
    assert deleted.manifest["embedding_cache"]["computed"] == 0 and not calls
    assert all(c.file_path != "gone.js" for c in deleted.chunks)
    assert "gone.js" not in paths(deleted, "goneunique")

    calls.clear()
    (repo / "move.js").rename(repo / "renamed.js")
    renamed = service.index(str(repo))
    assert renamed.manifest["changes"]["files_renamed"] == 1
    assert all(c.file_path != "move.js" for c in renamed.chunks)
    assert any(c.file_path == "renamed.js" for c in renamed.chunks)
    assert "renamed.js" in paths(renamed, "moveunique")
    assert "move.js" not in paths(renamed, "moveunique")

    # One mixed cycle must match a clean rebuild, including graph and BM25 corpus.
    write(repo, "extra.js", "extraunique")
    write(repo, "a.js", "newalphaunique")
    (repo / "new.js").unlink()
    (repo / "renamed.js").rename(repo / "again.js")
    mixed = service.index(str(repo))
    assert {k: mixed.manifest["changes"][k] for k in
            ("files_added", "files_modified", "files_deleted", "files_renamed")} == {
                "files_added": 1, "files_modified": 1, "files_deleted": 1, "files_renamed": 1}
    clean, _ = service_for(repo, tmp_path / "clean-cache")
    rebuilt = clean.index(str(repo))
    assert signature(mixed) == signature(rebuilt)
    assert np.allclose(mixed.retriever.embeddings, rebuilt.retriever.embeddings)
    terms = mixed.retriever.tokenize("newalphaunique extraunique")
    assert np.array_equal(mixed.retriever.lexical_scores(terms), rebuilt.retriever.lexical_scores(terms))

    restarted, restart_calls = service_for(repo, tmp_path / "cache")
    loaded = restarted.get()
    assert signature(loaded) == signature(mixed)
    assert restarted.index(str(repo)).manifest["version_key"] == mixed.manifest["version_key"]
    assert not restart_calls
    assert restarted.get(first_key).manifest["version_key"] == first_key

    write(repo, "a.js", "failureunique")
    old_key = restarted.get().manifest["version_key"]
    restarted.embedder.encode = lambda texts, kind="document": (_ for _ in ()).throw(RuntimeError("controlled embedding failure"))
    with pytest.raises(RuntimeError, match="controlled embedding failure"):
        restarted.index(str(repo))
    assert restarted.get().manifest["version_key"] == old_key
    assert restarted.status["state"] == "error"
    restarted.embedder.encode = fake_encoder(restart_calls)
    assert restarted.index(str(repo)).manifest["version_key"] != old_key


def test_ignore_binary_cache_and_concurrent_request(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    write(repo, "live.js", "liveunique")
    write(repo, "ignored.js", "ignoredunique")
    (repo / ".gitignore").write_text("ignored.js\n", encoding="utf-8")
    (repo / "binary.js").write_bytes(b"\x00\xff\x00")
    cache = repo / "generated-cache"
    cache.mkdir()
    write(cache, "self.js", "selfunique")
    settings = Settings(cache=cache, semantic="off", ts_enrich=False)
    files, _, warnings = read_snapshot(repo, "working-tree", settings)
    assert list(files) == ["live.js"]
    assert any("non-UTF-8" in w for w in warnings)
    app = create_app(settings)
    client = TestClient(app)
    assert client.post("/api/index", json={"repo_path": str(repo), "background": False}).status_code == 200
    assert client.post("/api/search", json={"query": "liveunique", "agentic": False}).json()["results"]
    assert client.post("/api/index", json={"repo_path": str(repo), "background": False}).json()["manifest"]["version_key"]
    assert app.state.service.status["operation"] == "noop"
    app.state.index_lock.acquire()
    try:
        assert client.post("/api/index", json={"repo_path": str(repo)}).status_code == 409
    finally:
        app.state.index_lock.release()


def test_search_keeps_previous_snapshot_during_update(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo, "a.js", "oldunique")
    service, calls = service_for(repo, tmp_path / "cache")
    old = service.index(str(repo))
    old_key = old.manifest["version_key"]
    write(repo, "a.js", "newunique")
    entered, release = threading.Event(), threading.Event()
    normal_encode = service.embedder.encode

    def paused_encode(texts, kind="document"):
        if kind != "query":
            entered.set()
            assert release.wait(5)
        return normal_encode(texts, kind=kind)

    service.embedder.encode = paused_encode
    failure = []

    def update():
        try:
            service.index(str(repo))
        except Exception as exc:
            failure.append(exc)

    worker = threading.Thread(target=update)
    worker.start()
    try:
        assert entered.wait(5)
        active = service.get()
        assert active.manifest["version_key"] == old_key
        assert "a.js" in paths(active, "oldunique")
        assert all("newunique" not in c.text for c in active.chunks)
    finally:
        release.set()
        worker.join(timeout=5)
    assert not failure and not worker.is_alive()
    assert service.get().manifest["version_key"] != old_key
    assert "a.js" in paths(service.get(), "newunique")


def test_removing_last_source_publishes_empty_index(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo, "only.js", "lastunique")
    service, calls = service_for(repo, tmp_path / "cache")
    service.index(str(repo))
    calls.clear()
    (repo / "only.js").unlink()
    empty = service.index(str(repo))
    assert empty.manifest["changes"]["files_deleted"] == 1
    assert empty.chunks == [] and empty.files == {}
    assert paths(empty, "lastunique") == []
    assert not calls
