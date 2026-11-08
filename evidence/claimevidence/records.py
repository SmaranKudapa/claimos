from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .model import SourceUnavailable

ROLL_COLUMNS = ("PARCEL_ID", "DOR_UC", "NBRHD_CD", "NBRHD_ORIG", "MKT_AR", "peer_basis", "PHY_ADDR1", "PHY_CITY",
                "PHY_ZIPCD", "JV", "AV_SD", "AV_NSD", "TV_SD", "TV_NSD", "JV_HMSTD", "LND_VAL", "LND_SQFOOT",
                "SPEC_FEAT_VAL", "TOT_LVG_AREA", "EFF_YR_BLT", "ACT_YR_BLT", "NO_BULDNG", "NO_RES_UNTS",
                "TAX_AUTH_CD", "TWN", "RNG", "SEC", "sqft", "eff", "land", "homestead", "ppsf")
DEFAULT_LEVEL = {"001": 0.84, "004": 0.80}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class CountyData:
    county: str
    county_code: str
    tax_year: int
    roll_stage: str
    homes: pd.DataFrame
    all_sales: pd.DataFrame
    qualified: pd.DataFrame
    time_index: dict
    time_method: dict
    level: dict
    level_source: dict
    files: list[dict]
    valuation_ym: int

    def subject(self, parcel_id: str) -> pd.Series | None:
        hit = self.homes[self.homes.PARCEL_ID == parcel_id]
        return None if hit.empty else hit.iloc[0]


def _attempt(fn, tries: int = 3, wait: float = 2.0):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(wait * (2 ** i))
    raise SourceUnavailable(f"{type(last).__name__}: {str(last)[:300]}")


def load_county(county_code: str, tax_year: int, data_dir: Path | str | None = None, tries: int = 3) -> CountyData:
    import os
    if data_dir:
        os.environ["FIND_DATA_DIR"] = str(data_dir)
    from taxfind.config import Settings
    from taxfind.engine.ingest import HttpCache
    from taxfind.desks.property_tax.florida import discover
    from taxfind.desks.property_tax.florida.source import load_pair
    from taxfind.desks.property_tax.screen import QUALIFIED, prepare, time_index

    settings = Settings().ensure()
    cache = HttpCache(settings.cache_dir / "http")
    pairs = _attempt(lambda: discover(cache, tax_year), tries)
    pair = pairs.get(str(county_code).zfill(2))
    if not pair:
        raise SourceUnavailable(f"No {tax_year} NAL+SDF pair is published for county code {county_code}.")
    work = settings.cache_dir / "fl"
    work.mkdir(parents=True, exist_ok=True)
    nal, sdf, meta = _attempt(lambda: load_pair(cache, pair, work), tries)
    nal = nal.drop_duplicates(subset=["PARCEL_ID"], keep="first")
    homes = prepare(nal)
    keep = [c for c in ROLL_COLUMNS if c in homes.columns]
    homes = homes[keep].copy()
    del nal
    sale_cols = [c for c in ("PARCEL_ID", "SALE_YR", "SALE_MO", "SALE_PRC", "QUAL_CD", "VI_CD", "OR_BOOK", "OR_PAGE",
                             "CLERK_NO", "SALE_ID_CD") if c in sdf.columns]
    q = sdf[sdf.QUAL_CD.isin(QUALIFIED) & (sdf.VI_CD == "I") & sdf.MULTI_PAR_SAL.isna() & (sdf.SALE_PRC > 20000)][sale_cols]
    home_cols = [c for c in ("PARCEL_ID", "DOR_UC", "NBRHD_CD", "NBRHD_ORIG", "MKT_AR", "peer_basis", "sqft", "eff", "land",
                             "JV", "PHY_ADDR1", "SPEC_FEAT_VAL", "LND_SQFOOT", "ACT_YR_BLT", "NO_BULDNG") if c in homes.columns]
    q = q.merge(homes[home_cols], on="PARCEL_ID", how="inner").dropna(subset=["SALE_YR", "SALE_MO"])
    q["ppsf"] = q.SALE_PRC / q.sqft
    q["ym"] = (q.SALE_YR * 12 + q.SALE_MO - 1).astype(int)
    vym = tax_year * 12
    idx, how = time_index(q, vym - 0.5)
    q["tadj"] = [idx.get(u, {}).get(ym, 1.0) for u, ym in zip(q.DOR_UC, q.ym)]
    pre = q[q.ym < vym]
    level, src = {}, {}
    for uc, fallback in DEFAULT_LEVEL.items():
        g = pre[pre.DOR_UC == uc]
        if len(g) >= 30:
            level[uc] = float((g.JV / (g.SALE_PRC * g.tadj)).median())
            src[uc] = (f"median county value / time-adjusted sale price over {len(g):,} qualified sales "
                       f"{MONTHS[int(g.ym.min()) % 12]} {int(g.ym.min()) // 12} to {MONTHS[int(g.ym.max()) % 12]} {int(g.ym.max()) // 12}")
        else:
            level[uc] = fallback
            src[uc] = "statewide default: too few local qualified sales to measure"
    s = sdf.dropna(subset=["SALE_YR", "SALE_MO"]).copy()
    s["ym"] = (s.SALE_YR * 12 + s.SALE_MO - 1).astype(int)
    files = []
    for kind in ("NAL", "SDF"):
        rf = pair[kind]
        man = cache.manifest.get(rf.url, {}) if hasattr(cache, "manifest") else {}
        files.append({"kind": kind, "url": rf.url, "sha256": meta[kind]["sha256"], "published": rf.modified,
                      "retrieved_at": man.get("fetched_at"), "roll_stage": rf.stage, "tax_year": rf.year,
                      "publisher": "Florida Department of Revenue, Property Tax Oversight data portal"})
    return CountyData(county=pair["NAL"].county, county_code=pair["NAL"].county_no, tax_year=pair["NAL"].year,
                      roll_stage=pair["NAL"].stage, homes=homes.reset_index(drop=True), all_sales=s,
                      qualified=q.reset_index(drop=True), time_index=idx, time_method=how, level=level,
                      level_source=src, files=files, valuation_ym=vym)


def as_str(v) -> str | None:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    v = str(v).strip()
    return v or None


def as_int(v) -> int | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(x) else int(round(x))


def resolve_address(cd: CountyData, address: str, city: str | None = None, zipcode: str | None = None) -> dict:
    import re
    from taxfind.engine.normalize import norm_street_series
    raw = (address or "").upper()
    m = re.search(r"\b(\d{5})(?:-\d{4})?\b\s*$", raw)
    zipcode = zipcode or (m.group(1) if m else None)
    street = re.split(r",", raw)[0].strip()
    want = norm_street_series(pd.Series([street])).iloc[0]
    if not want:
        return {"status": "unresolved", "reason": "no street address given", "candidates": []}
    h = cd.homes
    key = norm_street_series(h.PHY_ADDR1.astype("string").fillna(""))
    hit = h[key == want]
    if zipcode and "PHY_ZIPCD" in h.columns and len(hit) > 1:
        z = hit.PHY_ZIPCD.astype("string").str.replace(r"\\D", "", regex=True).str[:5]
        hit = hit[z == zipcode]
    if city and len(hit) > 1:
        hit = hit[hit.PHY_CITY.astype("string").str.upper().str.strip() == city.upper().strip()]
    cands = [{"parcel_id": r.PARCEL_ID, "address": as_str(r.PHY_ADDR1), "city": as_str(r.PHY_CITY)} for r in hit.head(10).itertuples()]
    if len(hit) == 1:
        return {"status": "resolved", "parcel_id": hit.iloc[0].PARCEL_ID, "matched": cands[0],
                "basis": "the owner's street address matched exactly one house or condo on the county roll"}
    if not len(hit):
        return {"status": "unresolved", "reason": "no house or condo on the county roll has this street address", "candidates": []}
    return {"status": "ambiguous", "reason": f"{len(hit)} parcels share this street address (often condo units); ask the owner for the unit or parcel number",
            "candidates": cands}
