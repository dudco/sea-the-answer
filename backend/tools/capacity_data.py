"""Shared strict capacity reference validation; no database or network writes."""
import csv
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
from io import StringIO
from pathlib import Path
import re

HEADERS = ['vessel_id','imo_number','ship','wikidata_dwt_t','wikidata_gt','name','type',
           'built','marine_dwt_t','marine_gt','ship_draught','length','beam',
           'dwt_relative_difference','capacity_status','candidate_dwt_t','candidate_gt',
           'use_restriction','wikidata_source_url','marine_vessels_source_url']

def dwt(value: str) -> Decimal | None:
    if value == '':
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError('Invalid reference DWT') from None
    if not number.is_finite() or not 0 < number < 10000000:
        raise ValueError('Reference DWT must be positive and finite')
    return number

def prepared_references(path: Path) -> tuple[list[dict], str]:
    """Read once: the exact hashed bytes are the only data subsequently inserted."""
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Reference CSV exceeds 64 MiB')
    with path.open('rb') as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError('Reference CSV exceeds 64 MiB')
    reader = csv.DictReader(StringIO(raw.decode('utf-8-sig'), newline=''))
    if reader.fieldnames != HEADERS:
        raise ValueError('Unexpected capacity reference CSV header')
    digest = hashlib.sha256(raw).hexdigest()
    rows, seen = [], set()
    with localcontext() as ctx:
        ctx.prec = 50
        for source_row, record in enumerate(reader, 2):
            if len(rows) >= 250000 or None in record or any(v is None for v in record.values()):
                raise ValueError('Reference CSV row width/count mismatch')
            imo = record['imo_number']
            vessel = record['vessel_id']
            if not re.fullmatch(r'[0-9]{7}', imo) or vessel != 'REAL:IMO:' + imo or vessel in seen:
                raise ValueError('Invalid or duplicate REAL reference identity')
            seen.add(vessel)
            wiki, marine, candidate = (dwt(record[k]) for k in
                                      ('wikidata_dwt_t','marine_dwt_t','candidate_dwt_t'))
            expected = wiki if wiki is not None else marine
            if candidate != expected:
                raise ValueError('Candidate DWT does not match declared source')
            status = 'UNAVAILABLE'
            if wiki is not None and marine is not None:
                difference = abs(wiki - marine) / max(wiki, marine)
                status = 'CONFLICT_OVER_5_PERCENT' if difference > Decimal('.05') else 'AGREE_WITHIN_5_PERCENT'
            elif wiki is not None:
                status = 'WIKIDATA_ONLY'
            elif marine is not None:
                status = 'MARINE_VESSELS_ONLY'
            if record['capacity_status'] != status:
                raise ValueError('Reference source agreement status is inconsistent')
            if record['use_restriction'] != 'REFERENCE_ONLY_NOT_STATUTORY_VERIFIED':
                raise ValueError('Statutory verification must not be inferred')
            if (record['wikidata_source_url'] != 'https://www.wikidata.org/'
                    or record['marine_vessels_source_url'] != 'https://github.com/rich-iannone/MarineVessels'):
                raise ValueError('Unknown capacity reference source')
            rows.append({'vessel_id':vessel, 'imo_number':imo, 'candidate_dwt_t':candidate,
                         'capacity_status':status, 'source_file_sha256':digest,
                         'source_filename':path.name, 'source_row':source_row, 'source_json':record})
    if not rows:
        raise ValueError('Reference CSV is empty')
    return rows, digest
