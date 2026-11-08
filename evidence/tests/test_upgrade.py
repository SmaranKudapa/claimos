from __future__ import annotations

import copy
import datetime as dt
import json

from claimevidence.comps import analyze
from claimevidence.engine import run
from claimevidence.jurisdictions import resolve
from claimevidence.jurisdictions.florida import deadlines_for, forum, rules_for
from claimevidence.report import Doc
from claimevidence.validate import validate
from claimevidence.valuation import conclude

from .conftest import envelope

TODAY = dt.date(2026, 11, 7)


def _subject(cd, pid="P0000"):
    return cd.subject(pid)


def test_strong_evidence_explains_each_sale_and_separates_adjustments_from_the_conversion(tmp_path, patched):
    res = run(envelope(), tmp_path, today=TODAY)
    v, a = res["valuation"], res["analysis"]
    assert v["outcome"] == "supports_reduction"
    for c in a["selected"]:
        assert c["similarities"] and set(c["adjustment_detail"]) == {"time", "land", "special_features", "living_area"}
        assert all(d["support"] and d["formula"] for d in c["adjustment_detail"].values())
    g = v["bridge"]["gap"]
    assert g["total"] == g["county_value_above_market_indication"] + g["just_value_conversion"] + g["rounding"]
    conv = v["conversion"]
    assert "never stacked" in conv["applied"] and conv["distinct_from"].startswith("exemptions")
    assert a["reconciliation"]["sensitivity"]["recorded_prices_median"] > 0 and a["reconciliation"]["weighted_cross_check"] > 0


def test_sales_systematically_older_than_the_subject_go_to_review_instead_of_supporting_a_value(county):
    cd = copy.deepcopy(county)
    i = cd.homes.index[cd.homes.PARCEL_ID == "P0000"][0]
    cd.homes.loc[i, "eff"] = 2016.0
    cd.homes.loc[i, "EFF_YR_BLT"] = 2016
    s = _subject(cd)
    a = analyze(cd, s)
    assert a["reliability"] == "insufficient" and "older" in a["systematic_bias"]
    v = conclude(s, a, {"peers": 0}, [], None, 0.85)
    assert v["outcome"] == "insufficient_evidence" and v["proposed_just_value"] is None


def test_insufficient_sales_request_nothing(tmp_path, patched):
    from .conftest import build_county
    patched["county"] = build_county(n_sales=2)
    res = run(envelope(), tmp_path, today=TODAY)
    assert res["valuation"]["outcome"] == "insufficient_evidence" and res["valuation"]["bridge"] is None


def test_a_duplicated_conversion_or_an_unsupported_adjustment_fails_validation(tmp_path, patched):
    res = run(envelope(), tmp_path, today=TODAY)
    col = json.load(open(next(tmp_path.rglob("collected.json"))))
    fm = forum("vab_just_value", "Testcounty")
    d = Doc("Petitioner's evidence of value", "x")
    d.add("p", "Plain text.")
    val = copy.deepcopy(res["valuation"])
    lvl = val["just_value_indications"]["market_at_county_level"]
    lvl["value"] = round(lvl["value"] * val["county_level"])
    v = validate(d, None, None, {"appeal": res["appeal"]}, col, res["analysis"], val, fm, {}, [], [], None)
    assert any(c["id"] == "V-CALC-LEVEL" and c["status"] == "fail" for c in v["checks"])
    a = copy.deepcopy(res["analysis"])
    key = next(k for c in a["selected"] for k, amt in c["adjustments"].items() if amt)
    for c in a["selected"]:
        c["adjustment_detail"][key]["support"] = ""
    v = validate(d, None, None, {"appeal": res["appeal"]}, col, a, res["valuation"], fm, {}, [], [], None)
    assert any(c["id"] == "V-ADJ-SUPPORT" and c["status"] == "fail" for c in v["checks"])


def test_later_sales_that_point_to_the_county_value_are_flagged_as_a_conflict(county):
    s = _subject(county)
    a = analyze(county, s)
    a["subsequent_sales"] = [{"parcel_id": f"L{i}", "address": "x", "sale_month": "2026-05", "sale_price": 600000, "sqft": 2000,
                              "location": "same county neighborhood as the subject", "time_factor": 1.0, "time_adjusted_price": 600000,
                              "effective_year_built": 2005, "county_just_value": 500000} for i in range(3)]
    v = conclude(s, a, {"peers": 0}, [], None, 0.85)
    assert v["later_sales"]["conflict"] is True and v["later_sales"]["contrary"] == 3


def test_hearing_formats_switch_the_delivery_obligations(tmp_path, patched):
    env = envelope()
    expect = {"remote": "remote_vab_upload", "in_person": "hearing_copies", "absent": "absent_petitioner_filing"}
    for fmt, keep in expect.items():
        e = copy.deepcopy(env)
        e["appeal"]["hearing_format"] = fmt
        res = run(e, tmp_path / fmt, today=TODAY)
        d = res["delivery"]["deliveries"]
        assert d[keep] == "not_sent"
        assert all(d[x] == "not_applicable" for x in expect.values() if x != keep)
        assert d["appraiser_exchange_incoming"] == "not_received" and d["petition_dr486"] == "not_filed"


def test_deadlines_carry_recipient_timezone_and_a_separate_internal_target():
    d = deadlines_for("Bay", 2026, "2026-12-02", TODAY)
    ex = d["evidence_exchange_petitioner"]
    assert ex["date"] == "2026-11-17" and ex["recipient"] == "property appraiser" and ex["timezone"] == "America/Chicago" and ex["legal"]
    assert ex["internal_target"]["legal"] is False and ex["internal_target"]["date"] < ex["date"]
    assert d["remote_evidence_upload"]["time"] == "09:00"
    assert deadlines_for("Lee", 2026, "2026-12-02", TODAY)["hearing"]["timezone"] == "America/New_York"


def test_rules_are_versioned_by_effective_date():
    before = {r["id"] for r in rules_for("Bay", "vab_just_value", "fl_vab_value_petition", "2025-06-01")}
    after = {r["id"] for r in rules_for("Bay", "vab_just_value", "fl_vab_value_petition", "2026-11-10")}
    assert "FL-EVX-02-PRE2025" in before and "FL-EVX-03" not in before
    assert "FL-EVX-02-PRE2025" not in after and {"FL-EVX-03", "FL-HRG-02"} <= after


def test_an_unsupported_state_gets_no_florida_rules_and_no_packet(tmp_path, patched):
    assert resolve("GA")["status"] == "unsupported" and resolve("fl")["status"] == "supported"
    env = envelope()
    env["appeal"]["jurisdiction"]["state"] = "GA"
    res = run(env, tmp_path, today=TODAY)
    assert res["jurisdiction_support"]["status"] == "unsupported"
    assert res["intake"]["status"] == "blocked" and res["packet"] is None and res["rules_applied"] == [] and res["deadlines"] == {}
    assert patched["loads"] == 0


def test_a_missing_county_code_blocks_intake(tmp_path, patched):
    env = envelope()
    env["appeal"]["jurisdiction"]["county_code"] = None
    res = run(env, tmp_path, today=TODAY)
    assert res["intake"]["status"] == "blocked" and res["packet"] is None


def test_presentation_and_substance_are_checked_separately(tmp_path, patched):
    res = run(envelope(), tmp_path, today=TODAY)
    v = res["validation"]
    assert v["presentation"] == "passed" and v["substance"] == "passed"
    kinds = {c["kind"] for c in v["checks"]}
    assert kinds == {"presentation", "substance"}
    assert any(c["id"] == "V-LAYOUT-ORPHAN" for c in v["checks"])
    assert res["readiness"]["presentation_check"] == "passed" and res["readiness"]["substance_check"] == "passed"


def test_the_text_follows_the_data_and_carries_no_sample_specific_wording(tmp_path, patched):
    from claimevidence.report import m
    outs = [run(envelope(parcel=p, case_id=f"case-{p}"), tmp_path, today=TODAY) for p in ("P0000", "P0001")]
    texts = []
    for res in outs:
        md = open(res["packet"]["markdown_path"]).read()
        texts.append(md)
        v = res["valuation"]
        assert m(v["county_values"]["just_value"]) in md
        if v["outcome"] == "supports_reduction":
            assert m(v["proposed_just_value"]) in md and m(v["market_value_indication"]) in md
        for word in ("Bay", "Weekend", "Redfish", "Panama", "Margaritaville", "Lagoon", "571,444", "476,100"):
            assert word not in md, word
        assert res["appeal"]["parcel_id"] in md
    assert texts[0] != texts[1]


def test_conditional_sections_are_omitted_with_a_recorded_reason(tmp_path, patched):
    res = run(envelope(), tmp_path, today=TODAY)
    omitted = {o["section"] for o in res["packet"]["omitted_sections"]}
    assert "Witness evidence" in omitted and "Condition evidence" in omitted
    md = open(res["packet"]["markdown_path"]).read()
    assert "Witness evidence" not in md.split("| Witness contact information")[1].split("\n", 1)[1]
    internal = open(res["packet"]["internal_record_path"]).read()
    assert "Sections omitted" in internal and "Witness evidence: no witness has been identified" in internal


def test_a_no_value_review_is_not_addressed_to_the_board_and_lists_the_sales_it_rejected(tmp_path, patched, county):
    cd = copy.deepcopy(county)
    i = cd.homes.index[cd.homes.PARCEL_ID == "P0000"][0]
    cd.homes.loc[i, "eff"] = 2016.0
    cd.homes.loc[i, "EFF_YR_BLT"] = 2016
    patched["county"] = cd
    res = run(envelope(), tmp_path, today=TODAY)
    assert res["valuation"]["outcome"] == "insufficient_evidence"
    md = open(res["packet"]["markdown_path"]).read()
    assert "BEFORE THE" not in md and "EVIDENCE REVIEW — NOT FOR SUBMISSION" in md
    assert "internal Claim OS screen" in md and "ranked by similarity and not used" in md
    for x in (res["valuation"].get("later_sales") or {}).get("sales", []):
        assert x["relation"] in ("supports the county value", "below the county value")
