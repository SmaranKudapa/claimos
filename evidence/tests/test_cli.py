from __future__ import annotations

import datetime as dt
import json

from claimevidence.cli import approvals, card_note, main
from claimevidence.engine import run

from .conftest import envelope

TODAY = dt.date(2026, 11, 7)
SHA = "a" * 64


def test_an_approval_line_binds_to_one_packet_and_a_later_rejection_wins():
    text = f"note\nAPPROVE EVIDENCE {SHA} FOR file_handoff, exchange_property_appraiser BY Fra Rosciano\n"
    got = approvals(text, SHA)
    assert got["status"] == "approved" and got["approved_for"] == ["file_handoff", "exchange_property_appraiser"]
    assert got["reviewed_by"] == "Fra Rosciano"
    assert approvals(text, "b" * 64) is None
    assert approvals("APPROVE EVIDENCE 1234 FOR file_handoff BY x") is None
    rejected = approvals(text + f"REJECT EVIDENCE {SHA} BY Fra: wrong comparable\n", SHA)
    assert rejected["status"] == "rejected" and rejected["approved_for"] == []


def test_card_note_is_blocked_until_review_signature_and_handoff_are_all_in_place(tmp_path, patched):
    unsigned = run(envelope(auth={}), tmp_path, today=TODAY)
    n = card_note(unsigned)
    assert n["status"] == "blocked" and n["note"].startswith("EVIDENCE READY FOR REVIEW")
    assert f"APPROVE EVIDENCE {unsigned['packet']['sha256']} FOR file_handoff BY" in n["note"]
    assert "nothing sent, exchanged or filed" in n["note"]
    review = {"packet_hash": unsigned["packet"]["sha256"], "status": "approved", "reviewed_by": "r", "reviewed_at": "2026-11-08",
              "approved_for": ["file_handoff"]}
    waiting = run(envelope(auth={}, prior_review=review), tmp_path, today=TODAY)
    assert card_note(waiting)["note"].startswith("EVIDENCE APPROVED, AWAITING SIGNATURE")
    signed_first = run(envelope(), tmp_path, today=TODAY)
    review["packet_hash"] = signed_first["packet"]["sha256"]
    done = run(envelope(prior_review=review), tmp_path, today=TODAY)
    n = card_note(done)
    assert n["status"] == "done" and n["note"].startswith("EVIDENCE COMPLETE")
    block = json.loads(n["note"].split("```json\n", 1)[1].split("\n```", 1)[0])
    assert block["packet_sha256"] == done["packet"]["sha256"] and block["evidence_status"] == "complete"


def test_replay_runs_are_labelled_and_never_complete(tmp_path, patched):
    first = run(envelope(), tmp_path, today=TODAY, as_of=dt.date(2026, 9, 1))
    review = {"packet_hash": first["packet"]["sha256"], "status": "approved", "reviewed_by": "r", "reviewed_at": "2026-11-08",
              "approved_for": ["file_handoff"]}
    res = run(envelope(prior_review=review), tmp_path, today=TODAY, as_of=dt.date(2026, 9, 1))
    n = card_note(res)
    assert "(replay)" in n["note"] and n["status"] == "blocked"
    assert any(r.startswith("replay:") for r in res["conclusions"]["not_ready_reasons"])


def test_build_input_supports_an_owner_free_check_without_a_find_record(tmp_path, capsys):
    assert main(["build-input", "--case-id", "FL-13-2026-30933354000", "--county-code", "13", "--tax-year", "2026",
                 "--parcel", "30933354000", "--entry-policy", "free_check"]) == 0
    inp = json.loads(capsys.readouterr().out)
    assert inp["appeal"]["jurisdiction"] == {"state": "FL", "county": "Bay", "county_code": "13"}
    assert inp["property"]["parcel_id"] == "30933354000" and inp["find"] == {} and inp["entry_policy"] == "free_check"
    assert main(["build-input", "--case-id", "x", "--county-code", "13", "--tax-year", "2026", "--parcel", "1"]) == 2


def test_the_requirements_matrix_prints_every_rule_with_its_source(capsys):
    assert main(["rules", "--matrix"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("| ID | Requirement") and "FL-EVX-01" in out and "floridarevenue.com" in out
