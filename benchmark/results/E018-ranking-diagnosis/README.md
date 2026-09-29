# E018 ranking diagnosis (2026-09-29)

Starting commit: `fec272f`. Branch: `exp/E018-ranking-diagnosis`.
The established TRAIN DEV split has 300 queries. The saved campaign candidate ZIP
is SHA-256 `faf0c8d3c8fdd54bd6c66673f567dce19597aedaa08ff503594c1d669f0be3fa`.
`baseline.json` records the exact DEV ID and qrels hashes and the frozen campaign metrics.
Run `python -m benchmark.analyze_ranking_errors` to regenerate the artifacts.

Dense DEV NDCG@10 is 0.697734, MRR@10 0.663316, Recall@10 0.806667,
Recall@100 0.933333, and Recall@1000 0.990000. Of 300 queries, 55 have the
answer at ranks 11–1000 and only 3 miss the top 1000. The saved top-200 lists
give exact per-query ranks for 45 of the 55; the remaining 10 are counted from
the frozen campaign's aggregate Recall@500 and Recall@1000. Rank percentiles
in `oracle_analysis.json` apply only to those 45 observed top-200 failures.

Product BM25 adds 4 unique correct top-10 answers over dense, but none at
depth 1000. Among 58 dense top-10 failures, BM25 puts the answer in its own
top 10 for 4 queries, top 20 for 8, top 50 for 12, and top 100 for 15.
The dense/BM25 top-1000 union is still 0.99. A broad BM25 fusion is therefore
not the leading experiment; earlier fusion improved DEV but failed TEST.

Document truncation is weakly associated with these errors: 8/242 top-10
successes and 2/45 observed rank-11-to-200 failures have positive documents
longer than 512 ModernBERT tokens. `error_taxonomy.json` reports deterministic
signals rather than inferred semantic labels. The hard-negative file keeps
the top ten false positives and their BM25 scores for each observed failure.

**Decision:** Rank discrimination is the largest measured bottleneck. E019
tests one small operator-aware score adjustment on dense near-neighbor
candidates. The candidate-set oracle NDCG@10 of 0.99 is a ceiling, not an
expected model result. No TEST queries or labels were used in this diagnosis.
