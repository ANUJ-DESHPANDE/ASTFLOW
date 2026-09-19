# Reference UI and correctness update

## Visual direction

The supplied video is the design reference: near-black editor panels, teal ambient background, narrow icon rail, left explorer, central workspace, right explanation panel, bottom composer, gray glass controls, and a blue-to-green active tab. Short fade/slide reveals and green source highlights follow that language. Reduced-motion preferences disable animation. The lime website inside the reference editor is preview content, not the editor's theme.

The old dashboard components and both legacy stylesheets have been removed. The replacement uses a single new studio stylesheet, a compact Map / Compare / Code switch, horizontal closable source tabs, editor zoom, collapsible explorer and companion, and a pinned chat composer. Trace is available within Map; source search runs through the composer. Real before/after source appears both in Monaco and the conversation evidence card. No website generator, code-editing agent, invitation feature or unrelated video button was invented. Explanations and before/after cards use actual indexed source and structural counts; they do not claim to know the author's intent.

## Implemented

- File-level system map, drill-down to symbols, recursive file explorer, and exact-source navigation.
- Before/after evidence cards, structural changes, and snapshot identity on source.
- Passive working-tree change notice, checked every 15 seconds while visible. Updating is explicit so the view does not change during reading.
- Request invalidation for search, trace, compare, source, repository switches and comparison selectors.
- Conservative handling of catch/loop bindings, reassignment, conditional/outside-constructor bindings, deletion, static/accessor methods, nested callbacks and syntax-error files.
- Unique IDs for duplicate same-line declarations; ambiguous trace results and bounded path-search states.
- TypeScript corroboration only: it cannot introduce relationships rejected by the static resolver.
- Import, constructor-assignment and call-site supporting spans, visible as evidence links.
- Call-site multiplicity in comparison; requested pair/direction filtering and control-flow exclusions for lexical sequence evidence.
- Restored actual demo files and reproducible Git snapshots. This is a reconstructed regression fixture, not a recovered copy of the missing original demo.
- Total-source-size limits, Git blob-size checks before loading content, Windows junction filtering, repository-root validation, bounded request bodies, JSON-only mutations, cross-site fetch rejection, and browser security headers.
- Pinned patched DOMPurify; updated optional datasets dependency; setup upgrades pip and uses npm ci.
- Bounded retry when Windows sync or antivirus temporarily locks newly written index files.
- Executed benchmark report for the restored fixture, with per-category metrics and explicit lexical fallback labeling.

## Supported analysis boundary

Verified import resolution is limited to unaliased relative ES6 named imports using direct `.js` paths or a missing-`.js` fallback. Default/namespace imports, aliases, directory-index fallback, re-exports, packages and CommonJS do not create verified edges. Source extraction/search may retain unsupported code; its presence in search does not imply structural support. Class-field methods and nested callbacks are not resolved. No new JavaScript resolver was added.

Source coordinates remain one-based inclusive lines and zero-based end-exclusive UTF-8 bytes. Input text is not normalized. Repository paths use `/`.

## Honest limits

This is a single-user loopback application, not an authenticated hosted service. Audits check known advisories, not the absence of every security defect. The optional embedding model requires a separate download; validation in this environment used lexical fallback. The real-repository, manually judged 40–50-question evaluation required by the original brief remains outstanding. The bundled demo and Apps adapter results are not substitutes for that evaluation.

There is no prompt-history integration, multilingual semantic analysis, runtime debugger, or LLM explanation service. The source-change notice does not execute repository code or interrupt building. The source viewer is lazy-loaded; its Monaco bundle is still large.
