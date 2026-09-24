import pytest

from backend.app.config import Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.search import MODES, Retriever


def _retriever():
    chunks = [Chunk(f"c{i}", f"c{i}", "a.js", name, "function", 1, 1, text, text, str(i))
              for i, (name, text) in enumerate([("openBluetoothSettings", "open bluetooth settings deeplink"),
                                                 ("loginUser", "validate credentials and create session")])]
    return Retriever(chunks, None, None, Settings(semantic="off", ts_enrich=False))


def test_only_real_ranking_modes_exist():
    assert MODES == {"bm25", "dense", "hybrid"}


@pytest.mark.parametrize("mode", ["reranked", "full", ""])
def test_unknown_mode_is_rejected_instead_of_aliasing_hybrid(mode):
    with pytest.raises(ValueError, match="Unknown ranking mode"):
        _retriever().rank("bluetooth", mode=mode)


def test_title_field_counts_query_terms_that_name_the_symbol():
    retriever = _retriever()
    rows, _ = retriever.rank("bluetooth settings", mode="bm25", boosts=False)
    assert rows[0]["chunk"].qualified_name == "openBluetoothSettings"
    # Title tokens are precomputed once per index, aligned with chunks.
    assert retriever.title_tokens[0] >= {"bluetooth", "settings"}
    assert len(retriever.title_tokens) == len(retriever.chunks)
