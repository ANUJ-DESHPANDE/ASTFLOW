# Rejected during the audit: parser naming / test-directory heuristics (not shipped)

Idea: (a) treat `test/`, `tests/`, `spec/` directories as tests so the 0.82 test down-weight applies to
expressjs/express, and (b) name anonymous functions assigned to properties (`res.cookie = function (…)`) by the
property path instead of `anonymous@L:C`.

Probe: 8 hand-written questions about expressjs/express (`9a34acf`) with hand-checked answers (file + start line),
run through the real `investigate()` path, committed parser (f0a88b3) vs the change. Qualitative evidence only.

| | found in top 10 | MRR@10 |
|---|---|---|
| committed parser | 6 / 8 | 0.446 |
| with (a) + (b) | 5 / 8 | 0.365 |

Cause: once a file is a test, the parser names `it('should …', fn)` callbacks `test:should …`; those English
sentences then match natural-language questions in BM25's title field (weight 2.0) more strongly than the 0.82 test
down-weight suppresses them. (b) moved `res.cookie` above `clearCookie` for "How do I clear a cookie?".
Both changes were reverted. A future attempt would need to keep test descriptions out of the title field and be
evaluated on a larger judged set.
Note: this probe used lexical-only search (the model was not in the scratch cache); both variants ran under the same condition, so the comparison stands, but absolute numbers are lexical-only.
