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

