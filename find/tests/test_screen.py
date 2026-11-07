import datetime as dt

from taxfind.desks.property_tax import florida
from taxfind.desks.property_tax.florida.source import FILE_RE, RollFile, latest_pairs
from taxfind.desks.property_tax.screen import evidence, screen
from taxfind.engine.people import attach_owners, portfolio_rollup

from .conftest import ROLL_YEAR


def test_flags_planted_overvalued_houses(roll, params):
    nal, sdf = roll
    r, aux = screen(nal, sdf, ROLL_YEAR, params)
    t = r.set_index("PARCEL_ID").tier
    assert t["P00000"] in ("strong", "possible") and t["P00001"] in ("strong", "possible") and t["P00002"] in ("strong", "possible")
    fair = [f"P{i:05d}" for i in range(4, 60)]
    assert (t[fair] == "none").mean() > 0.95


def test_homestead_cap_absorbs_savings(roll, params):
    nal, sdf = roll
    nal.loc[nal.PARCEL_ID == "P00003", "JV"] *= 1.4          # over-assessed but taxed on half
    nal.loc[nal.PARCEL_ID == "P00003", "JV_HMSTD"] = nal.loc[nal.PARCEL_ID == "P00003", "JV"]
    nal.loc[nal.PARCEL_ID == "P00003", ["AV_SD", "TV_SD"]] = nal.loc[nal.PARCEL_ID == "P00003", ["AV_NSD", "TV_NSD"]].values
    r, _ = screen(nal, sdf, ROLL_YEAR, params)
    row = r.set_index("PARCEL_ID").loc["P00003"]
    assert row.tier == "cap_absorbs" and row.est_savings == 0


def test_condo_flagged_and_level_measured(roll, params):
    nal, sdf = roll
    r, aux = screen(nal, sdf, ROLL_YEAR, params)
    assert r.set_index("PARCEL_ID").loc["C00000"].tier in ("strong", "possible", "review")
    assert abs(aux["stats"]["level"]["001"] - 0.85) < 0.03


def test_savings_math(roll, params):
    nal, sdf = roll
    r, _ = screen(nal, sdf, ROLL_YEAR, params)
    row = r.set_index("PARCEL_ID").loc["P00000"]
    assert row.defensible_value < row.JV
    assert abs(row.est_savings - (row.AV_NSD - row.defensible_value) * params.millage) < 1e-6


def test_evidence_lists(roll, params):
    nal, sdf = roll
    r, aux = screen(nal, sdf, ROLL_YEAR, params)
    flagged = r[r.tier.isin(["strong", "possible"])]
    ev = evidence(r, aux["comps"], flagged, params)
    e = ev["P00000"]
    assert 1 <= len(e["neighbors"]) <= 8 and 1 <= len(e["sales"]) <= 8
    assert all(n["parcel_id"] != "P00000" for n in e["neighbors"])
    assert all(s["sale_month"].startswith("2025") for s in e["sales"])


def test_payload_contract(roll, params):
    nal, sdf = roll
    nal = attach_owners(nal)
    r, aux = screen(nal, sdf, ROLL_YEAR, params)
    fl = r[r.tier.isin(florida.EXPORT_TIERS)]
    fl = portfolio_rollup(fl.assign(_sav=fl.est_savings), "_sav")
    pair = {k: RollFile("Test", "99", "final", k, ROLL_YEAR, f"https://x/{k}.zip", 1, "2026-10-01") for k in ("NAL", "SDF")}
    pl = florida.build_payloads(fl, evidence(r, aux["comps"], fl, params), pair, "run1", today=dt.date(2026, 11, 5))
    p = next(x for x in pl if x["property"]["parcel_id"] == "P00000")
    assert p["case_id"] == "FL-99-2026-P00000" and p["schema_version"] == 1
    assert p["owner"]["flagged_parcels_in_run"] >= 1 and p["owner"]["type"] == "company"
    assert p["filing_window"]["status"] == "closed" and p["filing_window"]["closes"] == "2026-09-09"
    c = next(x for x in pl if x["property"]["parcel_id"] == "C00000")
    assert c["property"]["unit"] == "100" and c["property"]["unit_source"] == "mailing_address"


def test_filing_window_states():
    assert florida.filing_window(2027, dt.date(2027, 3, 1))["status"] == "upcoming"
    assert florida.filing_window(2027, dt.date(2027, 8, 20))["status"] == "open"


def test_portal_filename_and_latest_pair():
    assert FILE_RE.match("Lee 46 Final NAL 2026.zip")["county"] == "Lee"
    assert FILE_RE.match("St. Johns 65 Preliminary SDF 2026.zip")["stage"] == "Preliminary"
    mk = lambda kind, stage, yr: RollFile("X", "11", stage, kind, yr, "u", 1, "")  # noqa: E731
    files = [mk("NAL", "preliminary", 2026), mk("SDF", "preliminary", 2026), mk("NAL", "final", 2026),
             mk("SDF", "final", 2026), mk("NAL", "final", 2027)]
    best = latest_pairs(files)
    assert best["11"]["NAL"].stage == "final" and best["11"]["NAL"].year == 2026   # 2027 has no SDF yet


def test_county_selection_aliases():
    from taxfind.pipeline import select
    pairs = {no: {"NAL": RollFile(name, no, "final", "NAL", 2026, "u", 1, "")}
             for no, name in (("23", "Dade"), ("65", "Saint Johns"), ("46", "Lee"), ("60", "Palm Beach"))}
    assert set(select(pairs, ["Miami-Dade", "St. Johns", "palm beach", "46"])) == {"23", "65", "60", "46"}
    assert select(pairs, "all") == pairs


def test_condos_compared_within_their_building(params):
    """Two condo buildings in one neighborhood: a Gulf-front tower at $400/sqft and a back-bay
    building at $250/sqft, all fairly valued. Comparing across buildings would flag the tower."""
    import numpy as np
    import pandas as pd
    rows, sales = [], []
    for b, (street, ppsf) in enumerate((("100 GULF DR", 400.0), ("900 BAY RD", 250.0))):
        for u in range(15):
            pid = f"B{b}U{u:02d}"
            jv = 1300 * ppsf
            rows.append({"PARCEL_ID": pid, "DOR_UC": "004", "NBRHD_CD": "400000", "JV": jv, "AV_NSD": jv, "TV_NSD": jv,
                         "JV_HMSTD": np.nan, "LND_VAL": 0.0, "EFF_YR_BLT": 2008.0, "ACT_YR_BLT": 2008.0, "TOT_LVG_AREA": 1300.0,
                         "PHY_ADDR1": street, "PHY_ZIPCD": "32413", "MKT_AR": "1"})
            if u < 8:
                sales.append({"PARCEL_ID": pid, "SALE_YR": 2025, "SALE_MO": 1 + u, "SALE_PRC": jv / 0.80, "QUAL_CD": "01",
                              "VI_CD": "I", "MULTI_PAR_SAL": pd.NA})
    nal = pd.DataFrame(rows).astype({"PARCEL_ID": "string", "DOR_UC": "string", "NBRHD_CD": "string",
                                     "PHY_ADDR1": "string", "PHY_ZIPCD": "string", "MKT_AR": "string"})
    sdf = pd.DataFrame(sales).astype({"PARCEL_ID": "string", "QUAL_CD": "string", "VI_CD": "string", "MULTI_PAR_SAL": "string"})
    r, aux = screen(nal, sdf, ROLL_YEAR, params)
    assert (r.peer_basis == "building").all()
    assert (r.tier == "none").all()


def test_own_sale_contradiction_goes_to_review(roll, params):
    import pandas as pd
    nal, sdf = roll
    jv = float(nal.loc[nal.PARCEL_ID == "P00000", "JV"].item())
    own = pd.DataFrame([{"PARCEL_ID": "P00000", "SALE_YR": 2025, "SALE_MO": 6, "SALE_PRC": jv / 0.80, "QUAL_CD": "01",
                         "VI_CD": "I", "MULTI_PAR_SAL": pd.NA, "SALE_ID_CD": "X", "CLERK_NO": "X"}]).astype(
        {"PARCEL_ID": "string", "QUAL_CD": "string", "VI_CD": "string", "MULTI_PAR_SAL": "string",
         "SALE_ID_CD": "string", "CLERK_NO": "string"})
    r, aux = screen(nal, pd.concat([sdf, own], ignore_index=True), ROLL_YEAR, params)
    row = r.set_index("PARCEL_ID").loc["P00000"]
    assert row.own_sale_contradicts and row.tier == "review"
    assert aux["stats"]["own_sale_demoted"] >= 1


def test_holdout_self_check_reported(roll, params):
    nal, sdf = roll
    r, aux = screen(nal, sdf, ROLL_YEAR, params)
    assert aux["stats"]["holdout"]["status"] == "untested"     # no sales after Jan 1 in the fixture
    assert 0 < aux["stats"]["coverage"] <= 1


def test_nullable_numeric_columns_do_not_break_payloads(params):
    """Real rolls load as nullable floats; NaN comparisons must not leak NA into flags."""
    from .conftest import make_roll
    nal, sdf = make_roll(nullable=True)
    nal = attach_owners(nal)
    r, aux = screen(nal, sdf, ROLL_YEAR, params)
    fl = r[r.tier.isin(florida.EXPORT_TIERS)]
    fl = portfolio_rollup(fl.assign(_sav=fl.est_savings), "_sav")
    pair = {k: RollFile("Test", "99", "final", k, ROLL_YEAR, "u", 1, "") for k in ("NAL", "SDF")}
    pl = florida.build_payloads(fl, {}, pair, "r", today=dt.date(2026, 11, 5), county_check=aux["stats"]["holdout"])
    assert pl and all(isinstance(p["signals"]["own_sale_contradicts"], bool) for p in pl)


def test_fully_exempt_home_saves_nothing(roll, params):
    nal, sdf = roll
    nal.loc[nal.PARCEL_ID == "P00000", ["TV_NSD", "TV_SD"]] = 0.0
    r, _ = screen(nal, sdf, ROLL_YEAR, params)
    row = r.set_index("PARCEL_ID").loc["P00000"]
    assert row.est_savings == 0 and row.tier == "cap_absorbs"


def test_school_levy_counts_when_the_10pct_cap_absorbs_the_rest(roll, params):
    """Non-homestead: AV_NSD capped below the defensible value, AV_SD (no cap) still above it."""
    nal, sdf = roll
    i = nal.PARCEL_ID == "P00001"
    jv = float(nal.loc[i, "JV"].item())
    nal.loc[i, ["AV_NSD", "TV_NSD"]] = jv * 0.5
    r, _ = screen(nal, sdf, ROLL_YEAR, params)
    row = r.set_index("PARCEL_ID").loc["P00001"]
    assert row.taxable_cut == 0 and row.taxable_cut_school > 0
    assert abs(row.est_savings - row.taxable_cut_school * params.millage_school) < 1e-6


def test_later_sale_demotes_but_not_the_self_check(roll, params):
    import pandas as pd
    nal, sdf = roll
    jv = float(nal.loc[nal.PARCEL_ID == "P00000", "JV"].item())
    later = pd.DataFrame([{"PARCEL_ID": "P00000", "SALE_YR": 2026, "SALE_MO": 4, "SALE_PRC": jv / 0.80, "QUAL_CD": "01",
                           "VI_CD": "I", "MULTI_PAR_SAL": pd.NA, "SALE_ID_CD": "L", "CLERK_NO": "L"}]).astype(
        {"PARCEL_ID": "string", "QUAL_CD": "string", "VI_CD": "string", "MULTI_PAR_SAL": "string",
         "SALE_ID_CD": "string", "CLERK_NO": "string"})
    r, aux = screen(nal, pd.concat([sdf, later], ignore_index=True), ROLL_YEAR, params)
    row = r.set_index("PARCEL_ID").loc["P00000"]
    assert row.tier == "review" and row.own_sale_contradicts
    assert row.deed_since_roll_ym == 2026 * 12 + 3
    assert aux["stats"]["holdout"]["flagged_sold"] == 1     # counted as flagged in the self-check


def test_calendar_covers_florida_and_flags_gaps():
    from taxfind.desks.property_tax.jurisdictions import JURISDICTIONS, calendar
    fl = next(j for j in JURISDICTIONS if j["id"] == "FL")
    assert fl["status"] == "live" and fl["months"] == [8, 9]
    out = calendar()
    assert "Florida" in out and "months with no live/next window" in out
