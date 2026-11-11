"""Public lexical interface: OpenSearch/Nori only, no local BM25 fallback."""
from .rag_lexical import LexicalIndex, fields


def tokenize(text):
    if not text.strip():
        return []
    index = LexicalIndex()
    try:
        return index.analyze(text)
    finally:
        index.close()


def query_tokens(query):
    if not query.strip():
        return []
    index = LexicalIndex()
    try:
        return index.query_tokens(query)
    finally:
        index.close()


def chunk_tokens(chunk):
    # Diagnostics only: production search never re-analyzes corpus text.
    return tokenize(fields(chunk))


def retrieve(query, chunks, top_k=5, *, diagnostics=None, complete_chunks=None):
    if type(top_k) is not int or not 1 <= top_k <= 1000:
        raise ValueError("top_k must be 1..1000")
    if not chunks or not query.strip():
        return []
    index = LexicalIndex()
    try:
        return index.search(query, chunks, top_k, diagnostics=diagnostics, complete_chunks=complete_chunks)
    finally:
        index.close()
