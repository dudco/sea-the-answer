"""Preview or atomically load the separate, non-statutory capacity reference CSV."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re

from dotenv import load_dotenv
import psycopg
from psycopg.types.json import Jsonb

try:
    from tools.capacity_data import HEADERS, dwt, prepared_references
except ModuleNotFoundError as exc:
    if exc.name not in ('tools','tools.capacity_data'):raise
    from backend.tools.capacity_data import HEADERS, dwt, prepared_references

MIGRATION = '20261013020000'









def load_references(dsn: str, path: Path, *, apply: bool = False) -> dict:
    rows, digest = prepared_references(path)
    result = {'mode':'preview', 'rows':len(rows), 'with_dwt':sum(r['candidate_dwt_t'] is not None for r in rows),
              'conflicts':sum(r['capacity_status']=='CONFLICT_OVER_5_PERCENT' for r in rows),
              'source_file_sha256':digest, 'reference_only':True}
    if not apply:
        return result
    if not dsn:
        raise ValueError('DATABASE_URL is required')
    with psycopg.connect(dsn.replace('postgresql+psycopg://','postgresql://',1), connect_timeout=5) as db:
        db.execute("SET LOCAL lock_timeout='5s'")
        db.execute("SET LOCAL statement_timeout='120s'")
        if db.execute("SELECT to_regclass('public.schema_migrations')").fetchone()[0] is None:
            raise ValueError('Apply capacity dbmate migration first')
        if not db.execute('SELECT 1 FROM public.schema_migrations WHERE version=%s',(MIGRATION,)).fetchone():
            raise ValueError('Apply capacity dbmate migration first')
        db.execute('LOCK TABLE maritime_data.vessels IN SHARE MODE')
        db.execute('LOCK TABLE maritime_data.capacity_candidates IN ACCESS EXCLUSIVE MODE')
        if db.execute('SELECT EXISTS (SELECT FROM maritime_data.capacity_candidates)').fetchone()[0]:
            raise ValueError('Capacity references are not empty; refusing overwrite')
        real = dict(db.execute("SELECT vessel_id,imo_number FROM maritime_data.vessels WHERE data_origin='REAL'").fetchall())
        if any(real.get(r['vessel_id']) != r['imo_number'] for r in rows):
            raise ValueError('Reference identity is not an existing REAL vessel')
        with db.cursor().copy('''COPY maritime_data.capacity_candidates
             (vessel_id,imo_number,candidate_dwt_t,capacity_status,source_file_sha256,
              source_filename,source_row,source_json) FROM STDIN''') as copy:
            for r in rows:
                copy.write_row(tuple(Jsonb(r[k]) if k=='source_json' else r[k] for k in
                               ('vessel_id','imo_number','candidate_dwt_t','capacity_status',
                                'source_file_sha256','source_filename','source_row','source_json')))
        if db.execute('SELECT count(*) FROM maritime_data.capacity_candidates').fetchone()[0] != len(rows):
            raise ValueError('Loaded reference row count mismatch')
    return {**result, 'mode':'loaded'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,default=Path(__file__).resolve().parents[1]/'.env')
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    load_dotenv(args.env_file,override=False)
    try:
        print(json.dumps(load_references(os.getenv('DATABASE_URL',''),args.csv,apply=args.apply)))
    except (ValueError, OSError, UnicodeError, csv.Error, psycopg.Error):
        raise SystemExit('Capacity load failed. Check CSV, migration, REAL identities and empty reference table; no source data was overwritten.') from None


if __name__ == '__main__':
    main()
