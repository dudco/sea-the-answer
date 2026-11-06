"""Capture and validate historical registry / regional observations; never admission inputs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from backend.tools.navigation_context import STATIONS, ReferencePeriod, static_summary
from backend.tools.navigation_references import NavigationCatalog, catalog_summary
from scripts.prepare_navigation_references import digest, dump

LIMIT = 8 * 1024 * 1024
STATIC = 'https://kystdatahuset.no/ws/api/ais/static-messages'
SCHEMA = 'https://kystdatahuset.no/ws/swagger/v1/swagger.json'
STATION_BASES = {key: f'https://opendata-download-{"ocobs" if key == "smhi_water_gothenburg" else "metobs"}.smhi.se/api/version/1.0/parameter/{row[1]}/station/{row[0]}'
                 for key, row in STATIONS.items()}
URLS = {'schema_no_static': SCHEMA}
for _key, _base in STATION_BASES.items():
    URLS[_key] = _base + '/period/latest-hour/data.json'
    URLS[_key + '_metadata'] = _base + '.json'
URLS['smhi_water_datum'] = STATION_BASES['smhi_water_gothenburg'] + '/period/latest-hour/data.csv'
ROUTE_BASE = 'https://a3cloud.kystverket.no/api/kystverket/routeinfo/v2/routes'
ROUTE_URLS = [ROUTE_BASE+'/list', *[ROUTE_BASE+'/list/'+loc for loc in ('SEGOT','FIHEL','DKAAL','NOBGO')]]


def period_for(now):
    end = now.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = end.replace(year=end.year-1, month=12) if end.month == 1 else end.replace(month=end.month-1)
    return ReferencePeriod(start=start, end=end)


def bindings(catalog):
    by_mmsi = defaultdict(set)
    for row in catalog.observations:
        if row.source_ref.source_id == 'ais_no' and row.mmsi and 'AIS_IDENTITY_AMBIGUOUS' not in row.issues:
            by_mmsi[row.mmsi].add(row.imo_number)
    if any(len(values) != 1 for values in by_mmsi.values()):
        raise ValueError('Conflicting baseline identity')
    return {key: next(iter(values)) for key, values in by_mmsi.items()}


def static_url(catalog, period):
    ids = bindings(catalog)
    if not ids or len(ids) > 500:
        raise ValueError('Reviewed bounded request requires 1–500 baseline MMSIs')
    query = [('start', period.start.isoformat()), ('end', period.end.isoformat()), ('limit', '10000')]
    url = STATIC + '?' + urllib.parse.urlencode(query + [('mmsi', m) for m in sorted(ids)])
    if len(url) > 8000:
        raise ValueError('Request exceeds the reviewed URL budget')
    return url


class SameOriginTLSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        old, new = urllib.parse.urlsplit(request.full_url), urllib.parse.urlsplit(new_url)
        if new.scheme != 'https' or new.netloc.casefold() != old.netloc.casefold():
            raise ValueError('Unreviewed source redirect; HTTPS and origin must be retained')
        return super().redirect_request(request, response, code, message, headers, new_url)


def download(url, target, *, allowed_urls=()):
    """TLS stays enabled. Windows fallback uses its normal system certificate trust."""
    if url not in allowed_urls and url not in URLS.values() and url not in ROUTE_URLS and not re.fullmatch(re.escape(ROUTE_BASE)+r'/NO-[0-9]{6}/download',url) and not url.startswith(STATIC + '?'):
        raise ValueError('Only reviewed public endpoints are supported')
    started = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'SEA-THE-ANSWER-capstone/1.0'})
        with urllib.request.build_opener(SameOriginTLSRedirect()).open(req, timeout=20) as response:
            data = bytearray()
            while chunk := response.read1(65536):
                data.extend(chunk)
                if len(data) > LIMIT or time.monotonic() - started > 90:
                    raise ValueError('Source size/time budget exceeded')
        target.write_bytes(data)
    except urllib.error.URLError as exc:
        if os.name != 'nt' or not isinstance(exc.reason, ssl.SSLCertVerificationError) or (url not in URLS.values() and url not in allowed_urls):
            raise
        # No custom certificate callback, redirect, shell interpolation or HTTP downgrade.
        script = r'''
$ErrorActionPreference='Stop'
$request=[System.Net.HttpWebRequest]::Create($env:HAEDAP_SOURCE_URL)
$request.AllowAutoRedirect=$false
$request.Timeout=20000
$request.ReadWriteTimeout=20000
$response=$request.GetResponse()
try {
  $stream=$response.GetResponseStream(); $memory=New-Object System.IO.MemoryStream
  try {
    $buffer=New-Object byte[] 65536; $clock=[Diagnostics.Stopwatch]::StartNew()
    while (($count=$stream.Read($buffer,0,$buffer.Length)) -gt 0) {
      if ($memory.Length+$count -gt 8388608 -or $clock.Elapsed.TotalSeconds -gt 90) {throw 'Source budget exceeded'}
      $memory.Write($buffer,0,$count)
    }
    [IO.File]::WriteAllBytes($env:HAEDAP_SOURCE_FILE,$memory.ToArray())
  } finally {$memory.Dispose(); $stream.Dispose()}
} finally {$response.Dispose()}
'''
        env = {**os.environ, 'HAEDAP_SOURCE_URL': url, 'HAEDAP_SOURCE_FILE': str(target.resolve())}
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], env=env,
                       check=True, timeout=100, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if not target.is_file() or not 0 < target.stat().st_size <= LIMIT:
        raise ValueError('Source size budget exceeded')


def fetch(base, directory):
    catalog = NavigationCatalog.model_validate_json(base.read_bytes())
    if catalog.version != 'NAVIGATION-REFERENCES-1.2':
        raise ValueError('A preserved 1.2 baseline is required')
    period = period_for(datetime.now(timezone.utc))
    request_url = static_url(catalog, period)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {'base_sha256': digest(base.read_bytes()), 'period': period.model_dump(mode='json'), 'sources': {}}
    for key, url in {'norway_static': request_url, **URLS}.items():
        filename = key + ('.csv' if key == 'smhi_water_datum' else '.json')
        row = {'url': STATIC if key == 'norway_static' else url, 'request_url': url, 'filename': filename}
        try:
            download(url, directory / filename)
            data = (directory / filename).read_bytes()
            row.update(status='captured', sha256=digest(data), bytes=len(data), retrieved_at=datetime.now(timezone.utc).isoformat())
        except (OSError, ValueError, subprocess.SubprocessError):
            row.update(status='failed', reason='Source unavailable or size/time limit; TLS validation retained')
        manifest['sources'][key] = row
        dump(directory / 'manifest.json', manifest)
    if any(r['status'] != 'captured' for r in manifest['sources'].values()):
        raise ValueError('Required source failed; see manifest. No existing catalog replaced.')
    return manifest


def registry_records(payload, ids):
    rows = payload.get('data')
    if payload.get('success') is not True or not isinstance(rows, list) or len(rows) >= 10000:
        raise ValueError('Registry response failed or may have been truncated')
    result = []
    for index, row in enumerate(rows):
        mmsi = str(row.get('mmsi', ''))
        if mmsi not in ids:
            raise ValueError('Registry returned an MMSI outside the explicit request')
        imo, issues = ids[mmsi], []
        registered = str(row['imoNumber']) if row.get('imoNumber') is not None else None
        if registered != imo:
            issues.append('REGISTRY_IDENTITY_MISMATCH')
        def dimension(a, b, maximum, axis):
            values = [row.get(a), row.get(b)]
            if not all(type(v) is int and 0 < v < maximum for v in values):
                issues.append('REGISTRY_' + axis + '_MISSING')
                return None
            return str(sum(values))
        def stamp(key):
            if row.get(key) is None:
                return None
            try:
                value = datetime.fromisoformat(row[key])
                return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
            except (ValueError, TypeError):
                issues.append('REGISTRY_TIME_INVALID')
                return None
        try:
            draft = Decimal(str(row.get('draught')))
            draft = str(draft) if draft.is_finite() and 0 < draft < 50 else None
        except InvalidOperation:
            draft = None
        result.append({'vessel_id': 'REAL:IMO:' + imo, 'imo_number': imo, 'mmsi': mmsi, 'registry_imo_number': registered,
            'reference_length_m': dimension('dimensionToBow', 'dimensionToStern', 511, 'LENGTH'),
            'reference_beam_m': dimension('dimensionToPort', 'dimensionToStarboard', 63, 'BEAM'),
            'registry_draught_m': draft, 'valid_from': stamp('validFrom'), 'valid_to': stamp('validTo'),
            'source_ref': {'source_id': 'norway_static', 'locator': f'/data/{index}'}, 'issues': issues})
    return result


def environment_record(key, payload, metadata, meta_source, datum_source=None, datum_text=None):
    station, parameter, unit, name = STATIONS[key]
    if (str(payload['station']['key']), payload['station']['name'], str(payload['parameter']['key'])) != (station, name, parameter):
        raise ValueError('Observation identity changed; review required')
    metadata_name = metadata.get('name')
    if metadata_name is None and metadata.get('title') == f'Vindhastighet - {name}: Välj tidsutsnitt':
        metadata_name = name
    if (str(metadata['key']), metadata_name, metadata['active'], metadata.get('mobile', False)) != (station, name, True, False):
        raise ValueError('Station identity/operational state changed')
    if payload['period']['key'] != 'latest-hour' or payload['parameter']['unit'] != ('cm' if unit == 'cm' else 'meter per sekund'):
        raise ValueError('Unit/period changed')
    if unit == 'm/s' and payload['parameter'].get('summary') != 'medelvärde 10 min, 1 gång/tim':
        raise ValueError('Wind aggregation changed')
    values = payload.get('value')
    if not isinstance(values, list) or not 0 < len(values) <= 100:
        raise ValueError('Unexpected observation count')
    latest = max(v['date'] for v in values)
    rows = [v for v in values if v['date'] == latest]
    if len(rows) != 1 or type(latest) is not int:
        raise ValueError('Ambiguous latest observation')
    row = rows[0]
    observed = datetime.fromtimestamp(latest / 1000, timezone.utc)
    position = metadata
    if unit == 'm/s':
        positions = [p for p in metadata.get('position', []) if p['from'] <= latest <= p['to']]
        if len(positions) != 1:
            raise ValueError('Station position unknown/ambiguous at observation time')
        position = positions[0]
    lat, lon = Decimal(str(position['latitude'])), Decimal(str(position['longitude']))
    if not (Decimal('57.5') <= lat <= Decimal('57.9') and Decimal('11.4') <= lon <= Decimal('12.1')):
        raise ValueError('Reviewed regional station moved outside Gothenburg region')
    if unit == 'cm' and (not datum_source or not datum_text or 'Höjdsystem: RH2000' not in datum_text or
                         f'{name};{station};' not in datum_text):
        raise ValueError('Water level datum/station evidence changed')
    return {'port_id': 'WPI:24020', 'station_id': station, 'station_name': name, 'latitude': str(lat), 'longitude': str(lon),
        'parameter_id': parameter, 'unit': unit, 'value': str(row['value']), 'observed_at': observed.isoformat(),
        'quality': row['quality'], 'aggregation': 'minute observation' if unit == 'cm' else '10-minute mean, hourly publication',
        'vertical_datum': 'RH2000' if unit == 'cm' else None,
        'station_metadata': {k: meta_source[k] for k in ('url', 'sha256')},
        'datum_evidence': {k: datum_source[k] for k in ('url', 'sha256')} if unit == 'cm' else None,
        'source_ref': {'source_id': key, 'locator': f'/value/{values.index(row)}'}}


def extend(base, raw, output):
    baseline = base.read_bytes()
    original = NavigationCatalog.model_validate_json(baseline)
    manifest = json.loads((raw / 'manifest.json').read_text(encoding='utf-8'))
    if original.version != 'NAVIGATION-REFERENCES-1.2' or digest(baseline) != manifest['base_sha256']:
        raise ValueError('Baseline lineage differs')
    period = ReferencePeriod.model_validate(manifest['period'])
    if period.end > period_for(datetime.now(timezone.utc)).end:
        raise ValueError('Registry period is not a completed month')
    records, data = manifest['sources'], {}
    expected = {'norway_static': static_url(original, period), **URLS}
    if set(records) != set(expected):
        raise ValueError('Required source list differs')
    for key, url in expected.items():
        row = records[key]
        filename = key + ('.csv' if key == 'smhi_water_datum' else '.json')
        path = raw / filename
        if row.get('status') != 'captured' or row.get('request_url') != url or row.get('filename') != filename or row.get('url') != (STATIC if key == 'norway_static' else url):
            raise ValueError('Source identity differs')
        if path.is_symlink() or not path.is_file() or path.stat().st_size > LIMIT:
            raise ValueError('Raw source size/path invalid')
        data[key] = path.read_bytes()
        if digest(data[key]) != row['sha256'] or len(data[key]) != row['bytes']:
            raise ValueError('Raw source hash/size differs')
    schema = json.loads(data['schema_no_static'])
    props = schema['components']['schemas']['KDataAPI3.Models.ResponseModels.AisStaticRecord']['properties']
    if any('metres' not in props[field].get('description', '') for field in ('dimensionToBow','dimensionToStern','dimensionToPort','dimensionToStarboard')) or 'registry' not in props['draught'].get('description', '').lower():
        raise ValueError('Registry units/meaning changed')
    license_url = schema['info']['license']['url']
    if license_url != 'https://data.norge.no/nlod/en/1.0':
        raise ValueError('Registry license changed')
    payload = original.model_dump(mode='json')
    payload.update(version='NAVIGATION-REFERENCES-1.3', generated_at=datetime.now(timezone.utc).isoformat(),
        static_reference_period=period.model_dump(mode='json'),
        static_references=registry_records(json.loads(data['norway_static']), bindings(original)))
    payload['environment_observations'] = [environment_record(key, json.loads(data[key]), json.loads(data[key+'_metadata']),
        records[key+'_metadata'], records['smhi_water_datum'], data['smhi_water_datum'].decode('utf-8-sig')) for key in STATIONS]
    for key in ('norway_static', 'schema_no_static', *STATIONS):
        row = records[key]
        payload['sources'].append({k: row[k] for k in ('url','sha256','retrieved_at')} | {'id': key, 'effective_at': None,
            'attribution': 'Kystverket / Kystdatahuset; reconstructed historical registry, not current AIS measurements' if key not in STATIONS else
            'SMHI open data / station owner; regional observation, not berth conditions or forecast',
            'license_url': license_url if key not in STATIONS else None})
    catalog = NavigationCatalog.model_validate(payload)
    if output.exists():
        raise ValueError('Use a new output; previous catalog preserved')
    output.parent.mkdir(parents=True, exist_ok=True)
    dump(output, catalog.model_dump(mode='json'))
    summaries = [static_summary(catalog.static_references, catalog.static_reference_period, 'REAL:IMO:'+i) for i in bindings(original).values()]
    summary = catalog_summary(catalog, digest(output.read_bytes()))
    summary['registry_summary_states'] = dict(Counter(s['status'] for s in summaries))
    summary['registry_length_available'] = sum(s['length_m'] is not None for s in summaries)
    summary['registry_beam_available'] = sum(s['beam_m'] is not None for s in summaries)
    dump(output.with_suffix('.summary.json'), summary)
    return summary


def capture_routes(directory):
    """Archive access/applicability evidence separately; never add a route to a port catalog."""
    import xml.etree.ElementTree as ET
    directory.mkdir(parents=True, exist_ok=False)
    sources, payloads = {}, {}
    for url in ROUTE_URLS:
        key = 'all' if url.endswith('/list') else url.rsplit('/',1)[1]
        path = directory / (key+'.json')
        download(url,path)
        data = path.read_bytes()
        payloads[key] = json.loads(data)
        if not isinstance(payloads[key],list) or len(payloads[key])>5000:
            raise ValueError('Unexpected route list')
        sources[key] = {'url':url,'sha256':digest(data),'retrieved_at':datetime.now(timezone.utc).isoformat(),'records':len(payloads[key])}
        dump(directory/'manifest.json',sources)
    sample = payloads['NOBGO'][0] if payloads['NOBGO'] else None
    if sample:
        number = sample['routenumber']
        if not re.fullmatch(r'NO-[0-9]{6}',number):
            raise ValueError('Unreviewed route identity')
        path = directory/(number+'.rtz'); url = ROUTE_BASE+'/'+number+'/download'
        download(url,path); data = path.read_bytes()
        if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
            raise ValueError('External/entity XML is not supported')
        root = ET.fromstring(data)
        if root.tag.rsplit('}',1)[-1] != 'route':
            raise ValueError('Unexpected RTZ format')
        sources['rtz_sample'] = {'url':url,'sha256':digest(data),'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'route_id':number,'waypoints':sum(e.tag.rsplit('}',1)[-1]=='waypoint' for e in root.iter()),
            'validity_start':sample['validityperiodstart'],'validity_stop':sample['validityperiodstop']}
        dump(directory/'manifest.json',sources)
    now = datetime.now(timezone.utc)
    summary = {'reference_only':True,'admission':'not_assessed','assessed_at':now.isoformat(),
        'all_records':len(payloads['all']),
        'currently_valid_records':sum(datetime.fromisoformat(r['validityperiodstart'])<=now<datetime.fromisoformat(r['validityperiodstop']) for r in payloads['all']),
        'supported_port_route_counts':{key:len(payloads[key]) for key in ('SEGOT','FIHEL','DKAAL')},
        'bergen_records':len(payloads['NOBGO']), 'catalog_routes_added':0,
        'notice':'Archived route references only. Current supported ports lack an exact route binding; expired periods are not renewed by download.'}
    dump(directory/'summary.json',summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    route_cmd = sub.add_parser('route-audit')
    route_cmd.add_argument('--raw-dir',type=Path,required=True)
    for name in ('fetch', 'extend'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--base', type=Path, required=True)
        cmd.add_argument('--raw-dir', type=Path, required=True)
        if name == 'extend':
            cmd.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'route-audit':
        result = capture_routes(args.raw_dir)
    else:
        result = fetch(args.base, args.raw_dir) if args.command == 'fetch' else extend(args.base, args.raw_dir, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
