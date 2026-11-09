import argparse
import copy
import json
from datetime import timedelta
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from taxfile.core import FORM_URL, digest, fetch_form, filing_today, prepare, record_notice, record_receipt


def sample_pdf(path, lines):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    text = ["BT /F1 11 Tf 45 745 Td 17 TL"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        text.append("(" + escaped + ") Tj T*")
    text.append("ET")
    stream.set_data("\n".join(text).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_metadata({"/Title": "SYNTHETIC TEST ONLY - NOT A REAL CLAIM"})
    writer.write(path)


def exercise(out, template=None, schema_version=1):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if template:
        template = Path(template)
    else:
        template = out / "official-dr486.pdf"
        fetch_form(template)
    sample = out / "input"
    sample.mkdir(exist_ok=True)
    today = filing_today()
    deadline = (today + timedelta(days=30)).isoformat()
    response_due = (today + timedelta(days=45)).isoformat()
    cid, parcel = "SYNTHETIC-LEE-" + str(today.year) + "-001", "SYNTHETIC-LEE-001"
    c = {"schema_version": 1, "desk": "property_tax", "case_id": cid, "jurisdiction": {"state": "FL", "county": "Lee", "county_code": "46", "tax_year": today.year}, "property": {"parcel_id": parcel, "address": "100 Example Way, Test City, FL 00000", "use": "single_family"}, "owner": {"name": "SYNTHETIC TEST OWNER - DO NOT FILE", "mailing_address": {"street": "100 Example Way", "city": "Test City", "state": "FL", "zip": "00000"}}, "tier": "strong", "filing_window": {"status": "open", "closes": deadline}, "source": {"run_id": "SYNTHETIC-VERIFICATION-ONLY", "found_at": today.isoformat(), "note": "Invented property, ownership, authority and deadlines for tests. Never submit."}}
    if schema_version == 2:
        c.update(schema_version=2, status="candidate", values={}, signals={}, estimate={"annual_savings": 1500, "annual_savings_range": [1000, 2000], "is_estimate": True}, confidence={"evidence_quality": 0.8, "evidence_label": "strong"}, explanation="Synthetic comparable analysis only.", assumptions=["Synthetic millage assumption."], warnings=["Synthetic portfolio grouping."], needs_verification=["Inspect the synthetic property record card."], portfolio={"portfolio_id": "SYNTHETIC-OWNER", "flagged_parcels": 2, "savings_in_run": 3000}, outreach={"eligible": False, "owner_suppressed": False, "blocked_by": ["qualify_not_run"]})
    match = {"case_id": cid, "tax_year": today.year}
    artifact = {}
    for kind, lines in {"authorization": ["Synthetic authorization fixture; no legal authorization or actual signature.", "Owner: SYNTHETIC TEST OWNER. Representation fixture: owner."], "evidence": ["Synthetic assessment: 500000; synthetic comparable estimate: 400000.", "Invented comparables: EXAMPLE-A, EXAMPLE-B. Not a valuation opinion."]}.items():
        path = sample / (kind + ".pdf")
        sample_pdf(path, ["SYNTHETIC TEST ONLY - NOT A REAL CLAIM", "DO NOT FILE. DO NOT CONTACT ANYONE.", "Case: " + cid, "Parcel: " + parcel] + lines)
        artifact[kind] = {"path": path.name, "sha256": digest(path.read_bytes())}
    source = "https://www.leeclerk.org/departments/value-adjustment-board-vab/filing-a-petition"
    envelope = {"candidate": c, "qualification": {**match, "status": "eligible", "route": "vab_value_appeal"}, "authorization": {**match, "status": "signed", "signer_name": "SYNTHETIC TEST OWNER", "representation_mode": "owner", "artifact": artifact["authorization"]}, "evidence": {**match, "status": "complete", "artifact": artifact["evidence"]}, "filing": {**match, "instructions_url": source, "deadline_source_url": source, "deadline": deadline, "deadline_verified": True, "method": "online", "fee_usd": 50, "fee_verified": True}, "test_notice": "SYNTHETIC TEST ONLY: flags exercise validation; no real qualification, signature, deadline or fee verification occurred."}
    if schema_version == 2:
        envelope["evidence"]["verifications"] = [{"check": c["needs_verification"][0], "status": "verified", "artifact": artifact["evidence"]}]
    handoff = sample / "case-handoff.json"
    handoff.write_text(json.dumps(envelope, indent=2))
    manifest, case_dir = prepare(handoff, out / "prepared", template)
    assert manifest["status"] == "ready_for_operator_review", manifest["holds"]
    assert manifest["submitted"] is False
    pdf = PdfReader(manifest["petition"]["path"])
    fields = pdf.get_fields()
    assert len(pdf.pages) == 2
    assert fields["Tax Payer Name"]["/V"] == c["owner"]["name"]
    assert parcel in fields["Parcel ID and Pyshical Address"]["/V"]
    for name in ("Real property Value", "Decrease", "Res 1-4 units"):
        assert fields[name]["/V"] == "/Yes", name
    for name in ("Petition Number", "County", "Year", "Date Received", "Signature taxpayer", "Signature5", "Signature representative"):
        assert not fields[name].get("/V"), name
    for annotation_ref in pdf.pages[0]["/Annots"]:
        annotation = annotation_ref.get_object()
        if annotation.get("/T") in ("Mailing Address", "Parcel ID and Pyshical Address"):
            assert int(annotation.get("/Ff", 0)) & 4096
    assert "00000" in fields["Mailing Address"]["/V"]
    assert len(manifest["artifacts"]) == (3 if schema_version == 2 else 2)
    assert manifest["candidate"] == c
    assert json.loads((case_dir / "candidate.json").read_text()) == c
    for a in manifest["artifacts"]:
        assert digest(Path(a["path"]).read_bytes()) == a["sha256"]
    results = [{"check": "complete sample, official PDF fields and attachment hashes", "passed": True}]
    variants = [
        ("missing evidence", lambda e: e.pop("evidence"), "evidence"),
        ("mismatched evidence case", lambda e: e["evidence"].update(case_id="OTHER"), "case-matched"),
        ("wrong tax year", lambda e: e["qualification"].update(tax_year=today.year - 1), "tax year"),
        ("altered evidence bytes", lambda e: e["evidence"]["artifact"].update(sha256="0" * 64), "SHA-256"),
        ("closed window", lambda e: e["candidate"]["filing_window"].update(status="closed"), "closed"),
        ("past deadline", lambda e: e["filing"].update(deadline=(today - timedelta(days=1)).isoformat()), "passed"),
        ("unsupported county route", lambda e: e["filing"].update(method="fax"), "method"),
        ("unverified fee", lambda e: e["filing"].update(fee_verified=False), "fee"),
        ("untrusted filing host", lambda e: e["filing"].update(instructions_url="https://www.leeclerk.org.attacker.invalid/"), "URLs"),
        ("changed owner", lambda e: e["candidate"]["owner"].update(may_have_changed=True), "Ownership"),
        ("unsigned authority", lambda e: e["authorization"].update(status="pending"), "signed"),
    ]
    for name, change, hold in variants:
        modified = copy.deepcopy(envelope)
        change(modified)
        path = sample / (name.replace(" ", "-") + ".json")
        path.write_text(json.dumps(modified, indent=2))
        blocked, _ = prepare(path, out / "blocked" / name.replace(" ", "-"), template)
        assert blocked["status"] == "blocked" and blocked["submitted"] is False
        assert any(hold in h for h in blocked["holds"]), (name, blocked["holds"])
        results.append({"check": name, "passed": True})
    receipt = case_dir / "synthetic-receipt.pdf"
    confirmation = "SYNTHETIC-CONFIRMATION-001"
    sample_pdf(receipt, ["SYNTHETIC TEST RECEIPT - NO SUBMISSION OCCURRED", "Confirmation: " + confirmation, "Parcel: " + parcel])
    manifest_path = case_dir / "manifest.json"
    row = record_receipt(manifest_path, receipt, confirmation, parcel)
    assert row["response_due"] is None
    notice = case_dir / "synthetic-notice.pdf"
    sample_pdf(notice, ["SYNTHETIC TEST NOTICE - NO LEGAL EFFECT", "Confirmation: " + confirmation, "Parcel: " + parcel, "Synthetic response deadline: " + response_due])
    record_notice(manifest_path, notice, response_due)
    repeated = record_receipt(manifest_path, receipt, confirmation, parcel)
    assert repeated["response_due"] == response_due
    assert repeated["next_action"] == "verify_clerk_acceptance_and_fee_receipt"
    assert repeated["deadline_source_sha256"] == repeated["notice"]["sha256"]
    assert len((case_dir / "receipts.jsonl").read_text().splitlines()) == 1
    updated = json.loads(manifest_path.read_text())
    assert updated["receipt"]["response_due"] == updated["response_deadline"] == response_due
    assert updated["submitted"] is False
    results.append({"check": "sample PDF receipt, later notice and idempotent replay", "passed": True})
    try:
        prepare(handoff, out / "prepared", template)
        raise AssertionError("A receipted case was prepared again")
    except ValueError as error:
        assert "receipt already exists" in str(error)
    results.append({"check": "duplicate preparation prevented", "passed": True})
    report = {"verification_only": True, "candidate_schema_version": schema_version, "disclaimer": "All cases, authorization, receipt and notice are synthetic. No filing, message, payment or teammate-agent action occurred.", "case_id": cid, "checks": results, "passed": len(results), "form_source": FORM_URL, "form_revision": manifest["petition"]["revision"], "case_directory": str(case_dir), "handoff": str(handoff)}
    (out / "verification-report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--template")
    parser.add_argument("--schema-version", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    print(json.dumps(exercise(args.out, args.template, args.schema_version), indent=2))
