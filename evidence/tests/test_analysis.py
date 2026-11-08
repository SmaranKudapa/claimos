from __future__ import annotations

import pandas as pd

from claimevidence.comps import CompParams, analyze, subject_sales
from claimevidence.valuation import conclude, round_value

from .conftest import YEAR, build_county


def _subject(cd):
    return cd.subject("P0000")


def test_suitable_comparables_are_selected_and_unsuitable_ones_are_excluded_with_reasons(county):
    a = analyze(county, _subject(county))
    assert len(a["selected"]) == 6
    assert a["indication"]["comparables"] == 6
    excluded = {e["parcel_id"]: {r["code"] for r in e["excluded_because"]} for e in a["excluded_nearest"]}
    assert "SIZE" in excluded["P0041"]
    assert "AGE" in excluded["P0042"]
    assert "LAND" in excluded["P0043"]
    assert all("P004" not in c["parcel_id"] for c in a["selected"])


def test_sales_after_the_valuation_date_are_disclosed_but_never_used(county):
    a = analyze(county, _subject(county))
    assert any(s["sale_month"] == f"{YEAR}-03" for s in a["subsequent_sales"])
    assert all(c["sale_month"] < f"{YEAR}-01" for c in a["selected"])


def test_adjustment_arithmetic_is_exact_and_reproducible(county):
    a = analyze(county, _subject(county))
    for c in a["selected"]:
        assert c["indicated_value"] == c["sale_price"] + c["net_adjustment"]
        assert abs(sum(c["adjustments"].values()) - c["net_adjustment"]) <= 2
    s = _subject(county)
    c = a["selected"][0]
    expected_size = round((s.sqft - c["sqft"]) * a["building_rate_per_sqft"])
    assert abs(c["adjustments"]["living_area"] - expected_size) <= 1 + abs(s.sqft - c["sqft"]) * 0.01
    assert analyze(county, s) == a


def test_too_few_sales_is_insufficient_evidence_not_a_finding_on_the_merits():
    cd = build_county(n_sales=2)
    a = analyze(cd, cd.subject("P0000"))
    assert a["indication"] is None and a["reliability"] == "insufficient"
    v = conclude(cd.subject("P0000"), a, {"peers": 0}, [], None, 0.85)
    assert v["outcome"] == "insufficient_evidence" and v["proposed_just_value"] is None and v["tax_estimate"] is None


def test_disagreeing_sales_are_insufficient_and_agreeing_sales_are_not():
    agree = build_county(spread=0.04)
    assert analyze(agree, agree.subject("P0000"))["reliability"] == "good"
    cd = build_county(spread=0.9, n_sales=12)
    a = analyze(cd, cd.subject("P0000"), CompParams(outlier_iqr=50))
    assert a["dispersion_cod"] > 0.25 and a["reliability"] == "insufficient"


def test_market_value_assessed_taxable_and_savings_are_kept_separate(county):
    s = _subject(county)
    a = analyze(county, s)
    v = conclude(s, a, {"peers": 0}, [], None, 0.85)
    assert v["outcome"] == "supports_reduction"
    assert v["proposed_just_value"] == round_value(v["market_value_indication"] * 0.85)
    assert v["proposed_just_value"] % 100 == 0
    e = v["effects"]
    assert e["just_value_reduction"] == v["county_values"]["just_value"] - v["proposed_just_value"]
    assert e["taxable_reduction_school"] <= e["assessed_reduction_school"]
    t = v["tax_estimate"]
    assert t["rate_basis"] == "assumed" and t["annual_savings_range"][0] < t["annual_savings"] < t["annual_savings_range"][1]
    assert "Not a result" in t["caveat"]


def test_a_save_our_homes_cap_can_absorb_the_whole_reduction():
    cd = build_county(subject_jv=400000.0, subject_homestead=True, subject_av=180000.0)
    s = cd.subject("P0000")
    v = conclude(s, analyze(cd, s), {"peers": 0}, [], None, 0.85)
    assert v["outcome"] == "supports_reduction"
    assert v["effects"]["assessed_reduction_non_school"] == 0
    assert v["tax_estimate"]["annual_savings"] < 2500
    assert "Save Our Homes" in v["effects"]["note"]


def test_the_subjects_own_sale_can_contradict_the_claim():
    cd = build_county(own_sale=(YEAR - 1, 9, 480000))
    s = cd.subject("P0000")
    own = subject_sales(cd, s)
    v = conclude(s, analyze(cd, s), {"peers": 0}, own, None, 0.85)
    assert v["outcome"] == "contradicted" and v["proposed_just_value"] is None


def test_a_fairly_assessed_home_does_not_support_a_reduction():
    cd = build_county(subject_jv=0.85 * 150 * 2000)
    s = cd.subject("P0000")
    v = conclude(s, analyze(cd, s), {"peers": 0}, [], None, 0.85)
    assert v["outcome"] == "does_not_support"


def test_a_material_difference_from_find_is_routed_back_to_qualify(county):
    s = _subject(county)
    v = conclude(s, analyze(county, s), {"peers": 0}, [], {"tier": "strong", "estimate": {"defensible_value": 380000.0}}, 0.85)
    assert v["versus_find"]["material_change"] is True and v["versus_find"]["route"] == "requalify"
    assert v["versus_find"]["find_defensible_value"] == 380000


def test_time_adjustment_moves_each_sale_to_the_valuation_date():
    cd = build_county()
    rising = {int(m): 1.0 + 0.01 * (YEAR * 12 - int(m)) for m in cd.qualified.ym}
    cd.time_index = {"001": rising}
    cd.qualified["tadj"] = [rising[int(m)] for m in cd.qualified.ym]
    s = cd.subject("P0000")
    a = analyze(cd, s)
    for c in a["selected"]:
        months_before = YEAR * 12 - (int(c["sale_month"][:4]) * 12 + int(c["sale_month"][5:]) - 1)
        assert c["time_factor"] == round(1.0 + 0.01 * months_before, 4)
        assert abs(c["adjustments"]["time"] - round(c["sale_price"] * (c["time_factor"] - 1))) <= 1
        assert c["adjustments"]["time"] > 0
    flat = analyze(build_county(), build_county().subject("P0000"))
    assert a["indication"]["market_value"] > flat["indication"]["market_value"]
