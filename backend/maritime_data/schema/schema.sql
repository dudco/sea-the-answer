-- Maritime data v1. Does not modify the existing public app schema.

-- Review before application. Import only validated rows; this file does not load CSV.

BEGIN;

CREATE SCHEMA IF NOT EXISTS maritime_data;

CREATE TABLE maritime_data.source_files (
  source_id text PRIMARY KEY,
  dataset_id text NOT NULL,
  filename text NOT NULL,
  sha256 text NOT NULL,
  source_url text,
  data_origin text NOT NULL,
  granularity text NOT NULL,
  selection text NOT NULL,
  row_count integer NOT NULL,
  header_json jsonb NOT NULL
);

CREATE TABLE maritime_data.vessels (
  vessel_id text PRIMARY KEY,
  data_origin text NOT NULL,
  imo_number text,
  source_vessel_id text NOT NULL
);

CREATE TABLE maritime_data.synthetic_voyages (
  voyage_id text PRIMARY KEY,
  vessel_id text NOT NULL REFERENCES maritime_data.vessels(vessel_id) ON DELETE RESTRICT,
  departure_port_label text,
  arrival_port_label text,
  first_report_date date NOT NULL,
  last_report_date date NOT NULL,
  mapping_status text NOT NULL
);

CREATE TABLE maritime_data.annual_reports (
  record_id text PRIMARY KEY,
  source_id text NOT NULL REFERENCES maritime_data.source_files(source_id) ON DELETE RESTRICT,
  source_sheet text NOT NULL,
  source_row integer NOT NULL,
  vessel_id text NOT NULL REFERENCES maritime_data.vessels(vessel_id) ON DELETE RESTRICT,
  vessel_name text,
  ship_type text,
  reporting_year integer NOT NULL,
  report_type text NOT NULL,
  period_label text NOT NULL,
  period_start date,
  period_end date,
  fuel_t numeric,
  co2_t numeric,
  sea_hours numeric,
  fuel_kg_per_nm numeric,
  distance_nm_estimate numeric,
  dwt_t numeric,
  fuel_type text,
  quality_status text NOT NULL,
  aggregate_eligible boolean NOT NULL,
  provenance_json jsonb NOT NULL,
  CHECK (quality_status IN ('VALID','REVIEW','REJECT')),
  CHECK (vessel_id LIKE 'REAL:IMO:%'),
  CHECK (report_type IN ('FULL','PARTIAL','ARCHIVE_ANNUAL')),
  CHECK (NOT aggregate_eligible OR (quality_status = 'VALID' AND report_type <> 'PARTIAL')),
  CHECK (period_end >= period_start)
);

CREATE TABLE maritime_data.synthetic_noon (
  record_id text PRIMARY KEY,
  source_id text NOT NULL REFERENCES maritime_data.source_files(source_id) ON DELETE RESTRICT,
  source_row integer NOT NULL,
  vessel_id text NOT NULL REFERENCES maritime_data.vessels(vessel_id) ON DELETE RESTRICT,
  voyage_id text NOT NULL REFERENCES maritime_data.synthetic_voyages(voyage_id) ON DELETE RESTRICT,
  report_date date NOT NULL,
  period_start_utc timestamptz NOT NULL,
  observed_at_utc timestamptz NOT NULL,
  vessel_name text NOT NULL,
  ship_type text NOT NULL,
  dwt_t numeric NOT NULL,
  operating_status text NOT NULL,
  distance_nm numeric NOT NULL,
  fuel_t numeric NOT NULL,
  fuel_type text NOT NULL,
  speed_kn numeric NOT NULL,
  engine_hours numeric NOT NULL,
  quality_status text NOT NULL,
  provenance_json jsonb NOT NULL,
  CHECK (quality_status IN ('VALID','REVIEW','REJECT')),
  CHECK (vessel_id LIKE 'SYN:%'),
  CHECK (dwt_t > 0 AND distance_nm >= 0 AND fuel_t >= 0 AND speed_kn >= 0),
  CHECK (engine_hours BETWEEN 0 AND 24),
  CHECK (observed_at_utc > period_start_utc AND observed_at_utc <= period_start_utc + interval '24 hours')
);

CREATE TABLE maritime_data.quality_issues (
  issue_id integer PRIMARY KEY,
  record_id text,
  source_id text NOT NULL REFERENCES maritime_data.source_files(source_id) ON DELETE RESTRICT,
  source_row integer NOT NULL,
  severity text NOT NULL,
  field text NOT NULL,
  code text NOT NULL,
  detail text NOT NULL
);

CREATE INDEX annual_vessel_year ON maritime_data.annual_reports(vessel_id, reporting_year);

CREATE INDEX noon_vessel_date ON maritime_data.synthetic_noon(vessel_id, report_date);

CREATE INDEX noon_voyage ON maritime_data.synthetic_noon(voyage_id);

CREATE VIEW maritime_data.real_annual_query AS SELECT * FROM maritime_data.annual_reports WHERE aggregate_eligible;

CREATE VIEW maritime_data.development_noon_query AS SELECT * FROM maritime_data.synthetic_noon WHERE quality_status='VALID';

COMMIT;
