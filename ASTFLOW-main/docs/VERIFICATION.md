# Verification — 19 September 2026

## Executed checks

| Check | Result |
|---|---|
| Backend pytest suite | **41 passed, 1 skipped** |
| Production TypeScript/Vite build | Passed |
| Live Edge browser suite | **8 passed** |
| Live API demo verification | Index v1/v2/working-tree, search, source, trace, refinement and comparison passed |
| npm audit after clean install | **0 known advisories** |
| Installed Python environment audit, after pip upgrade | **0 known advisories** |
| Complete pinned Python requirements audit | **0 known advisories**, after updating datasets to 5.0.1 |
| Restored fixture benchmark | Executed: 16 questions, 21 chunks, category metrics included |

The optional real embedding-model test was skipped because sentence-transformers/model weights were not installed in the validation environment. Benchmark rows explicitly identify lexical fallback; dense quality is not claimed. The optional dataset adapter's pinned packages were audited, but its remote dataset download was not rerun. Application-local `astflow` source is not a PyPI dependency and is excluded by the dependency auditor; it was reviewed and tested directly.

The replacement studio browser suite exercises real API responses: source tabs and zoom, explorer/companion toggles, loading and search evidence, map drill-down and trace call sites, before/after source comparison, delayed search across a snapshot switch, mobile drawers and reduced motion, modal focus containment, and reindex completion. The previous dashboard-specific suite has been replaced because those screens were removed.

The first run had seven passes and one test-selector failure (the accessible file-tab name contains a space after its JS icon). The selector was corrected; the final run is reported above. Screenshots are under `docs/screenshots/`.

Backend and dependency-audit results above are from the preceding correctness/security pass. This UI replacement did not change backend code or dependency versions.

Backend regressions cover shadowing, mutation, computed writes, invalid instance inference, constructor-parameter shadowing, static/accessor methods, parse errors, duplicate IDs, unsupported import boundaries, supporting spans, reversed traversal, call-site multiplicity, sequence direction, trace ambiguity/limits, source coordinates, request security and checkpoint immutability.

## Notable fixes during verification

- Fresh-clone demo failure: restored actual source files instead of an unmapped gitlink.
- Vulnerable DOMPurify dependency: root override and clean regenerated lockfile resolve 3.4.15.
- Optional datasets 4.8.5 vulnerability: updated to patched 5.0.1.
- Old environment pip advisories: upgraded pip and updated setup to do the same.
- Transient Windows/OneDrive index publication lock: bounded retry around atomic rename.
- Browser test selector updated to distinguish the Compare view tab from the Compare submit action.

Dependency scans report known advisories at the time of execution; they are not a guarantee of complete security. The application remains intended for one user on loopback.

## Remaining limitations

- No manually judged real-repository benchmark replacing the small demo fixture.
- No independently validated dense-model run in this environment.
- Monaco is lazy-loaded but emits a large-bundle build warning.
- Two test-library deprecation warnings remain; they do not fail the tests.
- This is an adaptation of the supplied video to ASTFLOW workflows, not a copy of the unrelated website shown inside its preview.

See [changes and scope](CHANGES.md), [benchmark results](../benchmark/results/local.md), and [live API measurements](../benchmark/results/verification.json).
