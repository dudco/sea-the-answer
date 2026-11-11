-- migrate:up
-- Independent durable lexical outbox. No FK: a physical delete must leave a
-- tombstone job. Repeated mutations in one transaction coalesce per document.
CREATE TABLE rag_lexical_jobs (
    document_id text PRIMARY KEY,
    generation bigint NOT NULL DEFAULT 1,
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processing','done','failed')),
    attempts integer NOT NULL DEFAULT 0,
    claim_token text,
    fingerprint text,
    error_code text,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    source_txid bigint NOT NULL DEFAULT txid_current()
);
CREATE INDEX rag_lexical_jobs_pending ON rag_lexical_jobs(state,next_attempt_at);

CREATE FUNCTION rag_lexical_enqueue(doc text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF doc IS NULL THEN RETURN; END IF;
    INSERT INTO rag_lexical_jobs(document_id) VALUES(doc)
    ON CONFLICT(document_id) DO UPDATE SET
        generation=rag_lexical_jobs.generation + CASE WHEN rag_lexical_jobs.source_txid=txid_current() THEN 0 ELSE 1 END,
        state='pending',attempts=0,claim_token=NULL,error_code=NULL,
        next_attempt_at=now(),updated_at=now(),source_txid=txid_current();
END $$;

CREATE FUNCTION rag_lexical_changed() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_doc text; new_doc text;
BEGIN
    IF TG_TABLE_NAME='chunks' THEN
        IF TG_OP <> 'INSERT' THEN old_doc := OLD.document_id; END IF;
        IF TG_OP <> 'DELETE' THEN new_doc := NEW.document_id; END IF;
    ELSIF TG_TABLE_NAME='chunk_pages' THEN
        IF TG_OP <> 'INSERT' THEN SELECT document_id INTO old_doc FROM chunks WHERE id=OLD.id; END IF;
        IF TG_OP <> 'DELETE' THEN SELECT document_id INTO new_doc FROM chunks WHERE id=NEW.id; END IF;
    ELSE
        IF TG_OP <> 'INSERT' THEN old_doc := OLD.id; END IF;
        IF TG_OP <> 'DELETE' THEN new_doc := NEW.id; END IF;
    END IF;
    PERFORM rag_lexical_enqueue(old_doc);
    IF new_doc IS DISTINCT FROM old_doc THEN PERFORM rag_lexical_enqueue(new_doc); END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER rag_lexical_documents AFTER INSERT OR UPDATE OR DELETE ON documents
    FOR EACH ROW EXECUTE FUNCTION rag_lexical_changed();
CREATE TRIGGER rag_lexical_metadata AFTER INSERT OR UPDATE OR DELETE ON document_meta
    FOR EACH ROW EXECUTE FUNCTION rag_lexical_changed();
CREATE TRIGGER rag_lexical_chunks AFTER INSERT OR UPDATE OR DELETE ON chunks
    FOR EACH ROW EXECUTE FUNCTION rag_lexical_changed();
CREATE TRIGGER rag_lexical_pages AFTER INSERT OR UPDATE OR DELETE ON chunk_pages
    FOR EACH ROW EXECUTE FUNCTION rag_lexical_changed();

-- migrate:down
DROP TRIGGER rag_lexical_pages ON chunk_pages;
DROP TRIGGER rag_lexical_chunks ON chunks;
DROP TRIGGER rag_lexical_metadata ON document_meta;
DROP TRIGGER rag_lexical_documents ON documents;
DROP FUNCTION rag_lexical_changed();
DROP FUNCTION rag_lexical_enqueue(text);
DROP TABLE rag_lexical_jobs;
