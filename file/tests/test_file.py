import copy
import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from taxfile.core import assess, load_handoff, local_artifact, record_receipt, record_notice


def candidate():
    return {"schema_version": 1, "case_id": "FL-26-2026-TEST", "desk": "property_tax", "jurisdiction": {"state": "FL", "county": "Hendry", "tax_year": 2026}, "property": {"parcel_id": "TEST", "address": "Test fixture", "use": "single_family"}, "owner": {"name": "Fixture only", "mailing_address": {}}, "source": {"run_id": "fixture"}, "tier": "strong", "filing_window": {"status": "closed", "closes": "2026-09-09"}}


class FileTests(unittest.TestCase):
    def test_nick_board_handoff_preserves_case_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card.md"
            path.write_text("Find result\n```json\n" + json.dumps(candidate()) + "\n```\n")
            _, result = load_handoff(path)
            self.assertEqual(result["case_id"], candidate()["case_id"])

    def test_closed_demo_cases_never_become_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            _, holds, _ = assess({}, candidate(), folder, date(2026, 11, 7))
            self.assertTrue(any("closed" in item for item in holds))
            self.assertTrue(any("qualification" in item for item in holds))
            self.assertTrue(any("authorization" in item for item in holds))
            self.assertTrue(any("evidence" in item for item in holds))

    def test_artifact_digest_and_path_are_enforced(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "packet.pdf").write_bytes(b"test evidence")
            good = {"path": "packet.pdf", "sha256": hashlib.sha256(b"test evidence").hexdigest()}
            self.assertEqual(local_artifact(good, root)["bytes"], 13)
            with self.assertRaises(ValueError):
                local_artifact({**good, "sha256": "wrong"}, root)
            with self.assertRaises(ValueError):
                local_artifact({**good, "path": "../outside.pdf"}, root)

    def test_mismatched_upstream_case_is_held(self):
        data = {"qualification": {"case_id": "different", "status": "eligible", "tax_year": 2026}}
        _, holds, _ = assess(data, candidate(), ".", date(2026, 11, 7))
        self.assertTrue(any("case-matched" in item for item in holds))

    def test_complete_case_is_ready_for_review_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            c = candidate()
            c["filing_window"]["status"] = "open"
            artifacts = {}
            for name in ("authorization", "evidence"):
                content = ("Synthetic " + name + " test fixture").encode()
                (root / (name + ".txt")).write_bytes(content)
                artifacts[name] = {"path": name + ".txt", "sha256": hashlib.sha256(content).hexdigest()}
            matching = {"case_id": c["case_id"], "tax_year": 2026}
            envelope = {"qualification": {**matching, "status": "eligible", "route": "vab_value_appeal"}, "authorization": {**matching, "status": "signed", "signer_name": "Fixture", "representation_mode": "owner", "artifact": artifacts["authorization"]}, "evidence": {**matching, "status": "complete", "artifact": artifacts["evidence"]}, "filing": {**matching, "deadline": "2026-12-01", "deadline_verified": True, "deadline_source_url": "https://www.hendryclerk.org/clerk-services/value-adjustment-board/", "instructions_url": "https://www.hendryclerk.org/clerk-services/value-adjustment-board/", "method": "mail", "fee_usd": 50, "fee_verified": True}}
            _, holds, found = assess(envelope, c, root, date(2026, 11, 7))
            self.assertEqual(holds, [])
            self.assertEqual(len(found), 2)

    def test_receipt_requires_proof_and_does_not_invent_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"case_id": "fixture", "status": "ready_for_operator_review", "property": {"parcel_id": "TEST"}}))
            receipt = root / "clerk.txt"
            receipt.write_text("Confirmation VAB-TEST-001 Parcel TEST")
            with self.assertRaises(ValueError):
                record_receipt(manifest, receipt, "FAKE", "TEST")
            result = record_receipt(manifest, receipt, "VAB-TEST-001", "TEST")
            self.assertIsNone(result["response_due"])
            self.assertEqual(result["status"], "receipt_recorded")
            again = record_receipt(manifest, receipt, "VAB-TEST-001", "TEST")
            self.assertEqual(result["sha256"], again["sha256"])
            self.assertEqual(len((root / "receipts.jsonl").read_text().splitlines()), 1)


    def test_notice_requires_case_and_date_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"case_id": "fixture", "receipt": {"confirmation_id": "VAB-TEST-001", "parcel_id": "TEST"}}))
            notice = root / "notice.txt"
            notice.write_text("VAB-TEST-001 response deadline: December 15, 2026")
            with self.assertRaises(ValueError):
                record_notice(manifest, notice, "2026-12-16")
            result = record_notice(manifest, notice, "2026-12-15")
            self.assertEqual(result["response_due"], "2026-12-15")
            self.assertTrue(Path(result["path"]).exists())
            self.assertEqual(json.loads(manifest.read_text())["response_deadline"], "2026-12-15")


if __name__ == "__main__":
    unittest.main()
