from __future__ import annotations

import json
import threading

import pytest

from claimevidence.engine import Busy, run, _lock
from claimevidence.handoff import check_handoff

from .conftest import envelope


def test_end_to_end_signed_case_produces_a_packet_and_a_structured_result(tmp_path, patched):
    res = run(envelope(), tmp_path)
    assert res["schema"] == "claimos.evidence.result/1"
    assert res["run"]["processing_status"] == "completed"
    assert res["conclusions"]["argument_support"] == "supports_reduction"
    assert res["conclusions"]["package_complete"] is True
    p = res["packet"]
    md = open(p["markdown_path"]).read()
    assert "Petitioner's evidence of value" in md and "Value requested" in md and "Not yet assigned" in md
    assert "| Petitioner | TEST OWNER |" in md
    assert "fil_poa_test" not in md and "annual" not in md.lower() and "appraisal" not in md.lower()
    assert open(p["pdf_path"], "rb").read(5) == b"%PDF-" and p["sha256"] == p["content_hash"]
    assert res["validation"]["status"] == "validated_against_configured_requirements"
    rd = res["readiness"]
    assert rd["generation"] == "generated" and rd["human_review"] == "not_reviewed" and rd["approval"] == "not_approved"
    assert set(rd["delivery"].values()) <= {"not_sent", "not_filed"}
    assert json.load(open(res["file_handoff"]["evidence_json"]))["status"] == "incomplete"
    for item in res["inventory"]:
        assert item["evidence_id"].startswith("ev-") and item["source"]
    assert res["review"]["human_review_required"] and res["review"]["filing_approval_required"]
    assert {"petition_filing", "evidence_exchange_petitioner", "evidence_exchange_appraiser", "hearing", "circuit_court"} <= set(res["deadlines"])


def test_duplicate_events_return_the_same_result_without_reprocessing(tmp_path, patched):
    a = run(envelope(), tmp_path)
    b = run(envelope(), tmp_path)
    assert b["run"]["duplicate_of"] == a["run"]["run_id"] and patched["loads"] == 1


def test_an_interrupted_run_resumes_from_its_checkpoint(tmp_path, patched, monkeypatch):
    calls = {"n": 0}
    import claimevidence.engine as eng
    real = eng.build_report

    def crash_once(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("worker killed")
        return real(*a, **k)

    monkeypatch.setattr(eng, "build_report", crash_once)
    with pytest.raises(RuntimeError):
        run(envelope(), tmp_path)
    res = run(envelope(), tmp_path)
    assert res["run"]["processing_status"] == "completed" and patched["loads"] == 1


def test_a_second_worker_cannot_process_the_same_cycle_concurrently(tmp_path):
    lock = tmp_path / "cycle" / ".lock"
    _lock(lock)
    with pytest.raises(Busy):
        _lock(lock)


def test_a_source_outage_is_a_retryable_processing_failure_not_a_merits_finding(tmp_path, patched):
    patched["fail"] = True
    res = run(envelope(), tmp_path)
    assert res["run"]["processing_status"] == "failed"
    assert res["run"]["errors"][0]["retryable"] is True
    assert res["conclusions"]["argument_support"] == "not_analyzed"
    assert res["next_action"]["action"] == "retry_evidence"


def test_new_evidence_makes_an_earlier_review_stale(tmp_path, patched):
    first = run(envelope(), tmp_path)
    reviewed = {"packet_hash": first["packet"]["sha256"], "status": "approved", "reviewed_by": "op", "reviewed_at": "2026-11-07",
                "approved_for": ["exchange_property_appraiser"]}
    same = run(envelope(prior_review=reviewed), tmp_path)
    assert same["review"]["status"] == "approved" and not same["review"]["stale"]
    sub = [{"id": "h1", "kind": "photo", "media_type": "image/jpeg", "file_ref": "fil_x", "sha256": "d" * 64,
            "document_date": "2025-12-20", "asserts": "condition", "description": "Roof damage"}]
    changed = run(envelope(prior_review=reviewed, homeowner_submissions=sub), tmp_path)
    assert changed["packet"]["content_hash"] != first["packet"]["content_hash"]
    assert changed["review"]["stale"] is True and changed["review"]["status"] == "pending"
    assert changed["packet"]["version"] > first["packet"]["version"]


def test_corrupt_and_wrong_type_uploads_are_rejected_and_undated_ones_are_limited(tmp_path, patched):
    subs = [{"id": "bad", "kind": "photo", "media_type": "image/jpeg", "file_ref": "fil_1", "sha256": "e" * 64, "integrity": "corrupt",
             "document_date": "2025-12-01"},
            {"id": "exe", "kind": "photo", "media_type": "application/x-msdownload", "file_ref": "fil_2", "sha256": "f" * 64},
            {"id": "nodate", "kind": "photo", "media_type": "image/png", "file_ref": "fil_3", "sha256": "0" * 64},
            {"id": "say", "kind": "statement", "statement_text": "The roof leaked before January.", "asserts": "condition"}]
    res = run(envelope(homeowner_submissions=subs), tmp_path)
    by = {i["source"].get("file_ref") or i["kind"]: i for i in res["inventory"] if i["kind"].startswith("homeowner_")}
    assert by["fil_1"]["verification"] == "rejected_corrupt" and not by["fil_1"]["county_facing"]
    assert by["fil_2"]["verification"] == "rejected_file_type"
    assert any("undated" in x for x in by["fil_3"]["limitations"])
    assert by["homeowner_statement"]["verification"] == "homeowner_statement_unverified"
    cn = next(r for r in res["requirements"] if r["id"] == "CN-01")
    assert cn["status"] == "satisfied" or cn["status"] == "missing"
    md = open(res["packet"]["markdown_path"]).read()
    assert "fil_1" not in md and "The roof leaked" not in md


def test_cases_and_parcels_are_isolated(tmp_path, patched):
    sub = [{"id": "secret", "kind": "photo", "media_type": "image/jpeg", "file_ref": "fil_private_A", "sha256": "1" * 64,
            "document_date": "2025-12-01", "description": "Owner A kitchen photo"}]
    a = run(envelope(case_id="case-A", homeowner_submissions=sub), tmp_path)
    b = run(envelope(parcel="P0001", case_id="case-B"), tmp_path)
    assert a["appeal"]["cycle_id"] != b["appeal"]["cycle_id"]
    assert "Owner A kitchen photo" not in open(b["packet"]["markdown_path"]).read()
    assert all(i["source"].get("file_ref") != "fil_private_A" for i in b["inventory"])


def test_each_parcel_in_a_portfolio_gets_its_own_analysis(tmp_path, patched):
    results = [run(envelope(parcel=p, case_id=f"case-{p}"), tmp_path) for p in ("P0000", "P0001", "P0002")]
    assert len({r["appeal"]["cycle_id"] for r in results}) == 3
    assert len({r["packet"]["content_hash"] if r["packet"] else r["run"]["run_id"] for r in results}) == 3


def test_a_claim_the_evidence_no_longer_supports_goes_back_to_qualify(tmp_path, patched):
    from .conftest import build_county
    patched["county"] = build_county(subject_jv=0.85 * 150 * 2000)
    res = run(envelope(), tmp_path)
    assert res["conclusions"]["argument_support"] == "does_not_support"
    assert res["next_action"] == {"actor": "qualify", "action": "requalify", "reason": res["valuation"]["outcome_reason"]}
    assert res["conclusions"]["filing_readiness"] == "not_ready"


def test_blocked_intake_does_not_load_data_or_produce_a_packet(tmp_path, patched):
    res = run(envelope(qualification={}), tmp_path)
    assert res["intake"]["status"] == "blocked" and res["packet"] is None and patched["loads"] == 0
    assert res["next_action"]["action"] == "resolve_intake_blockers"


def test_file_only_accepts_a_reviewed_current_packet_with_valid_authority(tmp_path, patched):
    res = run(envelope(), tmp_path)
    check = check_handoff(res)
    assert not check["usable_by_file"] and check["filing_approval_still_required"]
    assert any("review" in p for p in check["problems"])
    test_auth = run(envelope(case_id="case-T", auth={"status": "internal_test", "instrument": "internal_test"}), tmp_path)
    assert any("authorization" in p for p in check_handoff(test_auth)["problems"])
    assert any("superseded" in p for p in check_handoff(res, current_packet_hash="0" * 64)["problems"])


def test_the_coordinator_step_result_fits_the_existing_contract(tmp_path, patched):
    from claimevidence.stepresult import to_step_result
    res = run(envelope(), tmp_path)
    sr = to_step_result(res, open(res["packet"]["markdown_path"]).read())
    assert set(sr) == {"case_id", "step", "decision", "summary", "sources", "artifacts", "tool_requests", "email_drafts"}
    assert sr["step"] == "evidence" and sr["decision"] in ("ready", "review", "blocked")
    assert sr["tool_requests"] == [] and sr["email_drafts"] == []
    assert len(sr["summary"]) <= 6000 and len(sr["sources"]) <= 30 and len(sr["artifacts"]) <= 8
    assert all(s.startswith("https://") for s in sr["sources"])
    assert all(len(a["markdown"]) <= 40000 and a["title"] for a in sr["artifacts"])
    assert sr["artifacts"][-1]["markdown"].startswith("```json")
    blocked = to_step_result(run(envelope(case_id="case-X", qualification={}), tmp_path), None)
    assert blocked["decision"] == "blocked"
