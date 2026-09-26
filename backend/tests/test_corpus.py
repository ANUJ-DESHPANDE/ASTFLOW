import hashlib
import json

import numpy as np

from backend.app.config import Settings
from backend.app.corpus import SnippetIndex, read_corpus, resolve
from backend.app.retrieval.embeddings import Embedder

V1 = {"a": "def max_subarray(nums):\n    best = cur = nums[0]\n    return best",
      "b": "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a"}
V2 = {"a": V1["a"],  # unchanged across versions
      "b": "def gcd(a, b):\n    return a if b == 0 else gcd(b, a % b)",  # changed
      "c": "def is_prime(n):\n    return n > 1 and all(n % d for d in range(2, n))"}


class CountingEmbedder(Embedder):
    def __init__(self, settings):
        super().__init__(settings)
        self.model, self.attempted, self.calls = object(), True, []

    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        return np.array([[float(len(t) % 5 + 1), float(sum(map(ord, t)) % 7 + 1)] for t in texts], dtype=np.float32)


def test_reads_beir_jsonl_and_names_versions(tmp_path):
    path = tmp_path / "v1.jsonl"
    path.write_text("\n".join(json.dumps({"_id": k, "text": v}) for k, v in V1.items()), encoding="utf-8")
    assert read_corpus(path) == V1
    assert resolve(str(path)) == ("v1", path.resolve())
    assert resolve(f"release={path}") == ("release", path.resolve())


def test_lexical_search_returns_snippet_with_location(tmp_path):
    index = SnippetIndex({"v1": V1}, Settings(cache=tmp_path, semantic="off"))
    found = index.search("greatest common divisor gcd of two numbers", top_k=2)
    assert found["mode"] == "bm25"  # no model: truthful fallback, never labelled hybrid
    assert found["results"][0]["occurrences"] == ["v1:b"]


def test_identical_snippets_fold_across_versions_and_changes_stay_separate(tmp_path):
    index = SnippetIndex({"v1": V1, "v2": V2}, Settings(cache=tmp_path, semantic="off"))
    assert index.stats["distinct_snippets"] == 4  # a (shared), b@v1, b@v2, c
    found = index.search("max subarray best sum", top_k=4)
    top = found["results"][0]
    assert top["occurrences"] == ["v1:a", "v2:a"] and top["versions"] == ["v1", "v2"]
    gcd = [r for r in index.search("gcd", top_k=4)["results"] if r["id"] == "b"]
    assert sorted(r["versions"][0] for r in gcd) == ["v1", "v2"] and all(len(r["versions"]) == 1 for r in gcd)


def test_new_version_embeds_only_changed_snippets(tmp_path):
    settings = Settings(cache=tmp_path)
    first = CountingEmbedder(settings)
    SnippetIndex({"v1": V1}, settings, first)
    assert sum(map(len, first.calls)) == 2
    second = CountingEmbedder(settings)
    index = SnippetIndex({"v2": V2}, settings, second)
    assert index.stats["embedding_cache"] == {"reused": 1, "computed": 2, "precomputed": 0}  # a reused; b changed, c new
    assert sum(map(len, second.calls)) == 2
    third = CountingEmbedder(settings)
    SnippetIndex({"v1": V1, "v2": V2}, settings, third)
    assert third.calls == []  # every version already embedded


class UnitEmbedder(CountingEmbedder):
    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        rows = np.array([[len(t) % 7 + 1.0, sum(map(ord, t)) % 11 + 1.0, 1.0] for t in texts], dtype=np.float32)
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)


def _published(tmp_path, snippets, vectors, model="Alibaba-NLP/gte-modernbert-base"):
    path = tmp_path / "published.npz"
    keys = [hashlib.sha256(t.encode()).hexdigest() for t in snippets.values()]
    np.savez_compressed(path, model=np.array(model), hashes=np.array(keys), vectors=vectors)
    return path.as_uri()


def test_published_corpus_vectors_are_used_after_a_live_spot_check(tmp_path, monkeypatch):
    import backend.app.corpus as corpus
    snippets = {str(i): f"def solve_{i}(n):\n    return n * {i}" for i in range(300)}
    settings = Settings(cache=tmp_path / "cache")
    reference = UnitEmbedder(settings).encode(list(snippets.values()))
    monkeypatch.setitem(corpus.PREBUILT, settings.model, _published(tmp_path, snippets, reference))
    embedder = UnitEmbedder(settings)
    index = SnippetIndex({"apps": snippets}, settings, embedder)
    assert index.stats["embedding_cache"] == {"reused": 0, "computed": 0, "precomputed": 300}
    assert sum(map(len, embedder.calls)) == 8  # only the spot check was encoded


def test_published_vectors_that_disagree_with_live_encoding_are_rejected(tmp_path, monkeypatch):
    import backend.app.corpus as corpus
    snippets = {str(i): f"def solve_{i}(n):\n    return n * {i}" for i in range(300)}
    settings = Settings(cache=tmp_path / "cache")
    wrong = np.tile(np.array([[0., 0., 1.]], dtype=np.float32), (300, 1))
    monkeypatch.setitem(corpus.PREBUILT, settings.model, _published(tmp_path, snippets, wrong))
    index = SnippetIndex({"apps": snippets}, settings, UnitEmbedder(settings))
    assert index.stats["embedding_cache"] == {"reused": 0, "computed": 300, "precomputed": 0}
