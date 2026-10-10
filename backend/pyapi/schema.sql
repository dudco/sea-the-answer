-- PostgreSQL schema for the existing API. Apply to an empty database only.
-- JSONB keeps document, vessel and report payloads from the current API.
CREATE TABLE IF NOT EXISTS documents (
    id text PRIMARY KEY, logical_id text NOT NULL, hash text NOT NULL,
    title text NOT NULL, kind text NOT NULL, url text,
    reference text NOT NULL, version text NOT NULL, reviewed_at text NOT NULL,
    language text NOT NULL, active boolean NOT NULL DEFAULT true,
    imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS documents_one_active_revision
    ON documents(logical_id) WHERE active;
CREATE TABLE IF NOT EXISTS chunks (
    id text PRIMARY KEY, document_id text NOT NULL REFERENCES documents(id),
    position integer NOT NULL, heading text NOT NULL, text text NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_document_position_idx ON chunks(document_id, position);
CREATE TABLE IF NOT EXISTS document_meta (id text PRIMARY KEY REFERENCES documents(id), body jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS document_files (id text PRIMARY KEY REFERENCES documents(id), name text NOT NULL, base64 text NOT NULL);
CREATE TABLE IF NOT EXISTS chunk_pages (id text PRIMARY KEY REFERENCES chunks(id), page integer);

CREATE TABLE IF NOT EXISTS ships (id text PRIMARY KEY, body jsonb NOT NULL, version integer NOT NULL);
CREATE TABLE IF NOT EXISTS operations (
    id text PRIMARY KEY, ship text NOT NULL REFERENCES ships(id), date date NOT NULL,
    body jsonb NOT NULL, version integer NOT NULL, UNIQUE(ship,date)
);
CREATE INDEX IF NOT EXISTS operations_ship_date_idx ON operations(ship,date);

CREATE TABLE IF NOT EXISTS users (
    id text PRIMARY KEY, username text NOT NULL UNIQUE, name text NOT NULL,
    role text NOT NULL, password text NOT NULL, active boolean NOT NULL,
    version integer NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id text PRIMARY KEY, title text NOT NULL, type text NOT NULL, text text NOT NULL,
    sources jsonb NOT NULL, version integer NOT NULL, updated_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS report_meta (
    id text PRIMARY KEY REFERENCES reports(id), owner text NOT NULL,
    status text NOT NULL, body jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_runs (
    id text PRIMARY KEY, tool text NOT NULL, version text NOT NULL,
    input jsonb NOT NULL, output jsonb NOT NULL, created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS queries (
    id text PRIMARY KEY, question text NOT NULL, response jsonb NOT NULL,
    created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS query_owner (
    id text PRIMARY KEY REFERENCES queries(id), owner text NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id text PRIMARY KEY, at timestamptz NOT NULL, actor text NOT NULL,
    category text NOT NULL, action text NOT NULL, target text NOT NULL,
    detail jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS changes (
    id text PRIMARY KEY, at timestamptz NOT NULL, actor text NOT NULL,
    kind text NOT NULL, payload jsonb NOT NULL, status text NOT NULL,
    reviewer text, reviewed_at timestamptz, note text
);
CREATE TABLE IF NOT EXISTS settings (key text PRIMARY KEY, value text NOT NULL);
