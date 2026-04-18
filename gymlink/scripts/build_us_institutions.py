"""
Download NCES IPEDS Institutional Characteristics (HD) and build
static/data/us_institutions.json for GymLink school autocomplete.

Official source: https://nces.ed.gov/ipeds/datacenter/
Data file: HD{year}.zip → HD{year}.csv

Included: active (CYACTIVE=1) postsecondary institutions (PSEFLAG=1).
This covers public & private nonprofit & for-profit four-year schools,
community colleges, and other accredited postsecondary campuses in the
IPEDS universe (including D.C., Puerto Rico, and other U.S. areas NCES lists).
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "static" / "data" / "us_institutions.json"
SOURCE_BASE = "https://nces.ed.gov/ipeds/datacenter/data/HD{year}.zip"

CONTROL_LABEL = {
    "1": "Public",
    "2": "Private nonprofit",
    "3": "Private for-profit",
    "-3": "Unknown",
}
ICLEVEL_LABEL = {
    "1": "4-year",
    "2": "2-year",
    "3": "Less than 2-year",
    "-3": "Unknown",
}


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] | None = None
    year_used: int | None = None
    for year in range(2024, 2019, -1):
        url = SOURCE_BASE.format(year=year)
        try:
            with urlopen(url, timeout=120) as resp:
                raw = resp.read()
        except OSError as e:
            print(f"WARN: could not download {url}: {e}", file=sys.stderr)
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                if not names:
                    print(f"WARN: no CSV in zip {url}", file=sys.stderr)
                    continue
                csv_name = names[0]
                with zf.open(csv_name) as f:
                    # utf-8-sig strips BOM so the first column is "UNITID", not "\xef\xbb\xbfUNITID"
                    # when mis-decoded as latin-1.
                    text = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
                    reader = csv.DictReader(text)
                    rows = list(reader)
                    year_used = year
                    break
        except (zipfile.BadZipFile, OSError, UnicodeError) as e:
            print(f"WARN: bad zip or read error {url}: {e}", file=sys.stderr)
            continue

    if not rows or year_used is None:
        print("ERROR: could not download or parse any HD20xx.zip from NCES.", file=sys.stderr)
        return 1

    institutions: list[dict[str, str]] = []
    for row in rows:
        if row.get("CYACTIVE") != "1" or row.get("PSEFLAG") != "1":
            continue
        name = (row.get("INSTNM") or "").strip()
        if not name:
            continue
        city = (row.get("CITY") or "").strip()
        state = (row.get("STABBR") or "").strip()
        ctl = CONTROL_LABEL.get(row.get("CONTROL", ""), "Unknown")
        lvl = ICLEVEL_LABEL.get(row.get("ICLEVEL", ""), "Unknown")
        institutions.append(
            {
                "unitid": (row.get("UNITID") or "").strip(),
                "name": name[:200],
                "city": city[:80],
                "state": state[:2],
                "control": ctl,
                "level": lvl,
            }
        )

    institutions.sort(key=lambda x: (x["name"].lower(), x["city"].lower()))

    payload = {
        "meta": {
            "source": "U.S. National Center for Education Statistics (NCES), IPEDS",
            "survey": "Institutional Characteristics",
            "file": f"HD{year_used}",
            "url": SOURCE_BASE.format(year=year_used),
            "filter": "CYACTIVE=1 and PSEFLAG=1 (active postsecondary)",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "count": len(institutions),
        },
        "institutions": institutions,
    }

    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(institutions)} institutions to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
