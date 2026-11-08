import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from taxfile.core import assess, digest, load_handoff, petition_property_address
from test_file import candidate


def candidate_v2():
    c = candidate()
    c.update(schema_version=2, status="candidate", values={}, signals={}, estimate={"annual_savings": 1200, "annual_savings_range": [800, 1600], "is_estimate": True}, confidence={"evidence_quality": 0.8, "evidence_label": "strong"}, explanation="Synthetic comparison only.", assumptions=["Millage is assumed."], warnings=["Unit came from the mailing address."], needs_verification=["Inspect the property record card."], portfolio={"portfolio_id": "synthetic-owner", "flagged_parcels": 2, "savings_in_run": 2400}, outreach={"eligible": False, "owner_suppressed": False, "blocked_by": ["qualify_not_run"]})
    return c


def complete_envelope(root):
    c = candidate_v2()
    c["filing_window"].update(status="open")
    matching = {"case_id": c["case_id"], "tax_year": 2026}
    content = b"SYNTHETIC authorization and evidence fixture. No legal effect."
    (root / "evidence.txt").write_bytes(content)
    artifact = {"path": "evidence.txt", "sha256": digest(content)}
    source = "https://www.hendryclerk.org/clerk-services/value-adjustment-board/"
    e = {"candidate": c, "qualification": {**matching, "status": "eligible", "route": "vab_value_appeal"}, "authorization": {**matching, "status": "signed", "signer_name": "Synthetic owner", "representation_mode": "owner", "artifact": artifact}, "evidence": {**matching, "status": "complete", "artifact": artifact}, "filing": {**matching, "instructions_url": source, "deadline_source_url": source, "deadline": "2026-12-01", "deadline_verified": True, "method": "mail", "fee_usd": 50, "fee_verified": True}}
    return e


class FindV2Tests(unittest.TestCase):
    def test_v2_json_and_board_card_preserve_candidate_context(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "handoff.txt"
            c = candidate_v2()
            for value in (json.dumps(c), 'Find candidate\n```json\n' + json.dumps(c) + '\n```'):
                path.write_text(value)
                _, loaded = load_handoff(path)
                self.assertEqual(loaded, c)

    def test_versions_and_v2_contract_types_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "handoff.json"
            for changes in ({"schema_version": 3}, {"schema_version": True}, {"status": "eligible"}, {"needs_verification": "already checked"}, {"confidence": []}, {"outreach": {"eligible": True}}, {"explanation": None}):
                with self.subTest(changes=changes):
                    path.write_text(json.dumps({**candidate_v2(), **changes}))
                    with self.assertRaises(ValueError):
                        load_handoff(path)

    def test_unresolved_find_checks_block_an_otherwise_complete_packet(self):
        with tempfile.TemporaryDirectory() as folder:
            e = complete_envelope(Path(folder))
            _, holds, _ = assess(e, e["candidate"], folder, date(2026, 11, 7))
            self.assertTrue(any("Inspect the property record card." in hold for hold in holds))

    def test_verified_find_checks_require_matching_hashed_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            e = complete_envelope(Path(folder))
            resolution = {"check": e["candidate"]["needs_verification"][0], "status": "verified", "artifact": copy.deepcopy(e["evidence"]["artifact"])}
            e["evidence"]["verifications"] = [resolution]
            _, holds, _ = assess(e, e["candidate"], folder, date(2026, 11, 7))
            self.assertEqual(holds, [])
            resolution["artifact"]["sha256"] = "wrong"
            _, holds, _ = assess(e, e["candidate"], folder, date(2026, 11, 7))
            self.assertTrue(any("SHA-256" in hold for hold in holds))
            resolution["artifact"] = e["evidence"]["artifact"]
            e["evidence"]["case_id"] = "another case"
            _, holds, _ = assess(e, e["candidate"], folder, date(2026, 11, 7))
            self.assertTrue(any("Unresolved Find verification" in hold for hold in holds))

    def test_suppressed_owner_remains_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            e = complete_envelope(Path(folder))
            e["candidate"]["needs_verification"] = []
            e["candidate"]["outreach"]["owner_suppressed"] = True
            _, holds, _ = assess(e, e["candidate"], folder, date(2026, 11, 7))
            self.assertTrue(any("suppressed" in hold for hold in holds))

    def test_portfolio_does_not_replace_parcel_case_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "handoff.json"
            c = candidate_v2()
            path.write_text(json.dumps({"candidate": c}))
            _, loaded = load_handoff(path)
            self.assertEqual(loaded["case_id"], c["case_id"])
            self.assertNotEqual(loaded["case_id"], loaded["portfolio"]["portfolio_id"])


    def test_condo_unit_and_locality_are_preserved_without_duplication(self):
        prop = {"parcel_id": "SYNTHETIC-UNIT-3", "address": "100 Example Way", "unit": "3", "city": "Test City", "zip": "00000"}
        value = petition_property_address(prop, "FL")
        self.assertIn("100 Example Way #3", value)
        self.assertIn("Test City FL 00000", value)
        prop["address"] = "100 Flower Way"
        self.assertIn("Test City FL 00000", petition_property_address(prop, "FL"))
        prop["address"] = "100 Example Way #3"
        self.assertEqual(petition_property_address(prop, "FL").count("#3"), 1)

    def test_summary_and_csv_are_not_evidence_handoffs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "handoff.txt"
            for raw in (json.dumps({"schema_version": 2, "handoff": {"status": "delivered", "delivered": 200}}), "case_id,tier\nSYNTHETIC,strong"):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    load_handoff(path)


if __name__ == "__main__":
    unittest.main()
