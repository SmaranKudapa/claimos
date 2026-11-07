"""Synthetic Florida-format roll + sales: one neighborhood of similar houses where a few are planted
over-assessed, one condo building, and owners that test grouping."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxfind.config import ScreenParams

ROLL_YEAR = 2026


def make_roll(n: int = 60, seed: int = 0, overvalued: tuple[int, ...] = (0, 1, 2), homestead_capped: int = 3,
              nullable: bool = False):
    rng = np.random.default_rng(seed)
    rows, sales = [], []
    for i in range(n):
        sqft = float(rng.integers(1800, 2200))
        ppsf = 200.0 * rng.uniform(0.97, 1.03)
        jv = sqft * ppsf
        if i in overvalued:
            jv *= 1.40
        hm = i == homestead_capped
        rows.append({
            "CO_NO": "99", "PARCEL_ID": f"P{i:05d}", "DOR_UC": "001", "NBRHD_CD": "N1", "JV": round(jv),
            "JV_CHNG": np.nan, "AV_NSD": round(jv * (0.5 if hm else 1.0)), "TV_NSD": round(jv * (0.5 if hm else 1.0)),
            "AV_SD": round(jv * (0.5 if hm else 1.0)), "TV_SD": round(jv * (0.5 if hm else 1.0)),
            "JV_HMSTD": round(jv) if hm else np.nan, "LND_VAL": 60000.0, "EFF_YR_BLT": 2005.0, "ACT_YR_BLT": 2004.0,
            "TOT_LVG_AREA": sqft, "ALT_KEY": f"A{i}", "PHY_ADDR1": f"{100 + i} PALM ST", "PHY_ADDR2": pd.NA,
            "PHY_CITY": "TESTVILLE", "PHY_ZIPCD": "33900", "S_LEGAL": "PALM ESTATES LOT %d" % i,
            "OWN_NAME": "BIG INVESTOR LLC" if i in (0, 1) else f"OWNER{i} JOHN",
            "OWN_ADDR1": "1 WALL ST" if i in (0, 1) else f"{100 + i} PALM ST", "OWN_ADDR2": pd.NA,
            "OWN_CITY": "NEW YORK" if i in (0, 1) else "TESTVILLE", "OWN_STATE": "NY" if i in (0, 1) else "FL",
            "OWN_ZIPCD": "10005" if i in (0, 1) else "33900",
        })
        if 5 <= i < 5 + n // 2:   # sales of fairly valued homes in 2025, price = value / 0.85
            sales.append({"PARCEL_ID": f"P{i:05d}", "SALE_YR": 2025, "SALE_MO": int(1 + i % 12),
                          "SALE_PRC": round(sqft * ppsf / 0.85), "QUAL_CD": "01", "VI_CD": "I",
                          "MULTI_PAR_SAL": pd.NA, "SALE_ID_CD": f"S{i}", "CLERK_NO": f"C{i}"})
    # condo building: 12 units at one street address, unit only in owner mailing address
    for u in range(12):
        sqft = 1200.0
        jv = sqft * 250 * (1.45 if u == 0 else 1.0)
        rows.append({
            "CO_NO": "99", "PARCEL_ID": f"C{u:05d}", "DOR_UC": "004", "NBRHD_CD": "N2", "JV": round(jv), "JV_CHNG": np.nan,
            "AV_NSD": round(jv), "TV_NSD": round(jv), "AV_SD": round(jv), "TV_SD": round(jv), "JV_HMSTD": np.nan,
            "LND_VAL": 0.0, "EFF_YR_BLT": 2010.0,
            "ACT_YR_BLT": 2010.0, "TOT_LVG_AREA": sqft, "ALT_KEY": pd.NA, "PHY_ADDR1": "500 BEACH BLVD", "PHY_ADDR2": pd.NA,
            "PHY_CITY": "TESTVILLE", "PHY_ZIPCD": "33900", "S_LEGAL": "SEASIDE CONDO PH 1",
            "OWN_NAME": f"CONDO OWNER {u}", "OWN_ADDR1": f"500 BEACH BLVD #{100 + u}", "OWN_ADDR2": pd.NA,
            "OWN_CITY": "TESTVILLE", "OWN_STATE": "FL", "OWN_ZIPCD": "33900",
        })
        if u >= 4:
            sales.append({"PARCEL_ID": f"C{u:05d}", "SALE_YR": 2025, "SALE_MO": int(1 + u % 12),
                          "SALE_PRC": round(sqft * 250 / 0.80), "QUAL_CD": "01", "VI_CD": "I",
                          "MULTI_PAR_SAL": pd.NA, "SALE_ID_CD": f"SC{u}", "CLERK_NO": f"CC{u}"})
    nal = pd.DataFrame(rows)
    for c in ("JV", "AV_NSD", "TV_NSD", "AV_SD", "TV_SD", "JV_HMSTD"):
        nal[c] = nal[c].astype(float)
    if nullable:   # mimic pd.to_numeric on string columns: nullable Float64
        for c in ("JV", "AV_NSD", "TV_NSD", "JV_HMSTD", "LND_VAL", "TOT_LVG_AREA", "EFF_YR_BLT", "ACT_YR_BLT"):
            nal[c] = nal[c].astype("Float64")
    for c in ("PARCEL_ID", "DOR_UC", "NBRHD_CD", "PHY_ADDR1", "PHY_ADDR2", "PHY_CITY", "PHY_ZIPCD", "S_LEGAL", "ALT_KEY",
              "OWN_NAME", "OWN_ADDR1", "OWN_ADDR2", "OWN_CITY", "OWN_STATE", "OWN_ZIPCD", "CO_NO"):
        nal[c] = nal[c].astype("string")
    sdf = pd.DataFrame(sales)
    for c in ("PARCEL_ID", "QUAL_CD", "VI_CD", "MULTI_PAR_SAL", "SALE_ID_CD", "CLERK_NO"):
        sdf[c] = sdf[c].astype("string")
    return nal, sdf


@pytest.fixture
def roll():
    return make_roll()


@pytest.fixture
def params():
    # the synthetic data has few sales and flat months; loosen only the time-index month minimum
    return ScreenParams()
