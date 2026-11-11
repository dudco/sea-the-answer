"""Derived document verification receipts, never an authorization source.

Only offline callers holding a COMPLETE document snapshot may publish receipts.
Receipt identity includes the vector collection UUID, so deleting/recreating that
collection cannot reuse a previous verification. No PostgreSQL writes are needed.
"""
from __future__ import annotations

from collections import defaultdict

from .rag_embeddings import VectorUnavailable, content_hash, digest


def documents(rows: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["document_id"]].append(row)
    return dict(grouped)


def snapshot(rows: list[dict]) -> str:
    return digest(sorted((row["id"], content_hash(row)) for row in rows))


def coverage(rows: list[dict]) -> dict:
    return {"allowed_documents": len(documents(rows)), "allowed_chunks": len(rows),
            "ready_documents": 0, "ready_chunks": 0, "excluded_documents": 0,
            "excluded_chunks": 0, "exclusion_reasons": {}, "status": "not_checked"}


class Readiness:
    def __init__(self, index):
        self.index = index
        self.name = "haedap-ready-" + index.fingerprint[:32]

    def collection(self, *, create=False):
        from chromadb.errors import NotFoundError
        if create:
            return self.index.db.get_or_create_collection(self.name, embedding_function=None)
        try:
            return self.index.db.get_collection(self.name, embedding_function=None)
        except NotFoundError:
            return None

    def descriptor(self, document_id, rows):
        return {"version": 1, "document_id": document_id, "snapshot": snapshot(rows),
                "fingerprint": self.index.fingerprint,
                "collection_id": str(self.index.collection.id), "chunks": len(rows)}

    def lookup(self, keys):
        receipts = self.collection()
        found = {}
        if receipts is not None:
            for start in range(0, len(keys), 256):
                batch = receipts.get(ids=keys[start:start + 256], include=["metadatas"])
                found.update(zip(batch["ids"], batch["metadatas"]))
        return found

    def select(self, rows, diagnostics, *, complete_chunks=None):
        grouped = documents(rows)
        complete = grouped
        if complete_chunks is not None and complete_chunks is not rows:
            # CLI --limit ranks a subset of the same authorized DB snapshot.
            # Use full documents for certification, NEVER to expand query IDs.
            complete = documents(complete_chunks)
            current = {row["id"]: content_hash(row) for identity in grouped
                       for row in complete.get(identity, [])}
            if any(current.get(row["id"]) != content_hash(row) for row in rows):
                raise VectorUnavailable("candidate_snapshot_mismatch")
        expected = {digest(meta): (identity, meta) for identity in grouped
                    for group in [complete[identity]]
                    for meta in [self.descriptor(identity, group)]}
        found = self.lookup(list(expected))
        ready = set()
        corrupt = False
        reasons = {}
        for key, (identity, meta) in expected.items():
            receipt = found.get(key)
            reason = None
            if receipt is None:
                reason = "document_unverified_or_changed"
            elif receipt == {**meta, "state": "ready"}:
                ready.add(identity)
            else:
                reason = "index_verification_failed"
                corrupt = True
            if reason:
                counts = reasons.setdefault(reason, {"documents": 0, "chunks": 0})
                counts["documents"] += 1
                counts["chunks"] += len(grouped[identity])
        selected = [row for row in rows if row["document_id"] in ready]
        diagnostics.update(ready_documents=len(ready), ready_chunks=len(selected),
                           excluded_documents=len(grouped) - len(ready),
                           excluded_chunks=len(rows) - len(selected), exclusion_reasons=reasons,
                           status="partial" if len(selected) != len(rows) else "full")
        if corrupt:
            raise VectorUnavailable("index_verification_failed")
        if not selected:
            raise VectorUnavailable("no_ready_documents")
        return selected

    def verify(self, complete_rows, *, apply=False):
        """Full offline audit; apply publishes ready OR invalid receipts, no embeddings.

        The caller must supply complete document snapshots from PostgreSQL. Batch
        index() deliberately does not call this function or publish any receipt.
        """
        found = self.index.present(complete_rows)
        records = []
        ready = failed = 0
        for identity, group in documents(complete_rows).items():
            valid = all(self.index.record_id(row) in found for row in group)
            ready += int(valid)
            failed += int(not valid)
            meta = self.descriptor(identity, group)
            records.append((digest(meta), {**meta, "state": "ready" if valid else "invalid"}))
        if apply and records:
            missing = [key for key, meta in records if meta["state"] == "invalid"]
            prior = self.lookup(missing) if missing else {}
            # Never-certified/pending input is incomplete coverage, not corruption.
            # Only retract a receipt that previously claimed this exact snapshot.
            records = [(key, meta) for key, meta in records
                       if meta["state"] == "ready" or key in prior]
            if records:
                collection = self.collection(create=True)
                for start in range(0, len(records), 256):
                    batch = records[start:start + 256]
                    # This collection is a receipt store, never a retrieval corpus.
                    collection.upsert(ids=[key for key, _ in batch],
                                      metadatas=[meta for _, meta in batch],
                                      embeddings=[[1.0] for _ in batch])
        return {"verified_documents": ready + failed, "ready_documents": ready,
                "failed_documents": failed, "checked_chunks": len(complete_rows),
                "missing_or_stale_chunks": len(complete_rows) - len(found), "applied": apply}


def complete_selection(all_rows, selected_rows):
    """Exclude partially selected documents (e.g. CLI --limit) from publication."""
    selected = {row["id"] for row in selected_rows}
    return [row for group in documents(all_rows).values()
            if all(row["id"] in selected for row in group) for row in group]
