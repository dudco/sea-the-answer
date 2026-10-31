"""Rebuildable Chroma index. PostgreSQL-authorized candidates are mandatory."""
from __future__ import annotations

import os
from pathlib import Path

from .rag_embeddings import (VectorUnavailable, content_hash, contract, digest, embedder, passage)


def client(*, create=False):
    import chromadb
    from chromadb.config import Settings
    settings = Settings(anonymized_telemetry=False)
    host = os.getenv("HAEDAP_CHROMA_HOST")
    if host:
        return chromadb.HttpClient(host=host, port=int(os.getenv("HAEDAP_CHROMA_PORT", "8000")),
                                   settings=settings)
    path = Path(os.getenv("HAEDAP_CHROMA_PATH", ".rag-vectors"))
    if not create and not (path / "chroma.sqlite3").is_file():
        raise VectorUnavailable("index_not_ready")
    return chromadb.PersistentClient(path=str(path), settings=settings)


class VectorIndex:
    def __init__(self, *, create: bool = False, db=None, encoder=None, model_contract=None):
        self.contract = model_contract or contract()
        self.fingerprint = digest(self.contract)
        self.encoder = encoder
        db = db if db is not None else client(create=create)
        name = "haedap-" + self.fingerprint[:32]
        metadata = {"fingerprint": self.fingerprint, "contract": str(self.contract)}
        if create:
            self.collection = db.get_or_create_collection(name, metadata=metadata,
                configuration={"hnsw": {"space": "cosine"}}, embedding_function=None)
        else:
            try:
                self.collection = db.get_collection(name, embedding_function=None)
            except Exception:
                raise VectorUnavailable("index_not_ready") from None
        if (self.collection.metadata or {}).get("fingerprint") != self.fingerprint:
            raise VectorUnavailable("index_contract_mismatch")

    def record_id(self, chunk: dict) -> str:
        return digest([chunk["id"], content_hash(chunk), self.fingerprint])

    def metadata(self, chunk: dict) -> dict:
        return {"chunk_id": chunk["id"], "document_id": chunk["document_id"],
                "title": chunk.get("title") or "", "heading": chunk.get("heading") or "",
                "page": chunk.get("page") if chunk.get("page") is not None else -1,
                "content_hash": content_hash(chunk), "fingerprint": self.fingerprint,
                "embedding_input_hash": self.input_hash(chunk)}

    def input_hash(self, chunk: dict) -> str:
        # IDs/pages/version/scope do not enter E5; keep their record metadata separate.
        return digest([self.fingerprint, passage(chunk)])

    def present(self, chunks: list[dict]) -> set[str]:
        expected = {self.record_id(row): self.metadata(row) for row in chunks}
        ids = list(expected)
        found = set()
        for start in range(0, len(ids), 256):
            result = self.collection.get(ids=ids[start:start + 256], include=["metadatas"])
            for identity, meta in zip(result["ids"], result["metadatas"]):
                # Earlier indices have no input hash. Their original complete metadata
                # is still valid; input-based reuse is available for new records only.
                legacy = {k: v for k, v in expected.get(identity, {}).items() if k != "embedding_input_hash"}
                if identity in expected and (meta == expected[identity] or meta == legacy):
                    found.add(identity)
        return found

    def reusable_vectors(self, chunks: list[dict]) -> dict:
        keys = list({self.input_hash(row) for row in chunks})
        if not keys:
            return {}
        result = self.collection.get(where={"embedding_input_hash": {"$in": keys}},
                                     include=["metadatas", "embeddings"], limit=256)
        found = {}
        for meta, vector in zip(result["metadatas"], result["embeddings"]):
            if meta.get("fingerprint") == self.fingerprint and meta.get("embedding_input_hash") in keys:
                found.setdefault(meta["embedding_input_hash"], vector)
        return found

    def index(self, chunks: list[dict], batch_size: int = 16) -> dict:
        if type(batch_size) is not int or not 1 <= batch_size <= 256:
            raise ValueError("batch_size must be between 1 and 256")
        existing = self.present(chunks)
        missing = list({self.record_id(row): row for row in chunks
                        if self.record_id(row) not in existing}.values())
        count = 0
        for start in range(0, len(missing), batch_size):
            batch = missing[start:start + batch_size]
            reusable = self.reusable_vectors(batch)
            unique = {self.input_hash(row): row for row in batch if self.input_hash(row) not in reusable}
            if unique:
                encoded = (self.encoder or embedder()).documents(list(unique.values()), batch_size=batch_size)
                reusable.update(zip(unique, encoded))
            # Chroma get() returns ndarrays while the encoder returns lists.
            # Normalize every vector, independent of batch order, before upsert.
            vectors = [[float(value) for value in reusable[self.input_hash(row)]] for row in batch]
            self.collection.upsert(ids=[self.record_id(row) for row in batch],
                                   embeddings=vectors, metadatas=[self.metadata(row) for row in batch])
            count += len(batch)
        return {"requested": len(chunks), "indexed": count, "already_current": len(existing)}

    def search(self, query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
        if type(top_k) is not int or top_k < 1:
            raise ValueError("top_k must be positive")
        if not chunks or not query.strip():
            return []
        allowed = {self.record_id(row): row for row in chunks}
        if self.present(chunks) != set(allowed):
            raise VectorUnavailable("index_incomplete_or_stale")
        vector = (self.encoder or embedder()).query(query)
        # Restrict BEFORE ranking, never global top-k followed by scope filtering.
        result = self.collection.query(query_embeddings=[vector], ids=list(allowed),
            n_results=min(top_k, len(allowed)), include=["distances"])
        rows = []
        for identity, distance in zip(result["ids"][0], result["distances"][0]):
            if identity not in allowed:
                raise VectorUnavailable("index_scope_mismatch")
            rows.append({**allowed[identity], "score": 1.0 - float(distance)})
        positions = {row["id"]: i for i, row in enumerate(chunks)}
        return sorted(rows, key=lambda row: (-row["score"], positions[row["id"]]))
