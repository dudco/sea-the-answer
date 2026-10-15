"""Request-local BM25 retrieval over already-authorized chunks; no DB or web IO."""

from __future__ import annotations

import re
import unicodedata

from rank_bm25 import BM25Okapi


SEARCH_SYNONYMS = (
    ("fuel", "연료"), ("emission", "emissions", "배출량"),
    ("report", "보고서"), ("cii", "탄소집약도", "carbon intensity"),
    ("eca", "배출규제해역"), ("sulphur", "sulfur", "sox", "황함유량"),
    ("rating", "등급"), ("corrective", "시정", "개선"),
    ("changeover", "전환"), ("checklist", "점검표"),
)
_WORDS = re.compile(r"[a-z0-9]{2,}|[가-힣]{2,}")
_KOREAN = re.compile(r"[가-힣]{3,}\Z")
_SEARCH_FIELDS = ("title", "reference", "heading", "text")


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).lower()


def tokenize(value: str) -> list[str]:
    """Keep word frequency; supplement Korean words with overlapping bigrams.

    This is deliberately not a morphological analyzer or English stemmer.
    Search normalization never changes stored text or citation offsets.
    """
    tokens = []
    for word in _WORDS.findall(_normalize(value)):
        tokens.append(word)
        if _KOREAN.fullmatch(word):
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
    return tokens


def query_tokens(query: str) -> list[str]:
    """Actual deduplicated query tokens, including the existing expansion."""
    normalized = _normalize(query)
    words = list(dict.fromkeys(_WORDS.findall(normalized)))[:30]
    for group in SEARCH_SYNONYMS:
        # Preserve the existing bilingual expansion, including Korean suffixes.
        if any(word in normalized for word in group):
            words.extend(group)
    return list(dict.fromkeys(tokenize(" ".join(words))))


def chunk_tokens(chunk: dict) -> list[str]:
    """Tokenize exactly the fields used by BM25, retaining term frequencies."""
    return tokenize(" ".join(str(chunk.get(key) or "") for key in _SEARCH_FIELDS))


def retrieve(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """Return copies of matching chunks with a float `score`, highest first.

    Caller MUST filter scope, active revision/status and kind before calling:
    even IDF statistics must not depend on inaccessible documents. Equal scores
    retain input order. Scores may be zero/negative in small corpora and are not
    confidence probabilities. No corpus/index is cached across requests.
    """
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    terms = query_tokens(query)
    if not terms or not chunks:
        return []
    corpus = [chunk_tokens(chunk) for chunk in chunks]
    # BM25Okapi divides by vocabulary size/average length: an all-empty corpus
    # must not reach its constructor. Individual empty documents are supported.
    if not any(corpus):
        return []
    term_set = set(terms)
    matches = [i for i, tokens in enumerate(corpus) if not term_set.isdisjoint(tokens)]
    if not matches:
        return []
    scores = BM25Okapi(corpus).get_scores(terms)
    # Do not use score > 0 or get_top_n: the former loses genuine small-corpus
    # hits; the latter can include unrelated zero-score documents.
    matches.sort(key=lambda i: -float(scores[i]))
    return [{**chunks[i], "score": float(scores[i])} for i in matches[:top_k]]
