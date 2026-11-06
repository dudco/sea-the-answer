"""Bounded official Norway AIS / Aalborg sources, separate from runtime downloads."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
import time
import urllib.request

from backend.tools.port_reference import valid_imo
from scripts.prepare_navigation_references import digest, dump
from scripts.prepare_port_references import read_csv, normalize_ports, PORT_NUMBERS

URLS = {
    "ais_no": ("https://kystdatahuset.no/ws/api/ais/realtime/geojson", "norway.geojson"),
    "schema_no": ("https://kystdatahuset.no/ws/swagger/v1/swagger.json", "norway-swagger.json"),
    "aalborg_berths": ("https://portofaalborg.dk/wp-content/uploads/2026/01/port-information-and-safety-regulations_january-2026-1.pdf", "aalborg-2026.pdf"),
    "norway_terms": ("https://www.kystverket.no/en/sea-transport-and-ports/ais/access-to-ais-data/", "norway-terms.html"),
}
LIMIT = 16 * 1024 * 1024


def fetch(directory):
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for key, (url, filename) in URLS.items():
        try:
            started = time.monotonic()
            request = urllib.request.Request(url, headers={"User-Agent":"SEA-THE-ANSWER-capstone/1.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                data = bytearray()
                while True:
                    chunk = response.read1(64 * 1024)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > LIMIT or time.monotonic() - started > 180:
                        raise ValueError("Source size/time budget exceeded")
            (directory / filename).write_bytes(data)
            manifest[key] = {"id":key,"url":url,"filename":filename,"sha256":digest(data),
                "retrieved_at":datetime.now(timezone.utc).isoformat(),"status":"captured","bytes":len(data)}
        except (OSError, ValueError):
            manifest[key] = {"id":key,"url":url,"filename":filename,"status":"failed",
                             "reason":"Official source unavailable or size/time budget exceeded; TLS verification retained"}
        dump(directory / "manifest.json", manifest)
    if any(row["status"] != "captured" for row in manifest.values()):
        raise ValueError("Required source unavailable; see manifest. No previous data replaced.")
    return manifest


def captured(directory, manifest, key):
    row = manifest[key]
    if row.get("status") != "captured" or (row.get("url"),row.get("filename")) != URLS[key]:
        raise ValueError("Unsupported source identity: " + key)
    path = directory / row["filename"]
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise ValueError("Source exceeds size budget")
    data = path.read_bytes()
    if digest(data) != row.get("sha256"):
        raise ValueError("Source hash mismatch: " + key)
    return data


def norway_observations(payload, known_imos):
    """Position timestamps / undocumented dimensions never become verified static data."""
    features = payload.get("features")
    if payload.get("type") != "FeatureCollection" or not isinstance(features, list) or len(features) > 20000:
        raise ValueError("Unexpected Norway GeoJSON contract")
    ids, mmsis = Counter(), defaultdict(set)
    for feature in features:
        if not isinstance(feature,dict) or feature.get("type") != "Feature" or not isinstance(feature.get("properties"),dict):
            raise ValueError("Unexpected Norway feature contract")
        row = feature.get("properties", {})
        imo = str(row.get("imo", ""))
        if valid_imo(imo):
            ids[imo] += 1
            mmsis[str(row.get("mmsi", ""))].add(imo)
    records = []
    for index, feature in enumerate(features):
        row = feature.get("properties", {})
        imo = str(row.get("imo", ""))
        if not valid_imo(imo) or imo not in known_imos:
            continue
        mmsi = str(row.get("mmsi", ""))
        issues = ["AIS_STATIC_TIME_UNVERIFIED", "AIS_UNITS_UNVERIFIED"]
        if not re.fullmatch(r"[1-9][0-9]{8}", mmsi) or len(mmsis[mmsi]) != 1 or ids[imo] != 1:
            issues.append("AIS_IDENTITY_AMBIGUOUS")
        try:
            # The upstream field is explicitly UTC position time, not static report time.
            position = datetime.fromisoformat(row["date_time_utc"])
            position = position.replace(tzinfo=timezone.utc) if position.tzinfo is None else position.astimezone(timezone.utc)
        except (ValueError, TypeError, KeyError):
            position = None
            issues.append("AIS_POSITION_TIME_UNKNOWN")
        raw = {}
        for key in ("length", "breadth", "draught"):
            value = row.get(key)
            if type(value) in (int, float, Decimal) and Decimal(str(value)).is_finite() and len(str(value)) <= 40:
                raw[key] = str(value)
        records.append({"vessel_id":"REAL:IMO:"+imo,"imo_number":imo,
            "mmsi":mmsi if re.fullmatch(r"[1-9][0-9]{8}", mmsi) else None,"name":str(row.get("ship_name", ""))[:80],
            "metadata_received_at":None,"position_reported_at":position.isoformat() if position else None,
            "reported_length_m":None,"reported_beam_m":None,"reported_draught_m":None,"draught_lower_bound_m":None,
            "raw_reported_fields":raw,"source_ref":{"source_id":"ais_no","locator":f"/features/{index}/properties"},"issues":issues})
    return records


def aalborg_berths(page, port_id):
    """Reviewed 2026 PDF p.7. Footnoted draft and conditional LOA stay unknown."""
    expected = {"4121":("250", "9.4", "9.5", True), "4122":("250", "9.4", "9.5", False),
        "4123":("250", "9.4", "9.5", True), "4124":("130", "8.9", "9.0", False),
        "4125":("250", "9.4", "9.5", True), "0700":("250", "9.4", "9.5", True)}
    if not all(text in page for text in ("3.4. Berth limitations", "MAX. LOA", "MAX. DRAFT", "3.8. Under keel")):
        raise ValueError("Aalborg PDF headings changed; review required")
    if not re.search(r"draft.*?depends on pilo\s*t restrictions and latest soundings", page, re.I | re.S):
        raise ValueError("Aalborg draft qualifications changed")
    rows = re.findall(r"Quay\s+([0-9]{4})\s+(.+?)(?=Quay\s+[0-9]{4}|[✱*]\s*Max\.)", page, re.S)
    if len(rows) != 6 or {label for label, _ in rows} != set(expected):
        raise ValueError("Aalborg quay rows changed; do not guess columns")
    common = page[page.index("✱ Max."):] if "✱ Max." in page else page[page.index("* Max."):]
    berths = []
    for ordinal, (label, row) in enumerate(rows):
        loa, draft, depth, conditional = expected[label]
        numbers = re.findall(r"([0-9]+(?:[.,][0-9]+)?)\s*m\b", row)
        if [Decimal(n.replace(",", ".")) for n in numbers] != list(map(Decimal, (loa, draft, depth))):
            raise ValueError("Aalborg numeric columns changed; review required")
        has_condition = bool(re.search(r"depends on vessel\s+position of manifold", row))
        if conditional != has_condition or not re.search(r"Minimum 0[.,]1 m clearance", common):
            raise ValueError("Aalborg condition changed")
        text = f"Source: 2026 Oil Terminals, PDF page 7, Quay {label}\n{row.strip()}\n{common.strip()}"
        ref = {"source_id":"aalborg_berths", "locator":f"/pages/7/quays/{label}"}
        variant = {"heading":"Quay "+label,"text":text,"max_loa_m":None if conditional else loa,
                   "max_draught_m":None,"source_ref":ref}
        berths.append({"berth_id":port_id+":BERTH:"+label,"label":label,"variants":[variant],"source_ref":ref,
            "issues":["PILOT_AND_LATEST_SOUNDINGS_REQUIRED"] + (["MANIFOLD_POSITION_REQUIRED"] if conditional else []),
            "conditions":[text],"max_loa_m":variant["max_loa_m"],"max_draught_m":None,"max_beam_m":None})
    return berths


def extend(base, raw, vessels_path, wpi_path, output):
    from backend.tools.navigation_references import NavigationCatalog, catalog_summary
    original = NavigationCatalog.model_validate_json(base.read_bytes())
    if original.version not in ("NAVIGATION-REFERENCES-1.0", "NAVIGATION-REFERENCES-1.1"):
        raise ValueError("Extend a preserved 1.0/1.1 base; do not append duplicate sources")
    if digest(vessels_path.read_bytes()) != original.mrv_vessels_sha256 or digest(wpi_path.read_bytes()) != original.wpi_sha256:
        raise ValueError("Base MRV/WPI lineage differs")
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    data = {key:captured(raw, manifest, key) for key in URLS}
    schema = json.loads(data["schema_no"])
    endpoint = schema["paths"]["/api/ais/realtime/geojson"]["get"]
    if "last 10 minutes" not in endpoint.get("description", ""):
        raise ValueError("Norway position coverage changed; review the source contract")
    license_url = schema.get("info",{}).get("license",{}).get("url")
    if license_url != "https://data.norge.no/nlod/en/1.0":
        raise ValueError("Norway source license changed; review before redistributing")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("Offline PDF preparation needs pypdf; use uv run --project backend --with pypdf python -m scripts.prepare_navigation_sources") from None
    import io
    page = PdfReader(io.BytesIO(data["aalborg_berths"])).pages[6].extract_text()
    known = {r["imo_number"] for r in read_csv(vessels_path,["vessel_id","imo_number","data_origin"]) if r["data_origin"] == "REAL"}
    ports = normalize_ports(read_csv(wpi_path,["World Port Index Number","Main Port Name","Country Code","UN/LOCODE","Latitude","Longitude",*PORT_NUMBERS.values()]), {})
    aalborg = [p for p in ports if p["unlocode"] == "DKAAL"]
    if len(aalborg) != 1 or "WPI_ID_NON_UNIQUE_REQUIRES_REVIEW" in aalborg[0]["issues"]:
        raise ValueError("Aalborg to WPI mapping is ambiguous")
    payload = original.model_dump(mode="json")
    payload.update(version="NAVIGATION-REFERENCES-1.2", generated_at=datetime.now(timezone.utc).isoformat())
    payload["observations"].extend(norway_observations(json.loads(data["ais_no"]), known))
    payload["ports"].append({"port_id":aalborg[0]["port_id"],"unlocode":"DKAAL","name":"Aalborg",
        "source_id":"aalborg_berths","reference_scope":"Oil-terminal quays only; latest soundings, pilot restrictions and terminal acceptance required",
        "berths":aalborg_berths(page, aalborg[0]["port_id"])})
    for key in ("ais_no","schema_no","aalborg_berths"):
        m = manifest[key]
        payload["sources"].append({"id":key,"url":m["url"],"sha256":m["sha256"],"retrieved_at":m["retrieved_at"],
            "effective_at":None,"attribution":"Kystverket / Kystdatahuset; exact MRV IMO subset; position time and unverified units retained" if key != "aalborg_berths" else
            "Port of Aalborg A/S; 2026 Oil Terminals, p.7; conditional limits retained", "license_url":
            license_url if key != "aalborg_berths" else None})
    catalog = NavigationCatalog.model_validate(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("Use a new output path; previous catalog preserved")
    dump(output, catalog.model_dump(mode="json"))
    summary = catalog_summary(catalog, digest(output.read_bytes()))
    summary.update(raw_norway_features=len(json.loads(data["ais_no"])["features"]),
        linked_unique_imos=len({r.imo_number for r in catalog.observations}),
        cross_source_duplicate_imos=sum(n>1 for n in Counter(r.imo_number for r in catalog.observations).values()),
        berth_groups=sum(len(p.berths) for p in catalog.ports))
    dump(output.with_suffix(".summary.json"), summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch").add_argument("--raw-dir",type=Path,required=True)
    build = commands.add_parser("extend")
    for name in ("base","raw-dir","vessels","wpi","output"):
        build.add_argument("--"+name,type=Path,required=True)
    args = parser.parse_args()
    result = fetch(args.raw_dir) if args.command == "fetch" else extend(args.base,args.raw_dir,args.vessels,args.wpi,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
