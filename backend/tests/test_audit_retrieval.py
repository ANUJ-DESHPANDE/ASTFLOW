import numpy as np
from backend.app.config import Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.search import Retriever,tokenize

def test_sparse_bm25_matches_reference_including_repeated_tokens():
    texts=['camelCase snake_case apple apple', 'banana apple','the and or', 'apple']
    chunks=[Chunk(str(i),str(i),'',str(i),'module',1,1,t,t,str(i)) for i,t in enumerate(texts)]
    retriever=Retriever(chunks,None,None,Settings(semantic='off'))
    for query in ['apple','apple apple snake case','unknown','the','camelCase banana','']:
        terms=tokenize(query)
        assert np.allclose(retriever.lexical_scores(terms),retriever.bm25.get_scores(terms),rtol=1e-12,atol=1e-12)
    assert len(retriever.rank('apple',mode='bm25',limit=2)[0]) >= 2
