from __future__ import annotations

import json
from pathlib import Path

from .model import INPUT_SCHEMA


def find_record(jsonl: Path | str, county_code: str, tax_year: int, parcel_id: str) -> dict | None:
    want = f"FL-{str(county_code).zfill(2)}-{tax_year}-{parcel_id}"
    with open(jsonl) as fh:
        for line in fh:
            if want in line:
                rec = json.loads(line)
                if rec.get("case_id") == want:
                    return rec
    return None


def build_input(case_id: str, find: dict, qualification: dict | None, authorization: dict | None, consent: dict | None = None,
                homeowner_submissions: list | None = None, prior_review: dict | None = None, appeal_type: str = "vab_just_value",
                deadlines: dict | None = None) -> dict:
    j = find.get("jurisdiction") or {}
    inp = {"schema": INPUT_SCHEMA, "case_id": case_id,
           "appeal": {"tax_year": j.get("tax_year"), "appeal_type": appeal_type,
                      "jurisdiction": {"state": j.get("state", "FL"), "county": j.get("county"), "county_code": j.get("county_code")}},
           "property": {"parcel_id": (find.get("property") or {}).get("parcel_id"), "address": (find.get("property") or {}).get("address")},
           "find": find, "qualification": qualification or {}, "authorization": authorization or {}, "consent": consent or {},
           "homeowner_submissions": homeowner_submissions or []}
    if prior_review:
        inp["prior_review"] = prior_review
    if deadlines:
        inp["deadlines"] = deadlines
    return inp


def normalize_county(name: str) -> str:
    import re
    k = re.sub(r",?\s*(florida|fl)\.?$", "", name.strip(), flags=re.I)
    k = re.sub(r"\s+county$", "", k.strip(), flags=re.I)
    from taxfind.pipeline import _key
    return _key(k)


def resolve_county_code(name: str, tax_year: int, data_dir=None) -> str | None:
    import os
    if data_dir:
        os.environ["FIND_DATA_DIR"] = str(data_dir)
    from taxfind.config import Settings
    from taxfind.engine.ingest import HttpCache
    from taxfind.desks.property_tax.florida import discover
    want = normalize_county(name)
    pairs = discover(HttpCache(Settings().ensure().cache_dir / "http"), tax_year)
    hits = [no for no, p in pairs.items() if normalize_county(p["NAL"].county) == want]
    return hits[0] if len(hits) == 1 else None
