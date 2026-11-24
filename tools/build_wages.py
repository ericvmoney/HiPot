"""Build the government wage reference for the pay page from BLS OEWS data.

Input (downloaded by hand through a browser, because BLS refuses scripted
requests; ignored by git):
  data/pay/source/oesm25ma/MSA_M2025_dl.xlsx   OEWS May 2025, metropolitan areas
  data/geo/source/list1_2023.xlsx              OMB delineations (CBSA -> CSA)

Output (committed, small):
  data/pay/bls-oews-2025.json

For each HiPot metro region and each occupation below: the annual and hourly
median, 75th and 90th percentiles, and employment, taken from the metropolitan
area in that region with the most people in that occupation. BLS top-codes very
high wages (shown as '#'); those values are recorded as null with a flag.

The mapping from HiPot role groups and levels to occupations is a first draft
by the supervisor, after the old hub's method: median for senior, 75th
percentile for staff, 90th for principal, and the engineering-manager
occupation's median for managers. BLS has no level or job-title split, so the
figure is a reference point, not a salary for the role.

    uv run python -m tools.build_wages
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import openpyxl

from pipeline.io import ROOT, load_yaml

SOURCE = ROOT / "data" / "pay" / "source" / "oesm25ma" / "MSA_M2025_dl.xlsx"
DELINEATION = ROOT / "data" / "geo" / "source" / "list1_2023.xlsx"
OUT = ROOT / "data" / "pay" / "bls-oews-2025.json"

OCCUPATIONS = {
    "11-9041": "Architectural and engineering managers",
    "11-3051": "Industrial production managers",
    "11-2021": "Marketing managers",
    "13-1081": "Logisticians",
    "13-1023": "Purchasing agents",
    "13-1082": "Project management specialists",
    "13-1071": "Human resources specialists",
    "13-1161": "Market research analysts and marketing specialists",
    "13-2011": "Accountants and auditors",
    "15-1252": "Software developers",
    "15-1244": "Network and computer systems administrators",
    "15-2051": "Data scientists",
    "17-2011": "Aerospace engineers",
    "17-2041": "Chemical engineers",
    "17-2051": "Civil engineers",
    "17-2061": "Computer hardware engineers",
    "17-2071": "Electrical engineers",
    "17-2072": "Electronics engineers, except computer",
    "17-2112": "Industrial engineers",
    "17-2131": "Materials engineers",
    "17-2141": "Mechanical engineers",
    "17-2161": "Nuclear engineers",
    "17-2199": "Engineers, all other",
    "17-3023": "Electrical and electronic engineering technologists and technicians",
    "17-3027": "Mechanical engineering technologists and technicians",
    "19-2012": "Physicists",
    "19-2032": "Materials scientists",
    "19-5011": "Occupational health and safety specialists",
    "23-1011": "Lawyers",
    "41-4011": "Sales representatives, technical and scientific products",
    "47-2111": "Electricians",
    "49-1011": "First-line supervisors of mechanics, installers and repairers",
    "51-1011": "First-line supervisors of production and operating workers",
    "51-2028": "Electrical, electronic and electromechanical assemblers",
    "51-9061": "Inspectors, testers, sorters, samplers and weighers",
}

# Draft: HiPot role group (first discipline for engineering and science roles,
# otherwise the function) -> occupation. Managers and directors of engineering
# roles use 11-9041 instead.
ROLE_TO_OCCUPATION = {
    "systems": "17-2199", "electrical": "17-2071", "power-electronics": "17-2072", "battery": "17-2199",
    "power-systems": "17-2071", "mechanical": "17-2141", "thermal": "17-2141", "controls": "17-2199",
    "firmware": "17-2061", "software": "15-1252", "data": "15-2051", "test": "17-2199",
    "manufacturing": "17-2112", "chemical-process": "17-2041", "materials": "17-2131", "quality": "17-2112",
    "field": "17-2199", "nuclear-plasma": "17-2161", "optics": "17-2072", "civil-structural": "17-2051",
    "aerospace": "17-2011",
    "science": "19-2032", "technician": "17-3023", "trades": "47-2111", "production": "51-2028",
    "supply-chain": "13-1081", "quality-compliance": "51-9061", "ehs": "19-5011", "project-program": "13-1082",
    "field-operations": "49-1011", "product": "11-2021", "sales-bd": "41-4011", "marketing": "13-1161",
    "finance-legal": "13-2011", "people-admin": "13-1071", "it": "15-1244",
}
LEVEL_TO_STATISTIC = {"intern": None, "entry": "p25", "mid": "median", "senior": "median", "staff": "p75",
                      "principal": "p90", "manager": "median", "director": "p75", "executive": "p90"}
MANAGER_OCCUPATION = {"engineering": "11-9041", "production": "11-3051"}


def number(value):
    """BLS cells: a number, '*' (not available) or '#' (top-coded)."""
    if isinstance(value, (int, float)):
        return value, False
    return None, value == "#"


def region_of_cbsa() -> dict[str, str]:
    """CBSA code -> HiPot metro id, through the CSA where there is one."""
    taxonomy = load_yaml(ROOT / "taxonomy.yml")
    by_census = {m["census"]: m["id"] for m in taxonomy["metros"]}
    rows = list(openpyxl.load_workbook(DELINEATION, read_only=True).active.iter_rows(values_only=True))
    header = rows[2]
    out = {}
    for row in (dict(zip(header, r)) for r in rows[3:] if r[0] and str(r[0]).isdigit()):
        metro = by_census.get(f"CSA {row['CSA Code']}") if row["CSA Code"] else None
        metro = metro or by_census.get(f"CBSA {row['CBSA Code']}")
        if metro:
            out[str(row["CBSA Code"])] = metro
    return out


def main() -> int:
    if not SOURCE.exists():
        print(f"Missing {SOURCE.relative_to(ROOT)}: download oesm25ma.zip from https://www.bls.gov/oes/tables.htm "
              "in a browser and extract it into data/pay/source/.", file=sys.stderr)
        return 1
    regions = region_of_cbsa()
    best: dict[tuple[str, str], dict] = {}
    unmapped = set()
    rows = openpyxl.load_workbook(SOURCE, read_only=True).active.iter_rows(values_only=True)
    header = next(rows)
    for raw in rows:
        row = dict(zip(header, raw))
        if row["OCC_CODE"] not in OCCUPATIONS or row["O_GROUP"] != "detailed":
            continue
        metro = regions.get(str(row["AREA"]))
        if metro is None:
            unmapped.add(row["AREA_TITLE"])
            continue
        employment = row["TOT_EMP"] if isinstance(row["TOT_EMP"], (int, float)) else 0
        key = (metro, row["OCC_CODE"])
        if key in best and best[key]["employment"] >= employment:
            continue
        figures, top_coded = {}, []
        for stat, column in (("p25", "PCT25"), ("median", "MEDIAN"), ("p75", "PCT75"), ("p90", "PCT90")):
            for period, prefix in (("year", "A_"), ("hour", "H_")):
                value, capped = number(row[prefix + column])
                figures[f"{period}_{stat}"] = value
                if capped:
                    top_coded.append(f"{period}_{stat}")
        best[key] = {"employment": int(employment), "area": row["AREA_TITLE"], **figures,
                     **({"top_coded": top_coded} if top_coded else {})}

    by_metro: dict[str, dict] = defaultdict(dict)
    for (metro, occupation), figures in sorted(best.items()):
        by_metro[metro][occupation] = figures
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "U.S. Bureau of Labor Statistics, Occupational Employment and Wage Statistics, May 2025, "
                  "metropolitan areas (https://www.bls.gov/oes/tables.htm, oesm25ma.zip)",
        "built_by": "tools/build_wages.py",
        "note": "Per HiPot metro region: the metropolitan area in it with the most people in each occupation. "
                "BLS has no level or job-title split; these are reference points, not salaries for a role. "
                "Top-coded values (BLS '#') are null and listed in top_coded.",
        "occupations": OCCUPATIONS,
        "role_to_occupation": ROLE_TO_OCCUPATION,
        "manager_occupation": MANAGER_OCCUPATION,
        "level_to_statistic": LEVEL_TO_STATISTIC,
        "metros": by_metro,
    }, separators=(",", ":"), sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    print(f"metro regions with data: {len(by_metro)}; occupation-region pairs: {len(best)}")
    print(f"BLS areas outside HiPot's metro regions (skipped): {len(unmapped)}")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
