#!/usr/bin/env python3
"""Upsert Find's candidates.csv into claimos-site's `candidates` table.

usage: import_candidates.py <candidates.csv> <run_id> [app_id]

Runs SQL through `naive db query --app <id>` (the CLI is logged in; no secrets here).
"""
import csv
import os
import re
import shutil
import subprocess
import sys

APP = "app_nkhc92xe21cyzfd5qakpkcj4g4"  # claimos-site
NAIVE = shutil.which("naive") or os.path.expanduser("~/.local/bin/naive")
BATCH = 500

CSV_COLS = ["case_id", "county", "tax_year", "parcel_id", "address", "unit", "city", "zip", "use", "homestead",
            "just_value", "assessed_value", "defensible_value", "annual_savings", "neighbor_ratio", "sales_ratio",
            "tier", "filing_closes", "filing_status"]
COLS = CSV_COLS + ["run_id", "addr_key"]
NUMERIC = {"tax_year", "just_value", "assessed_value", "defensible_value", "annual_savings", "neighbor_ratio", "sales_ratio"}
BOOLEAN = {"homestead"}


def addr_key(address, zip_):
    # Same rule as the schema comment: upper(regexp_replace(trim(address), '\s+', ' ', 'g')) || '|' || coalesce(zip,'')
    return re.sub(r"\s+", " ", (address or "").strip()).upper() + "|" + (zip_ or "").strip()


def lit(col, value):
    v = (value or "").strip()
    if v == "":
        return "NULL"
    if col in NUMERIC:
        return str(int(float(v))) if col == "tax_year" else repr(float(v))
    if col in BOOLEAN:
        return "true" if v.lower() in ("true", "t", "1", "yes") else "false"
    return "'" + v.replace("'", "''") + "'"  # text and date columns; Postgres casts the date literal


def upsert_sql(rows, run_id):
    values = []
    for r in rows:
        r = dict(r, run_id=run_id, addr_key=addr_key(r["address"], r["zip"]))
        values.append("(" + ",".join(lit(c, r[c]) for c in COLS) + ")")
    updates = ",".join("%s=excluded.%s" % (c, c) for c in COLS if c != "case_id")
    return "insert into candidates (%s) values %s on conflict (case_id) do update set %s, imported_at=now()" % (
        ",".join(COLS), ",".join(values), updates)


def run_sql(sql, app):
    subprocess.run([NAIVE, "db", "query", sql, "--app", app], check=True, stdout=subprocess.DEVNULL)


def main(path, run_id, app=APP):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for i in range(0, len(rows), BATCH):
        run_sql(upsert_sql(rows[i:i + BATCH], run_id), app)
        print("upserted %d/%d" % (min(i + BATCH, len(rows)), len(rows)))


assert addr_key("7969    1ST PL ", "33935") == "7969 1ST PL|33935"
assert lit("address", "O'NEIL ST") == "'O''NEIL ST'" and lit("homestead", "False") == "false" and lit("unit", "") == "NULL"

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
