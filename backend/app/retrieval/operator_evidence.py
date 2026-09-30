"""Small, opt-in code-operator evidence for dense candidate reranking.

E019 evaluates this on the frozen DEV split. The production retriever does not
enable it unless the experiment clears the benchmark gates.
"""

import re

import numpy as np


QUERY_PATTERNS = {
    "xor": r"\b(?:xor|exclusive\s+or)\b",
    "gcd": r"\b(?:gcd|greatest\s+common\s+divisor)\b",
    "lcm": r"\b(?:lcm|least\s+common\s+multiple)\b",
    "modulo": r"\b(?:modulo|modulus|remainder)\b",
    "sort": r"\b(?:sort|sorted|sorting)\b",
    "binary_search": r"\bbinary\s+search\b",
    "factorial": r"\bfactorial\b",
    "prime": r"\bprime\s+numbers?\b|\bprimality\b",
    "palindrome": r"\bpalindrom(?:e|ic)\b",
}

CODE_PATTERNS = {
    "xor": r"\^|\bxor\b",
    "gcd": r"\bgcd\b|\b__gcd\b",
    "lcm": r"\blcm\b",
    "modulo": r"%|\bmod\b",
    "sort": r"\.sort\s*\(|\bsorted\s*\(|\bsort\s*\(",
    "binary_search": r"\bbisect\b|\blower_bound\b|\bupper_bound\b|\bbinary_search\b",
    "factorial": r"\bfactorial\b|\bfact\b",
    "prime": r"\b(?:prime|is_prime|isprime|sieve)\b",
    "palindrome": r"\bpalindrom\w*\b|\[\s*::\s*-1\s*\]",
}


def rerank_operator_evidence(query: str, doc_ids: list[str], corpus: dict[str, str],
                             dense_scores: np.ndarray, *, depth: int = 50,
                             boost: float = 0.02) -> np.ndarray:
    """Boost explicit operator matches within the dense top ``depth`` only."""
    active = [name for name, pattern in QUERY_PATTERNS.items() if re.search(pattern, query, re.I)]
    scores = np.array(dense_scores, dtype=np.float64, copy=True)
    if not active:
        return scores
    top = np.argsort(-scores, kind="stable")[:depth]
    for i in top:
        text = corpus[doc_ids[i]]
        if any(re.search(CODE_PATTERNS[name], text, re.I) for name in active):
            scores[i] += boost
    return scores
