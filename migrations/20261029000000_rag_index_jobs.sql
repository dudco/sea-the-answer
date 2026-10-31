-- migrate:up
CREATE TABLE rag_index_jobs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    fingerprint text NOT NULL,
    generation bigint NOT NULL DEFAULT 1,
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending','processing','done','failed','cancelled')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    claim_token text,
    error_code text,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(document_id, fingerprint)
);
CREATE INDEX rag_index_jobs_ready ON rag_index_jobs(fingerprint, next_attempt_at, id)
    WHERE state IN ('pending','processing','failed');

-- migrate:down
DROP TABLE rag_index_jobs;
