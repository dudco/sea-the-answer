"""Prepare open reference data that can support, but not certify, CII work.

The script deliberately keeps these datasets outside the PostgreSQL maritime_data schema.
IMO DCS reports are aggregated and anonymized. Wikidata and MarineVessels ship
particulars are useful candidate values, but are not verified statutory records.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "maritime-data" / "2026-09-30-v2"
REFERENCE = DATA / "reference"
OUTPUT = REFERENCE / "open-cii-inputs"
MARINE = REFERENCE / "marine-vessels-2015" / "marine_vessels.csv"
WIKIDATA = REFERENCE / "wikidata-vessel-particulars" / "wikidata_ships_with_deadweight.csv"
DCS = REFERENCE / "imo-dcs-public-reports"

TONNE_URI = "http://www.wikidata.org/entity/Q191118"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_imo(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()


def prepare_capacity_candidates() -> dict[str, object]:
    vessels = pd.read_csv(DATA / "vessels.csv", dtype=str)
    vessels = vessels[vessels["data_origin"].eq("REAL")].copy()
    vessels["imo_number"] = normalize_imo(vessels["imo_number"])

    marine = pd.read_csv(MARINE, dtype=str)
    marine["imo_number"] = normalize_imo(marine["IMO"])
    marine["marine_dwt_t"] = pd.to_numeric(marine["DWT"], errors="coerce")
    marine["marine_gt"] = pd.to_numeric(marine["GT"], errors="coerce")
    marine["marine_non_null"] = marine[["DWT", "GT", "type", "built", "length", "beam"]].notna().sum(axis=1)
    marine = (
        marine[marine["imo_number"].str.fullmatch(r"\d{7}")]
        .sort_values(["imo_number", "marine_non_null"], ascending=[True, False])
        .drop_duplicates("imo_number")
    )

    wikidata = pd.read_csv(WIKIDATA, dtype=str)
    wikidata["imo_number"] = normalize_imo(wikidata["imo"])
    wikidata = wikidata[
        wikidata["imo_number"].str.fullmatch(r"\d{7}") & wikidata["dwtUnit"].eq(TONNE_URI)
    ].copy()
    wikidata["wikidata_dwt_t"] = pd.to_numeric(wikidata["dwt"], errors="coerce")
    wikidata["wikidata_gt"] = pd.to_numeric(wikidata["gt"], errors="coerce")
    wikidata = (
        wikidata.sort_values(["imo_number", "wikidata_dwt_t"])
        .drop_duplicates("imo_number")
    )

    result = vessels[["vessel_id", "imo_number"]].merge(
        wikidata[["imo_number", "ship", "wikidata_dwt_t", "wikidata_gt"]],
        on="imo_number",
        how="left",
    ).merge(
        marine[
            [
                "imo_number",
                "name",
                "type",
                "built",
                "marine_dwt_t",
                "marine_gt",
                "ship_draught",
                "length",
                "beam",
            ]
        ],
        on="imo_number",
        how="left",
    )

    both = result["wikidata_dwt_t"].notna() & result["marine_dwt_t"].notna()
    denominator = result[["wikidata_dwt_t", "marine_dwt_t"]].max(axis=1)
    result["dwt_relative_difference"] = (
        (result["wikidata_dwt_t"] - result["marine_dwt_t"]).abs() / denominator
    )
    result["capacity_status"] = "UNAVAILABLE"
    result.loc[result["wikidata_dwt_t"].notna(), "capacity_status"] = "WIKIDATA_ONLY"
    result.loc[result["marine_dwt_t"].notna(), "capacity_status"] = "MARINE_VESSELS_ONLY"
    result.loc[both & result["dwt_relative_difference"].le(0.05), "capacity_status"] = "AGREE_WITHIN_5_PERCENT"
    result.loc[both & result["dwt_relative_difference"].gt(0.05), "capacity_status"] = "CONFLICT_OVER_5_PERCENT"
    result["candidate_dwt_t"] = result["wikidata_dwt_t"].combine_first(result["marine_dwt_t"])
    result["candidate_gt"] = result["wikidata_gt"].combine_first(result["marine_gt"])
    result["use_restriction"] = "REFERENCE_ONLY_NOT_STATUTORY_VERIFIED"
    result["wikidata_source_url"] = "https://www.wikidata.org/"
    result["marine_vessels_source_url"] = "https://github.com/rich-iannone/MarineVessels"

    result.to_csv(OUTPUT / "vessel_capacity_candidates.csv", index=False, encoding="utf-8-sig")

    annual = pd.read_csv(DATA / "annual_reports.csv", usecols=["vessel_id"], dtype=str)
    usable_vessel_ids = set(result.loc[result["candidate_dwt_t"].notna(), "vessel_id"])
    annual_candidate_rows = int(annual["vessel_id"].isin(usable_vessel_ids).sum())
    return {
        "real_vessels": int(len(result)),
        "wikidata_dwt_matches": int(result["wikidata_dwt_t"].notna().sum()),
        "marine_vessels_dwt_matches": int(result["marine_dwt_t"].notna().sum()),
        "union_dwt_matches": int(result["candidate_dwt_t"].notna().sum()),
        "union_dwt_coverage_pct": round(float(result["candidate_dwt_t"].notna().mean() * 100), 2),
        "cross_source_matches": int(both.sum()),
        "cross_source_agree_within_5_pct": int((both & result["dwt_relative_difference"].le(0.05)).sum()),
        "cross_source_conflict_over_5_pct": int((both & result["dwt_relative_difference"].gt(0.05)).sum()),
        "annual_report_rows_with_candidate_dwt": annual_candidate_rows,
        "annual_report_candidate_dwt_coverage_pct": round(float(annual_candidate_rows / len(annual) * 100), 2),
    }


def prepare_dcs_tables() -> dict[str, object]:
    annual_totals = pd.DataFrame(
        [
            [2019, 27221, 1187155816, 1779238611, 1562499142, 132289058, 213070793, None],
            [2020, 27723, 1221698112, 1839017080, 1483530033, 127016759, 203103633, None],
            [2021, 28171, 1254767215, 1873250408, 1488515348, 125708570, 212230077, None],
            [2022, 28834, 1289334001, 1920542414, 1521381982, 129828224, 213364131, 664432909],
            [2023, 28620, 1300833461, 1931978701, 1638421345, 142637834, 211137491, 655703233],
            [2024, 29690, 1356540397, 2005422879, 1731903177, 150703725, 223370487, 691492741],
        ],
        columns=[
            "reporting_year",
            "ships_reported",
            "gross_tonnage",
            "deadweight_tonnage",
            "distance_nm",
            "hours_under_way",
            "fuel_consumption_t",
            "co2_emissions_t",
        ],
    )
    annual_totals["aggregation"] = "GLOBAL_ANONYMIZED_AGGREGATE"
    annual_totals["source"] = "IMO_DCS_ANNUAL_REPORT"
    annual_totals.to_csv(OUTPUT / "imo_dcs_annual_totals_2019_2024.csv", index=False, encoding="utf-8-sig")

    cii = pd.DataFrame(
        [
            [2023, 28620, 5528, 6028, 7625, 3931, 1541, 3967],
            [2024, 28453, 5605, 6075, 8355, 4319, 1563, 2536],
        ],
        columns=["reporting_year", "cii_scope_ships", "rating_a", "rating_b", "rating_c", "rating_d", "rating_e", "not_reported"],
    )
    cii["ratings_reported"] = cii[["rating_a", "rating_b", "rating_c", "rating_d", "rating_e"]].sum(axis=1)
    cii["reporting_rate_pct"] = (cii["ratings_reported"] / cii["cii_scope_ships"] * 100).round(1)
    cii.to_csv(OUTPUT / "imo_dcs_cii_ratings_2023_2024.csv", index=False, encoding="utf-8-sig")

    fuels = [
        ["Bulk carrier", 3879436, 42970657, 9904804, 0, 2, 121791, 3, 6162, 1, 21775],
        ["Combination carrier", 11188, 131592, 4742, 0, 0, 0, 0, 0, 0, 0],
        ["Containership", 4820629, 56348774, 4364612, 0, 0, 1276070, 0, 2852, 21289, 656263],
        ["Cruise passenger ship", 2096178, 3785430, 74436, 0, 0, 241014, 0, 0, 0, 45493],
        ["Gas carrier", 653176, 3964120, 1050529, 0, 23472, 198246, 62280, 244602, 0, 679],
        ["General cargo ship", 1904130, 4022738, 1318438, 0, 0, 27537, 0, 0, 0, 10050],
        ["LNG carrier", 882251, 2424514, 176226, 0, 0, 12058444, 0, 0, 28410, 60],
        ["Others", 2299712, 2246672, 444722, 0, 0, 178661, 0, 0, 0, 1453],
        ["Passenger ship", 408249, 779988, 159449, 0, 0, 148235, 0, 0, 0, 0],
        ["Refrigerated cargo carrier", 132918, 692022, 243310, 0, 0, 0, 0, 0, 0, 25],
        ["Ro-ro cargo ship", 390669, 1957831, 269053, 0, 0, 31262, 0, 0, 0, 15414],
        ["Ro-ro cargo ship (vehicle carrier)", 694426, 3863409, 1213793, 0, 0, 190970, 0, 0, 0, 268653],
        ["Ro-ro passenger ship", 1077879, 2188346, 446152, 0, 0, 160811, 0, 0, 0, 5728],
        ["Tanker", 7118084, 30658883, 4775843, 0, 0, 321653, 18279, 15891, 88144, 28803],
    ]
    fuel_columns = ["ship_type", "mdo_mgo_t", "hfo_t", "lfo_t", "ethane_t", "ethanol_t", "lng_t", "lpg_butane_t", "lpg_propane_t", "methanol_t", "other_t"]
    fuel_table = pd.DataFrame(fuels, columns=fuel_columns)
    fuel_table.insert(0, "reporting_year", 2024)
    fuel_table["total_fuel_t"] = fuel_table[fuel_columns[1:]].sum(axis=1)
    assert int(fuel_table["total_fuel_t"].sum()) == 223370487
    fuel_table.to_csv(OUTPUT / "imo_dcs_fuel_by_ship_type_2024.csv", index=False, encoding="utf-8-sig")

    return {
        "annual_years": annual_totals["reporting_year"].tolist(),
        "annual_rows": int(len(annual_totals)),
        "cii_years": cii["reporting_year"].tolist(),
        "cii_rows": int(len(cii)),
        "fuel_by_ship_type_rows_2024": int(len(fuel_table)),
        "fuel_total_2024_t": int(fuel_table["total_fuel_t"].sum()),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    capacity = prepare_capacity_candidates()
    dcs = prepare_dcs_tables()
    source_files = []
    for path in sorted((DCS.glob("*.pdf"))):
        source_files.append({"filename": path.name, "sha256": sha256(path), "bytes": path.stat().st_size})
    source_files.extend(
        [
            {"filename": str(MARINE.relative_to(REFERENCE)), "sha256": sha256(MARINE), "bytes": MARINE.stat().st_size},
            {"filename": str(WIKIDATA.relative_to(REFERENCE)), "sha256": sha256(WIKIDATA), "bytes": WIKIDATA.stat().st_size},
        ]
    )
    summary = {
        "purpose": "Open reference inputs for CII readiness and validation",
        "generated_on": "2026-09-30",
        "capacity_candidates": capacity,
        "imo_dcs": dcs,
        "restrictions": [
            "IMO DCS tables are global anonymized aggregates and cannot be joined to individual MRV ships.",
            "Wikidata and MarineVessels capacity values are non-statutory candidates and require verification before official CII use.",
            "MarineVessels is dated 2015 and does not document its upstream source in the package metadata.",
            "EU MRV covers EEA-related voyages and is not a complete global IMO DCS annual record.",
        ],
        "source_files": source_files,
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
