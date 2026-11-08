from __future__ import annotations

import datetime as dt
import json

from pypdf import PdfReader

from claimevidence.engine import run
from claimevidence.forums import forum
from claimevidence.report import Doc
from claimevidence.rules import cost_of_sale, deadlines_for, exchange_due, remote_upload_due, rules_for
from claimevidence.validate import validate

from .conftest import envelope, find_payload

TODAY = dt.date(2026, 11, 7)


def _pages(res):
    return [" ".join((p.extract_text() or "").split()) for p in PdfReader(res["packet"]["pdf_path"]).pages]


def test_every_index_entry_points_at_the_page_that_holds_the_exhibit(tmp_path, patched):
    res = run(envelope(), tmp_path, today=TODAY)
    pages = _pages(res)
    ex = res["packet"]["exhibits"]
    assert [e["id"] for e in ex] == [f"Exhibit {i + 1}" for i in range(len(ex))]
    for e in ex:
        assert f"{e['id']}: {e['title'][:20]}" in pages[e["page"] - 1]
    index_page = next(p for p in pages if "Evidence index" in p or "Exhibit Description Date" in p)
    assert all(e["id"] in index_page for e in ex)
    assert all(f"Page {i + 1} of {len(pages)}" in p for i, p in enumerate(pages))
    labels = [o.title for o in PdfReader(res["packet"]["pdf_path"]).outline if not isinstance(o, list)]
    assert "Summary" in labels and "Evidence index" in labels


def test_the_identification_page_never_invents_a_petition_number_and_shows_one_when_supplied(tmp_path, patched):
    a = run(envelope(), tmp_path, today=TODAY)
    assert "Petition number Not yet assigned" in _pages(a)[0]
    b = run(envelope(submission={"petition_number": "2026-0042", "contact_phone": "850-555-0100"}), tmp_path, today=TODAY)
    first = _pages(b)[0]
    assert "Petition number 2026-0042" in first and "850-555-0100" in first
    assert not [c for c in b["validation"]["checks"] if c["id"] == "V-FMT-COVER" and c["status"] != "pass"]


def test_unsigned_cases_get_a_packet_without_a_named_petitioner(tmp_path, patched):
    res = run(envelope(auth={}), tmp_path, today=TODAY)
    first = _pages(res)[0]
    assert "Petitioner Not yet confirmed" in first and "TEST OWNER" not in " ".join(_pages(res))
    assert res["readiness"]["authorization"] == "not_signed" and res["conclusions"]["filing_readiness"] == "not_ready"


def test_redaction_removes_text_from_every_output_not_just_the_view(tmp_path, patched):
    res = run(envelope(redactions=["TESTVILLE"]), tmp_path, today=TODAY)
    assert res["packet"]["redactions_applied"] > 0
    assert "TESTVILLE" not in " ".join(_pages(res))
    for k in ("markdown_path", "html_path"):
        assert "TESTVILLE" not in open(res["packet"][k]).read()
    assert all(c["status"] == "pass" for c in res["validation"]["checks"] if c["id"] == "V-REDACT")


def _doc_with(text):
    d = Doc("Petitioner's evidence of value", "P / 2026")
    d.add("p", text)
    return d


def test_validation_rejects_appraisal_language_placeholders_internal_ids_and_contact_data(tmp_path, patched):
    res = run(envelope(), tmp_path, today=TODAY)
    col = json.load(open(next(tmp_path.rglob("collected.json"))))
    base = {"appeal": res["appeal"]}
    fm = forum("vab_just_value", "Testcounty")
    for bad, check in (("This appraisal shows the value.", "V-TEXT-CLAIMS"), ("The board will win this for you.", "V-TEXT-CLAIMS"),
                       ("Value: None", "V-TEXT-PLACEHOLDER"), ("See fil_9psg0r37dx2n9 for details", "V-PRIVACY"),
                       ("Call the owner at owner@example.com", "V-PRIVACY"), ("Find agent flagged this", "V-PRIVACY")):
        v = validate(_doc_with(bad), None, None, base, col, res["analysis"], res["valuation"], fm, {}, [], [], None)
        assert any(c["id"] == check and c["status"] == "fail" for c in v["checks"]), bad
        assert v["status"] == "failed"


def test_redaction_leak_is_caught(tmp_path, patched):
    res = run(envelope(), tmp_path, today=TODAY)
    col = json.load(open(next(tmp_path.rglob("collected.json"))))
    v = validate(_doc_with("Owner SSN 123-45-6789"), None, None, {"appeal": res["appeal"]}, col, res["analysis"], res["valuation"],
                 forum("vab_just_value", "Testcounty"), {}, ["123-45-6789"], [], None)
    assert {c["id"] for c in v["checks"] if c["status"] == "fail"} >= {"V-REDACT", "V-PRIVACY"}


def test_generation_never_marks_anything_sent_and_events_need_an_approved_matching_packet(tmp_path, patched):
    first = run(envelope(), tmp_path, today=TODAY)
    sha = first["packet"]["sha256"]
    event = {"delivery_id": "exchange_property_appraiser", "status": "sent", "at": "2026-11-10T15:00:00Z", "by": "operator@claimos",
             "evidence_ref": "certified-mail-receipt-1", "packet_sha256": sha}
    unapproved = run(envelope(delivery_events=[event]), tmp_path, today=TODAY)
    man = json.load(open(unapproved["delivery"]["path"]))
    assert man["event_log"][0]["accepted"] is False and unapproved["delivery"]["deliveries"]["exchange_property_appraiser"] == "not_sent"
    review = {"packet_hash": sha, "status": "approved", "reviewed_by": "reviewer", "reviewed_at": "2026-11-08",
              "approved_for": ["exchange_property_appraiser"]}
    wrong = run(envelope(prior_review=review, delivery_events=[{**event, "packet_sha256": "0" * 64}]), tmp_path, today=TODAY)
    assert wrong["delivery"]["deliveries"]["exchange_property_appraiser"] == "not_sent"
    ok = run(envelope(prior_review=review, delivery_events=[event]), tmp_path, today=TODAY)
    assert ok["delivery"]["deliveries"]["exchange_property_appraiser"] == "sent"
    assert ok["delivery"]["deliveries"]["petition_dr486"] == "not_filed"
    assert ok["readiness"]["approval"] == "approved_for_the_specified_submission" and ok["readiness"]["approved_for"] == ["exchange_property_appraiser"]


def test_rescheduling_recomputes_deadlines_without_creating_a_new_packet(tmp_path, patched):
    a = run(envelope(appeal={**envelope()["appeal"], "hearing_date": "2026-12-02"}), tmp_path, today=TODAY)
    b = run(envelope(appeal={**envelope()["appeal"], "hearing_date": "2026-12-11"}), tmp_path, today=TODAY)
    assert a["packet"]["sha256"] == b["packet"]["sha256"] and a["packet"]["version"] == b["packet"]["version"]
    assert a["deadlines"]["evidence_exchange_petitioner"]["date"] == "2026-11-17"
    assert b["deadlines"]["evidence_exchange_petitioner"]["date"] == "2026-11-25"
    man = json.load(open(b["delivery"]["path"]))
    ex = next(d for d in man["deliveries"] if d["id"] == "exchange_property_appraiser")
    assert ex["due"]["date"] == "2026-11-25"


def test_file_receives_a_complete_evidence_object_only_after_review_of_the_exact_packet(tmp_path, patched):
    first = run(envelope(), tmp_path, today=TODAY)
    ev = json.load(open(first["file_handoff"]["evidence_json"]))
    assert ev["status"] == "incomplete" and ev["case_id"] == "FL-99-2026-P0000" and ev["tax_year"] == 2026
    review = {"packet_hash": first["packet"]["sha256"], "status": "approved", "reviewed_by": "reviewer", "reviewed_at": "2026-11-08",
              "approved_for": ["file_handoff"]}
    approved = run(envelope(prior_review=review), tmp_path, today=TODAY)
    ev = json.load(open(approved["file_handoff"]["evidence_json"]))
    root = tmp_path.joinpath(approved["file_handoff"]["dir"])
    assert ev["status"] == "complete"
    import hashlib
    assert hashlib.sha256((root / ev["artifact"]["path"]).read_bytes()).hexdigest() == ev["artifact"]["sha256"]


def test_find_verification_strings_are_answered_exactly_and_only_verified_with_an_artifact(tmp_path, patched):
    checks = ["Confirm the parcel's actual millage for its taxing district — the savings here use an assumed rate, not a billed one.",
              "Few comparable sales (3): the sales ratio rests on a small sample."]
    res = run(envelope(find={**find_payload(), "needs_verification": checks}), tmp_path, today=TODAY)
    ev = json.load(open(res["file_handoff"]["evidence_json"]))
    assert [v["check"] for v in ev["verifications"]] == checks
    millage = ev["verifications"][0]
    assert millage["status"] == "unverified" and "artifact" not in millage
    for v in ev["verifications"]:
        if v["status"] == "verified":
            assert v["artifact"]["path"] and len(v["artifact"]["sha256"]) == 64


def test_synthetic_fixtures_are_labelled_and_can_never_be_delivered_or_handed_to_file(tmp_path, patched):
    review_probe = run(envelope(synthetic=True), tmp_path, today=TODAY)
    review = {"packet_hash": review_probe["packet"]["sha256"], "status": "approved", "reviewed_by": "r", "reviewed_at": "2026-11-08",
              "approved_for": ["exchange_property_appraiser", "file_handoff"]}
    res = run(envelope(synthetic=True, prior_review=review), tmp_path, today=TODAY)
    assert _pages(res)[0].startswith("TEST FIXTURE") or "TEST FIXTURE, NOT FOR SUBMISSION" in _pages(res)[0]
    assert set(res["delivery"]["deliveries"].values()) == {"blocked_synthetic"}
    assert json.load(open(res["file_handoff"]["evidence_json"]))["status"] == "synthetic_fixture"
    from claimevidence.stepresult import to_step_result
    assert to_step_result(res, None)["decision"] == "blocked"


def test_an_unconfigured_county_has_no_cost_of_sale_and_says_so(tmp_path, patched):
    res = run(envelope(), tmp_path, today=TODAY)
    assert res["valuation"]["cost_of_sale"] is None
    cos = [c for c in res["validation"]["checks"] if c["id"] == "V-CALC-COS"]
    assert cos and cos[0]["status"] == "warn"


def test_bay_uses_its_dr493_rate_and_the_exchange_counting_rule():
    c = cost_of_sale("Bay County", 2026, "001")
    assert c["rate"] == 0.15 and "DR-493" in c["source"]
    assert cost_of_sale("Volusia", 2026, "001") is None
    assert exchange_due(dt.date(2026, 12, 2)) == dt.date(2026, 11, 17)
    assert exchange_due(dt.date(2026, 12, 11)) == dt.date(2026, 11, 25)
    assert remote_upload_due(dt.date(2026, 12, 7)) == dt.datetime(2026, 12, 3, 9, 0)
    d = deadlines_for("Bay", 2026, None, TODAY)
    assert d["petition_filing"]["date"] == "2026-09-08" and d["petition_filing"]["verified"] and d["petition_filing"]["status"] == "passed"
    assert d["evidence_exchange_petitioner"]["date"] is None


def test_forums_are_separate_and_court_is_never_generated():
    assert forum("vab_just_value", "Bay")["authority"] == "Bay County Value Adjustment Board"
    assert forum("informal_characteristics_correction", "Bay")["authority"] == "Bay County Property Appraiser"
    court = forum("circuit_court_value", "Bay")
    assert court["supported"] == "legal_review_only" and court["document"] is None
    assert forum("vab_just_value", "Volusia")["county"]["local_procedures"] == "unknown"
    ids = {r["id"] for r in rules_for("Bay", "vab_just_value", "fl_vab_value_petition")}
    assert {"FL-EVX-01", "FL-HRG-02", "BAY-VAL-01", "FL-475-01"} <= ids and "LEE-VAL-01" not in ids
    assert "FL-INF-01" not in ids


def test_an_incomplete_case_still_renders_but_requests_nothing_and_stays_blocked(tmp_path, patched):
    from .conftest import build_county
    patched["county"] = build_county(n_sales=2)
    res = run(envelope(), tmp_path, today=TODAY)
    assert res["conclusions"]["argument_support"] == "insufficient_evidence"
    first = _pages(res)[0]
    assert "Value requested No value is requested" in first
    assert res["validation"]["status"] == "validated_against_configured_requirements"
    assert res["readiness"]["portal_status"]["code"] == "insufficient_evidence"
    assert json.load(open(res["file_handoff"]["evidence_json"]))["status"] == "incomplete"


def _in_county(name, **kw):
    fp = find_payload()
    fp["jurisdiction"] = {**fp["jurisdiction"], "county": name}
    env = envelope(find=fp, **kw)
    env["appeal"]["jurisdiction"]["county"] = name
    return env


def test_county_delivery_rules_stay_local(tmp_path, patched):
    hendry = run(_in_county("Hendry"), tmp_path / "h", today=TODAY)
    assert hendry["delivery"]["deliveries"]["remote_vab_upload"] == "not_applicable"
    lee = run(_in_county("Lee"), tmp_path / "l", today=TODAY)
    man = json.load(open(lee["delivery"]["path"]))
    ex = next(d for d in man["deliveries"] if d["id"] == "exchange_property_appraiser")
    assert "vabmail@leepa.org" in ex["method"] and lee["delivery"]["deliveries"]["remote_vab_upload"] == "not_sent"
    assert any(c["id"] == "V-FMT-COUNTY-SIZE" and c["status"] == "pass" for c in lee["validation"]["checks"])
    bay = run(_in_county("Bay"), tmp_path / "b", today=TODAY)
    bman = json.load(open(bay["delivery"]["path"]))
    bex = next(d for d in bman["deliveries"] if d["id"] == "exchange_property_appraiser")
    assert "to be agreed" in bex["method"] and "not confirmed" in bex["copies"]
    assert "PB-EVX-01" not in {r["id"] for r in bay["rules_applied"]} and "LEE-EVX-01" not in {r["id"] for r in bay["rules_applied"]}


def test_a_witness_without_an_address_blocks_the_exchange_but_not_generation(tmp_path, patched):
    sub = [{"id": "w1", "kind": "statement", "statement_text": "I will testify.", "witness": "Pat Owner",
            "witness_subject": "the condition of the roof on January 1"}]
    res = run(envelope(homeowner_submissions=sub), tmp_path, today=TODAY)
    assert "Pat Owner" in " ".join(_pages(res)) and "To be added before the exchange" in " ".join(_pages(res))
    assert any(c["id"] == "V-WITNESS" and c["status"] == "warn" for c in res["validation"]["checks"])
    man = json.load(open(res["delivery"]["path"]))
    ex = next(d for d in man["deliveries"] if d["id"] == "exchange_property_appraiser")
    assert any("witness address" in b for b in ex["blockers"])
    assert res["readiness"]["generation"] == "generated"


def test_a_packet_that_requests_nothing_is_titled_not_for_submission(tmp_path, patched):
    from .conftest import build_county
    patched["county"] = build_county(n_sales=2)
    res = run(envelope(), tmp_path, today=TODAY)
    first = _pages(res)[0]
    assert first.startswith("Evidence review, not for submission") or "Evidence review, not for submission" in first[:200]
    assert "Not for submission." in first
