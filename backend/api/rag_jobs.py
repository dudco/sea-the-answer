"""Durable indexing outbox. No embedding or network IO in document transactions."""
from __future__ import annotations

from uuid import uuid4

from .rag_embeddings import VectorUnavailable, content_hash, contract, digest

MAX_ATTEMPTS = 5
SAFE_ERRORS = frozenset({"model_not_prepared", "model_contract_mismatch", "invalid_embedding",
                         "passage_too_long", "index_contract_mismatch"})


def fingerprint() -> str:
    return digest(contract())


def enqueue(store, document_id: str, model_fingerprint: str | None = None) -> None:
    """Use caller transaction: rollback removes the request along with the document."""
    store.run("""INSERT INTO rag_index_jobs(document_id,fingerprint) VALUES(%s,%s)
        ON CONFLICT(document_id,fingerprint) DO UPDATE SET
        generation=rag_index_jobs.generation+1,state='pending',attempts=0,
        claim_token=NULL,error_code=NULL,next_attempt_at=now(),updated_at=now()""",
        (document_id, model_fingerprint or fingerprint()))


def eligible(store, document_id: str) -> bool:
    return bool(store.one("""SELECT d.id FROM documents d
        LEFT JOIN document_meta m ON m.id=d.id WHERE d.id=%s AND d.active
        AND COALESCE(m.body->>'status','active')='active'""", (document_id,)))


def chunks(store, document_id: str) -> list[dict]:
    # Trusted offline worker may index all scopes. Retrieval still authorizes in PG.
    return store.all("""SELECT c.id,c.document_id,c.heading,c.text,p.page,d.title,d.reference
        FROM chunks c JOIN documents d ON d.id=c.document_id
        LEFT JOIN chunk_pages p ON p.id=c.id WHERE d.id=%s ORDER BY c.position""", (document_id,))


def snapshot_hash(rows: list[dict]) -> str:
    return digest([content_hash(row) for row in rows])


def retry_delay(attempts: int) -> int:
    return min(300, 5 * 2 ** min(max(attempts - 1, 0), 6))


def error_code(exc: Exception) -> str:
    return str(exc) if isinstance(exc, VectorUnavailable) and str(exc) in SAFE_ERRORS else "index_backend_failure"


def unlock(store, identity: int) -> None:
    store.one("SELECT pg_advisory_unlock(hashtextextended('haedap-rag-job:' || %s::text,0))", (identity,))


def claim(store, model_fingerprint: str) -> dict | None:
    """Dedicated session must remain open until finish; session death releases lock.

    No long-running transaction: commit processing state before model/Chroma IO.
    Lock in Python, not in a SELECT expression with LIMIT (which could lock extra rows).
    """
    rows = store.all("""SELECT id FROM rag_index_jobs WHERE fingerprint=%s
        AND (state='processing' OR (state IN ('pending','failed')
             AND attempts < %s AND next_attempt_at <= now())) ORDER BY id""",
        (model_fingerprint, MAX_ATTEMPTS))
    for row in rows:
        identity = row["id"]
        locked = store.one("SELECT pg_try_advisory_lock(hashtextextended('haedap-rag-job:' || %s::text,0)) AS locked", (identity,))
        if not locked["locked"]:
            continue
        job = store.one("""UPDATE rag_index_jobs SET state='processing',attempts=attempts+1,
            claim_token=%s,error_code=NULL,updated_at=now() WHERE id=%s AND fingerprint=%s
            AND (state='processing' OR (state IN ('pending','failed')
                 AND attempts < %s AND next_attempt_at <= now())) RETURNING *""",
            (uuid4().hex, identity, model_fingerprint, MAX_ATTEMPTS))
        if job:
            store.db.commit()
            return job
        unlock(store, identity)
    store.db.commit()
    return None


def finish(store, job: dict, state: str, code: str | None = None) -> None:
    store.run("""UPDATE rag_index_jobs SET state=%s,error_code=%s,claim_token=NULL,
        next_attempt_at=now()+(%s * interval '1 second'),updated_at=now()
        WHERE id=%s AND generation=%s AND claim_token=%s""",
        (state, code, retry_delay(job["attempts"]), job["id"], job["generation"], job["claim_token"]))
    store.db.commit()


def process_one(store, *, index_factory=None, model_fingerprint=None, batch_size=16) -> bool:
    """One committed job; caller owns a dedicated session (never a request session)."""
    from .rag_vector import VectorIndex
    fp = model_fingerprint or fingerprint()
    job = claim(store, fp)
    if job is None:
        return False
    try:
        if not eligible(store, job["document_id"]):
            finish(store, job, "cancelled")
            return True
        rows = chunks(store, job["document_id"])
        before = snapshot_hash(rows)
        store.db.commit()
        index = (index_factory or (lambda: VectorIndex(create=True)))()
        if index.fingerprint != fp:
            raise VectorUnavailable("index_contract_mismatch")
        # Small batches bound memory; stop early after superseding saves/deletions.
        for start in range(0, len(rows), batch_size):
            current = store.one("SELECT generation,claim_token FROM rag_index_jobs WHERE id=%s", (job["id"],))
            valid = current and current["generation"] == job["generation"] and current["claim_token"] == job["claim_token"]
            active = eligible(store, job["document_id"])
            store.db.commit()
            if not valid:
                return True
            if not active:
                finish(store, job, "cancelled")
                return True
            index.index(rows[start:start + batch_size], batch_size)
        # Serialize final status with document changes, without holding a lock over embedding.
        store.one("SELECT id FROM documents WHERE id=%s FOR UPDATE", (job["document_id"],))
        if not eligible(store, job["document_id"]):
            finish(store, job, "cancelled")
        elif before != snapshot_hash(chunks(store, job["document_id"])):
            finish(store, job, "failed", "document_changed")
        else:
            finish(store, job, "done")
        return True
    except Exception as exc:
        store.db.rollback()
        finish(store, job, "failed", error_code(exc))
        return True
    finally:
        unlock(store, job["id"])
        store.db.commit()
