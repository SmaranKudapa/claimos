from __future__ import annotations

import copy
import datetime as dt

from claimevidence.intake import run_intake

from .conftest import YEAR, envelope, find_payload


def _blocked(inp, code):
    r = run_intake(inp, dt.date(2026, 11, 7))
    return r["status"] == "blocked" and any(b["code"] == code for b in r["blockers"]), r


def test_a_complete_signed_qualified_case_is_accepted():
    r = run_intake(envelope(), dt.date(2026, 11, 7))
    assert r["status"] == "accepted" and r["cycle_id"] == f"FL-99-{YEAR}-P0000/vab_just_value"


def test_find_record_for_another_year_is_rejected_so_cycles_never_mix():
    inp = envelope()
    inp["find"] = find_payload(year=YEAR - 1)
    ok, _ = _blocked(inp, "I07")
    assert ok


def test_find_record_for_another_parcel_is_rejected():
    inp = envelope()
    inp["find"] = find_payload(parcel="P0001")
    ok, _ = _blocked(inp, "I06")
    assert ok


def test_missing_authorization_blocks_and_routes_to_signup():
    ok, r = _blocked(envelope(auth={}), "I11")
    assert ok and r["route"] in ("signup", "coordinator", "operator")
    assert any(b["resolver"] == "signup" for b in r["blockers"])


def test_authorization_for_another_year_or_parcel_is_rejected():
    for change in ({"tax_year": YEAR - 1}, {"parcel_ids": ["P9999"]}, {"document_sha256": None}):
        inp = envelope()
        inp["authorization"] = {**inp["authorization"], **change}
        ok, _ = _blocked(inp, "I11")
        assert ok, change


def test_uncompensated_written_authorization_cannot_support_a_fee_based_engagement():
    inp = envelope()
    inp["authorization"] = {**inp["authorization"], "instrument": "written_authorization_dr486a"}
    ok, r = _blocked(inp, "I11")
    assert ok and "uncompensated" in r["blockers"][0]["message"]


def test_internal_test_authorization_allows_preparation_but_never_filing():
    r = run_intake(envelope(auth={"status": "internal_test", "instrument": "internal_test"}), dt.date(2026, 11, 7))
    assert r["status"] == "accepted" and r["authorization_is_test"]
    assert any(b["code"] == "I11" for b in r["file_blockers"])


def test_missing_qualification_blocks_and_routes_to_qualify():
    ok, r = _blocked(envelope(qualification={}), "I10")
    assert ok and any(b["resolver"] == "qualify" for b in r["blockers"])


def test_stale_find_schema_and_unsupported_appeal_types_are_blocked():
    inp = envelope()
    inp["find"] = find_payload(schema=1)
    assert _blocked(inp, "I08")[0]
    inp = envelope()
    inp["appeal"]["appeal_type"] = "vab_exemption_denial"
    assert _blocked(inp, "I04")[0]


def test_a_changed_owner_is_flagged_before_filing():
    inp = envelope()
    inp["find"] = find_payload(owner={"name": "X", "may_have_changed": True, "deed_since_roll": "2026-04"})
    r = run_intake(inp, dt.date(2026, 11, 7))
    assert r["status"] == "accepted" and any(b["code"] == "I12" for b in r["file_blockers"])
