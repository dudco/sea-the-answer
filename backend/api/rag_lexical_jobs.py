"""Independent lexical outbox. Each processor owns a dedicated PG session."""
from uuid import uuid4

from .rag_jobs import chunks, eligible, retry_delay, snapshot_hash
from .rag_lexical import LexicalIndex, LexicalUnavailable, fingerprint, record_id, receipt_id


def enqueue(store, document_id):
    store.run("SELECT rag_lexical_enqueue(%s)", (document_id,))


def lock(store, document_id, release=False):
    fn = "pg_advisory_unlock" if release else "pg_try_advisory_lock"
    return store.one(f"SELECT {fn}(hashtextextended('haedap-lexical:' || %s,0)) AS locked",
                     (document_id,))["locked"]


def claim(store, document_id=None):
    candidates = store.all("""SELECT document_id FROM rag_lexical_jobs
        WHERE (%s::text IS NULL OR document_id=%s) AND (state='processing' OR
          (state IN ('pending','failed') AND attempts<5 AND next_attempt_at<=now()))
        ORDER BY updated_at,document_id""", (document_id, document_id))
    for item in candidates:
        doc = item["document_id"]
        if not lock(store, doc):
            continue
        job = store.one("""UPDATE rag_lexical_jobs SET state='processing',attempts=attempts+1,
            claim_token=%s,error_code=NULL,updated_at=now()
            WHERE document_id=%s AND (state='processing' OR
              (state IN ('pending','failed') AND attempts<5 AND next_attempt_at<=now())) RETURNING *""",
            (uuid4().hex, doc))
        if job:
            store.db.commit()
            return job
        lock(store, doc, True)
    store.db.commit()
    return None


def finish(store, job, state, reason=None):
    store.run("""UPDATE rag_lexical_jobs SET state=%s,error_code=%s,fingerprint=%s,
        claim_token=NULL,next_attempt_at=now()+(%s * interval '1 second'),updated_at=now()
        WHERE document_id=%s AND generation=%s AND claim_token=%s""",
        (state, reason, fingerprint(), retry_delay(job["attempts"]),
         job["document_id"], job["generation"], job["claim_token"]))
    store.db.commit()


def process_one(store, *, index_factory=LexicalIndex, document_id=None, batch_size=100, limit=None):
    """Both automatic worker and explicit CLI use this fenced publication path.

    Remote writes are immutable IDs until final publication. The advisory lock
    spans commits, excluding duplicate workers/CLI for the same document.
    """
    job = claim(store, document_id)
    if job is None:
        return False
    index = None
    try:
        doc = job["document_id"]
        rows = chunks(store, doc) if eligible(store, doc) else []
        before = snapshot_hash(rows)
        store.db.commit()
        index = index_factory()
        index.create()
        subset = rows[:limit] if limit else rows
        for start in range(0, len(subset), batch_size):
            current = store.one("SELECT generation,claim_token FROM rag_lexical_jobs WHERE document_id=%s", (doc,))
            store.db.commit()
            if not current or (current["generation"], current["claim_token"]) != (job["generation"], job["claim_token"]):
                return True
            index.index(subset[start:start+batch_size], batch_size)
        # Match application lock order (document then outbox). Content writes
        # which only hold chunk/meta locks still advance the job before commit.
        store.one("SELECT id FROM documents WHERE id=%s FOR UPDATE", (doc,))
        current_rows = chunks(store, doc) if eligible(store, doc) else []
        current = store.one("SELECT generation,claim_token FROM rag_lexical_jobs WHERE document_id=%s FOR UPDATE", (doc,))
        if not current or (current["generation"], current["claim_token"]) != (job["generation"], job["claim_token"]):
            store.db.commit()
            return True
        if snapshot_hash(current_rows) != before:
            finish(store, job, "failed", "document_changed")
        elif len(subset) != len(rows):
            finish(store, job, "failed", "partial_index")
        else:
            verified = index.verify(rows, publish=True)
            if verified["missing_chunks"]:
                raise LexicalUnavailable("lexical_verification_failed")
            keep = [record_id(r) for r in rows] + ([receipt_id(rows)] if rows else [])
            index.purge(doc, keep)
            finish(store, job, "done")
        return True
    except Exception as exc:
        store.db.rollback()
        safe = {"lexical_contract_mismatch", "lexical_verification_failed", "lexical_bulk_failure"}
        reason = str(exc) if isinstance(exc, LexicalUnavailable) and str(exc) in safe else "lexical_backend_failure"
        finish(store, job, "failed", reason)
        return True
    finally:
        if index is not None:
            index.close()
        lock(store, job["document_id"], True)
        store.db.commit()
