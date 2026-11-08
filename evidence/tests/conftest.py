from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from claimevidence.records import CountyData

YEAR = 2026
VYM = YEAR * 12


def _home(i, sqft, eff, land, jv, nb="N1", feat=0.0, homestead=False, av=None, tv=None, uc="001"):
    av = jv if av is None else av
    tv = av if tv is None else tv
    return {"PARCEL_ID": f"P{i:04d}", "DOR_UC": uc, "NBRHD_CD": nb, "NBRHD_ORIG": nb, "MKT_AR": "M1", "peer_basis": "neighborhood",
            "PHY_ADDR1": f"{100 + i} OAK ST", "PHY_CITY": "TESTVILLE", "PHY_ZIPCD": "32400", "JV": jv, "AV_SD": jv, "AV_NSD": av,
            "TV_SD": tv if not homestead else max(av - 50000, 0), "TV_NSD": tv if not homestead else max(av - 50000, 0),
            "JV_HMSTD": jv if homestead else 0.0, "LND_VAL": land, "SPEC_FEAT_VAL": feat, "TOT_LVG_AREA": sqft,
            "EFF_YR_BLT": eff, "ACT_YR_BLT": eff, "NO_BULDNG": 1, "TAX_AUTH_CD": "1", "sqft": float(sqft), "eff": float(eff),
            "land": float(land), "homestead": homestead, "ppsf": jv / sqft}


def build_county(subject_jv=400000.0, n_sales=12, subject_homestead=False, subject_av=None, own_sale=None, sale_price_ppsf=150.0,
                 spread=0.04, extra_homes=None):
    rng = np.random.default_rng(7)
    homes = [_home(0, 2000, 2005, 60000, subject_jv, homestead=subject_homestead, av=subject_av)]
    sales = []
    for i in range(1, 41):
        sqft = 2000 * float(np.exp(rng.uniform(-0.15, 0.15)))
        jv = 0.85 * sale_price_ppsf * sqft
        homes.append(_home(i, round(sqft), 2005 + int(rng.integers(-5, 6)), 60000 + int(rng.integers(-8000, 8000)), round(jv)))
    homes.append(_home(41, 4200, 2005, 60000, 0.85 * 150 * 4200))
    homes.append(_home(42, 2000, 1960, 60000, 0.85 * 150 * 2000))
    homes.append(_home(43, 2000, 2005, 400000, 0.85 * 150 * 2000))
    for h in extra_homes or []:
        homes.append(h)
    for i in range(1, 1 + n_sales):
        h = homes[i]
        price = sale_price_ppsf * h["sqft"] * float(np.exp(rng.uniform(-spread, spread)))
        sales.append({"PARCEL_ID": h["PARCEL_ID"], "SALE_YR": float(YEAR - 1), "SALE_MO": float(1 + (i % 12)), "SALE_PRC": round(price, -2),
                      "QUAL_CD": "01", "VI_CD": "I", "OR_BOOK": str(4000 + i), "OR_PAGE": str(10 * i), "CLERK_NO": f"C{i:05d}", "SALE_ID_CD": None})
    for idx in (41, 42, 43):
        h = homes[idx]
        sales.append({"PARCEL_ID": h["PARCEL_ID"], "SALE_YR": float(YEAR - 1), "SALE_MO": 6.0, "SALE_PRC": round(150 * h["sqft"], -2),
                      "QUAL_CD": "01", "VI_CD": "I", "OR_BOOK": "4999", "OR_PAGE": str(idx), "CLERK_NO": f"X{idx}", "SALE_ID_CD": None})
    sales.append({"PARCEL_ID": homes[5]["PARCEL_ID"], "SALE_YR": float(YEAR), "SALE_MO": 3.0, "SALE_PRC": 280000.0, "QUAL_CD": "01",
                  "VI_CD": "I", "OR_BOOK": "5100", "OR_PAGE": "1", "CLERK_NO": "LATE1", "SALE_ID_CD": None})
    if own_sale:
        sales.append({"PARCEL_ID": "P0000", "SALE_YR": float(own_sale[0]), "SALE_MO": float(own_sale[1]), "SALE_PRC": float(own_sale[2]),
                      "QUAL_CD": "01", "VI_CD": "I", "OR_BOOK": "4500", "OR_PAGE": "9", "CLERK_NO": "OWN1", "SALE_ID_CD": None})
    hdf = pd.DataFrame(homes)
    sdf = pd.DataFrame(sales)
    sdf["ym"] = (sdf.SALE_YR * 12 + sdf.SALE_MO - 1).astype(int)
    cols = ["PARCEL_ID", "DOR_UC", "NBRHD_CD", "NBRHD_ORIG", "MKT_AR", "peer_basis", "sqft", "eff", "land", "JV", "PHY_ADDR1",
            "SPEC_FEAT_VAL", "ACT_YR_BLT", "NO_BULDNG"]
    q = sdf.merge(hdf[cols], on="PARCEL_ID")
    q["ppsf"] = q.SALE_PRC / q.sqft
    q["tadj"] = 1.0
    files = [{"kind": k, "url": f"https://floridarevenue.com/test/{k}.zip", "sha256": ("a" if k == "NAL" else "b") * 64,
              "published": "2026-10-16T00:00:00Z", "retrieved_at": "2026-11-07T00:00:00Z", "roll_stage": "final", "tax_year": YEAR,
              "publisher": "Florida Department of Revenue"} for k in ("NAL", "SDF")]
    return CountyData(county="Testcounty", county_code="99", tax_year=YEAR, roll_stage="final", homes=hdf, all_sales=sdf,
                      qualified=q, time_index={"001": {int(m): 1.0 for m in sdf.ym}}, time_method={"001": "monthly, test"},
                      level={"001": 0.85, "004": 0.85}, level_source={"001": "test level", "004": "test level"}, files=files,
                      valuation_ym=VYM)


def find_payload(parcel="P0000", year=YEAR, county_code="99", schema=2, tier="strong", owner=None):
    return {"schema_version": schema, "case_id": f"FL-{county_code}-{year}-{parcel}", "tier": tier,
            "jurisdiction": {"state": "FL", "county": "Testcounty", "county_code": county_code, "tax_year": year,
                             "county_check": {"status": "validated"}},
            "property": {"parcel_id": parcel, "address": "100 OAK ST"},
            "estimate": {"defensible_value": 255000.0, "annual_savings": 2000.0},
            "owner": owner or {"name": "TEST OWNER", "may_have_changed": False},
            "outreach": {"owner_suppressed": False},
            "filing_window": {"closes": f"{year}-09-09", "verified": False, "basis": "estimate"},
            "source": {"run_id": "FL-TEST", "found_at": "2026-11-07T00:00:00Z", "roll_file": "https://floridarevenue.com/test/NAL.zip"}}


def envelope(parcel="P0000", case_id="case-A", auth=None, qualification=None, **kw):
    inp = {"schema": "claimos.evidence.input/1", "case_id": case_id,
           "appeal": {"tax_year": YEAR, "appeal_type": "vab_just_value", "jurisdiction": {"state": "FL", "county": "Testcounty", "county_code": "99"}},
           "property": {"parcel_id": parcel}, "find": find_payload(parcel),
           "qualification": qualification if qualification is not None else {"decision": "pursue", "ref": "q-1", "case_id": case_id, "tax_year": YEAR},
           "authorization": auth if auth is not None else {"status": "signed", "instrument": "power_of_attorney_dr486poa", "parcel_ids": [parcel],
                                                         "tax_year": YEAR, "document_ref": "fil_poa_test", "document_sha256": "c" * 64,
                                                         "signed_at": "2026-11-01", "signer_name": "TEST OWNER"},
           "consent": {"channels": ["portal"]}}
    inp.update(kw)
    return inp


@pytest.fixture
def county():
    return build_county()


@pytest.fixture
def patched(monkeypatch):
    state = {"county": build_county(), "loads": 0}

    def fake_load(code, year, data_dir=None, tries=3):
        state["loads"] += 1
        if state.get("fail"):
            from claimevidence.model import SourceUnavailable
            raise SourceUnavailable("ConnectionError: portal unreachable")
        return copy.deepcopy(state["county"])

    monkeypatch.setattr("claimevidence.engine.load_county", fake_load)
    return state
