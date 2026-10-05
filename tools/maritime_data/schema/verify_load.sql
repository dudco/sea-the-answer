-- Assertions for the selected 2026-09-30-v2 dataset. Any failure aborts load.
DO $$
BEGIN
  IF (SELECT count(*) FROM maritime_data.source_files) <> 6
  OR (SELECT count(*) FROM maritime_data.vessels) <> 25252
  OR (SELECT count(*) FROM maritime_data.annual_reports) <> 80552
  OR (SELECT count(*) FROM maritime_data.synthetic_noon) <> 4380
  OR (SELECT count(*) FROM maritime_data.synthetic_voyages) <> 238
  OR (SELECT count(*) FROM maritime_data.quality_issues) <> 26249
  THEN RAISE EXCEPTION 'Dataset row counts do not match the approved preparation'; END IF;
  IF (SELECT count(*) FROM maritime_data.real_annual_query) <> 79032
  OR EXISTS (SELECT 1 FROM maritime_data.real_annual_query WHERE quality_status <> 'VALID' OR report_type = 'PARTIAL')
  THEN RAISE EXCEPTION 'Real annual query eligibility mismatch'; END IF;
  IF EXISTS (SELECT 1 FROM maritime_data.synthetic_noon n JOIN maritime_data.synthetic_voyages v USING(voyage_id) WHERE n.vessel_id <> v.vessel_id)
  THEN RAISE EXCEPTION 'Voyage vessel mismatch'; END IF;
  IF EXISTS (SELECT 1 FROM maritime_data.annual_reports a JOIN maritime_data.vessels v USING(vessel_id) JOIN maritime_data.source_files s USING(source_id) WHERE v.data_origin <> 'REAL' OR s.data_origin <> 'REAL')
  OR EXISTS (SELECT 1 FROM maritime_data.synthetic_noon n JOIN maritime_data.vessels v USING(vessel_id) JOIN maritime_data.source_files s USING(source_id) WHERE v.data_origin <> 'SYNTHETIC' OR s.data_origin <> 'SYNTHETIC')
  THEN RAISE EXCEPTION 'Real/synthetic origin mismatch'; END IF;
  IF EXISTS (SELECT 1 FROM maritime_data.quality_issues q WHERE q.record_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM maritime_data.annual_reports a WHERE a.record_id=q.record_id) AND NOT EXISTS (SELECT 1 FROM maritime_data.synthetic_noon n WHERE n.record_id=q.record_id))
  THEN RAISE EXCEPTION 'Unresolved quality issue record reference'; END IF;
END $$;
SELECT report_type, quality_status, aggregate_eligible, count(*) AS rows
FROM maritime_data.annual_reports GROUP BY 1,2,3 ORDER BY 1,2,3;
SELECT count(*) AS noon_rows, count(DISTINCT voyage_id) AS voyages,
  count(*) FILTER (WHERE distance_nm=0) AS zero_distance_rows
FROM maritime_data.development_noon_query;
