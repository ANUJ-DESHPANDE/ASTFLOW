"""Retrieval-independent evaluation layer: frozen runs in, cross-checked metrics out.

Nothing in this package ranks documents. It consumes rankings produced elsewhere,
freezes them to TREC files, and scores the same bytes with several independent
evaluators so no single implementation is trusted on its own.
"""
