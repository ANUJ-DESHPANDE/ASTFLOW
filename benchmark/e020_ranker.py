"""Experimental E020 top-50 feature ranker. Never wired into production."""

import keyword
import math
import re

import numpy as np

NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
WORD = re.compile(r"[A-Za-z]+|\d+")
SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[_\W]+")
OPERATORS = ("xor", "gcd", "lcm", "modulo", "sort", "binary", "factorial", "prime", "palindrome")
FEATURES = ("dense", "word_overlap", "rare_overlap", "identifier_overlap", "number_overlap",
            "operator_overlap", "document_log_tokens")


def normalize_identifier(value):
    return tuple(w.lower() for w in SPLIT.split(value) if w)


def terms(value):
    out = set()
    for item in NAME.findall(value or ""):
        out.update(normalize_identifier(item))
    return out


def features(query, document, dense, idf):
    if not math.isfinite(float(dense)):
        raise ValueError("dense score must be finite")
    q = terms(query)
    d = terms(document)
    shared = q & d
    names = {x.lower() for x in NAME.findall(document or "") if ("_" in x or any(c.isupper() for c in x)) and not keyword.iskeyword(x)}
    qnames = {x.lower() for x in NAME.findall(query or "")}
    qnums = set(re.findall(r"\b\d{2,}\b", query or ""))
    dnums = set(re.findall(r"\b\d{2,}\b", document or ""))
    return np.array((float(dense), len(shared) / max(1, len(q)),
                     sum(idf.get(w, 0.0) for w in shared) / max(1.0, sum(idf.get(w, 0.0) for w in q)),
                     len(names & qnames) / max(1, len(qnames)),
                     len(qnums & dnums) / max(1, len(qnums)),
                     len(set(OPERATORS) & q & d) / max(1, len(set(OPERATORS) & q)),
                     math.log1p(len(WORD.findall(document or "")))), dtype=np.float64)


def rank_top50(query, ids, corpus, dense, idf, mean, scale, coef, depth=50):
    dense = np.asarray(dense, dtype=np.float64)
    assert len(ids) == len(dense) and len(set(ids)) == len(ids)
    assert len(mean) == len(scale) == len(coef) == len(FEATURES)
    if not np.isfinite(dense).all():
        raise ValueError("non-finite dense scores")
    top = np.argsort(-dense, kind="stable")[:depth]
    values = np.array([features(query, corpus.get(ids[i], ""), dense[i], idf) for i in top])
    scores = ((values - mean) / scale) @ coef
    if not np.isfinite(scores).all():
        raise ValueError("non-finite rerank scores")
    order = np.argsort(-scores, kind="stable")
    chosen = set(top)
    result = top[order].tolist() + [i for i in np.argsort(-dense, kind="stable") if i not in chosen]
    assert len(result) == len(ids) and len(set(result)) == len(ids)
    return result
