All baselines use the same indexed code chunks and relevance judgments.

- **BM25 only:** code-aware tokens and BM25 with positive IDF, no symbol or graph boosts.
- **Dense only:** normalized CPU embeddings, ranked by dot product; unavailable when the model is absent.
- **Hybrid:** reciprocal rank fusion of lexical and dense ranks, no symbol or graph boosts.
- **Hybrid + structure:** hybrid plus bounded caller/callee proximity.
- **ASTFLOW full:** hybrid, exact-symbol and name-token boosts, test balancing, graph expansion, and up to two evidence-driven retrieval passes.

The local benchmark is a handcrafted demo regression set, not an independent generalization estimate. MRR scans at most 50 retrieved candidates; NDCG and recall use the top ten. Raw per-query rankings are saved so aggregate improvements and regressions can be inspected.
