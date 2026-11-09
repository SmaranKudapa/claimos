import copy
import json
import tempfile
import unittest
from pathlib import Path
from taxfile.bridge import evidence_input, evidence_handoff
from taxfile.core import assess, digest
from taxfile.handoff import evidence_holds, qualification_from_batch
from test_find_v2 import candidate_v2


def bundle(root):
    candidate = candidate_v2()
    candidate['case_id'] = 'FL-36-2026-SYNTHETIC'
    candidate['jurisdiction']['county_code'] = '36'
    candidate['property']['parcel_id'] = 'SYNTHETIC'
    candidate['needs_verification'] = []
    candidate['filing_window']['status'] = 'open'
    case = candidate['case_id']
    row = {'find_case_id': case, 'caseId': 'qualify-alternate-id', 'jurisdictionId': 'FL-36', 'judgedAsOf': '2026-11-07', 'status': 'QUALIFIED', 'route': {'id': 'vab_petition', 'form': 'DR-486', 'deadline': '2026-12-01'}, 'translatorNotes': [], 'annualSavings': 1200}
    qualify = {'realDate': '2026-11-07', 'replay': False, 'cases': [row]}
    packet = b'%PDF-1.4\nSYNTHETIC BOUNDARY TEST ONLY'
    (root / 'evidence-packet.pdf').write_bytes(packet)
    sha = digest(packet)
    result = {'schema': 'claimos.evidence.result/1', 'case_id': case, 'appeal': {'tax_year': 2026, 'parcel_id': 'SYNTHETIC', 'jurisdiction': {'county_code': '36'}}, 'run': {'processing_status': 'completed'}, 'synthetic': False, 'replay': None, 'packet': {'sha256': sha, 'version': 1}, 'review': {'status': 'approved', 'stale': False, 'reviewed_packet_hash': sha, 'approved_for': ['file_handoff'], 'reviewed_by': 'fixture reviewer', 'reviewed_at': '2026-11-07'}, 'validation': {'status': 'validated_against_configured_requirements'}, 'readiness': {'format_validation': 'validated_against_configured_requirements', 'analytical_sufficiency': 'supports_reduction', 'evidence_completeness': 'complete'}, 'authorization': {'valid_for_filing': True}}
    evidence = {'case_id': case, 'tax_year': 2026, 'status': 'complete', 'artifact': {'path': 'evidence-packet.pdf', 'sha256': sha}, 'verifications': [], 'source': {'schema': result['schema'], 'packet_sha256': sha, 'packet_version': 1}}
    for name, obj in [('candidate', candidate), ('qualify', qualify), ('result', result), ('evidence', evidence)]:
        (root / (name + '.json')).write_text(json.dumps(obj))
    return candidate, qualify, result, evidence


class HandoffBridgeTests(unittest.TestCase):
    def test_qualify_mapping_keeps_identity_original_decision_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            c, q, _, _ = bundle(Path(folder))
            mapped = qualification_from_batch(q, c)
            self.assertEqual(mapped['case_id'], c['case_id'])
            self.assertEqual(mapped['decision'], 'qualified')
            self.assertEqual(mapped['source']['original'], q['cases'][0])
            q['replay'] = True
            mapped = qualification_from_batch(q, c)
            self.assertEqual(mapped['status'], 'replay_only')
            self.assertTrue(mapped['replay'])

    def test_qualification_identity_and_decision_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            c, base, _, _ = bundle(Path(folder))
            changes = [('status', v) for v in ('REJECTED', 'INCOMPLETE', 'NEXT_CYCLE', 'NEEDS_REVIEW')]
            changes += [('find_case_id', 'different'), ('jurisdictionId', 'FL-13'), ('judgedAsOf', '2025-11-07'), ('route', {'id': 'other', 'form': 'DR-486'})]
            for field, value in changes:
                q = copy.deepcopy(base);q['cases'][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    qualification_from_batch(q, c)
            for q in ({**base, 'replay': None}, {**base, 'cases': base['cases'] * 2}, {**base, 'cases': []}):
                with self.assertRaises(ValueError):
                    qualification_from_batch(q, c)

    def test_replay_cannot_be_removed_by_only_changing_the_batch_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            c, q, _, _ = bundle(Path(folder))
            q['cases'][0]['judgedAsOf'] = '2026-09-01'
            self.assertTrue(qualification_from_batch(q, c)['replay'])
            q['cases'][0]['judgedAsOf'] = q['realDate']
            q['cases'][0]['translatorNotes'] = ['replay: historical valuation window']
            self.assertTrue(qualification_from_batch(q, c)['replay'])

    def test_evidence_input_does_not_invent_authorization_or_consent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);c, _, _, _ = bundle(root)
            result = evidence_input(root / 'candidate.json', root / 'qualify.json')
            self.assertEqual(result['find'], c)
            self.assertEqual(result['authorization'], {})
            self.assertEqual(result['consent'], {})
            self.assertEqual(result['qualification']['decision'], 'qualified')

    def test_original_evidence_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            c, _, original, ev = bundle(Path(folder))
            self.assertEqual(evidence_holds(original, ev, c), [])
            mutations = [
                ('schema', None), ('case_id', 'other'), ('synthetic', True), ('replay', {'as_of': '2026-09-01'}),
                ('run', {'processing_status': 'failed'}), ('packet', {'sha256': 'wrong', 'version': 1}),
                ('review', {**original['review'], 'status': 'pending'}),
                ('review', {**original['review'], 'stale': True}),
                ('review', {**original['review'], 'reviewed_packet_hash': 'wrong'}),
                ('review', {**original['review'], 'approved_for': ['exchange_property_appraiser']}),
                ('validation', {'status': 'failed'}), ('authorization', {'valid_for_filing': False}),
                ('readiness', {**original['readiness'], 'evidence_completeness': 'incomplete'}),
            ]
            for field, value in mutations:
                r = copy.deepcopy(original);r[field] = value
                with self.subTest(field=field, value=value):
                    self.assertTrue(evidence_holds(r, ev, c))

    def test_import_preserves_artifacts_and_refuses_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);c, _, _, _ = bundle(root)
            out = root / 'imported' / 'case.json'
            result = evidence_handoff(root / 'candidate.json', root / 'qualify.json', root / 'result.json', root / 'evidence.json', out)
            self.assertEqual(result['candidate'], c)
            art = result['evidence']['artifact']
            self.assertEqual(digest((out.parent / art['path']).read_bytes()), art['sha256'])
            with self.assertRaises(ValueError):
                evidence_handoff(root / 'candidate.json', root / 'qualify.json', root / 'result.json', root / 'evidence.json', out)

    def test_tampered_packet_never_creates_a_handoff(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);bundle(root)
            (root / 'evidence-packet.pdf').write_bytes(b'tampered')
            out = root / 'imported' / 'case.json'
            with self.assertRaises(ValueError):
                evidence_handoff(root / 'candidate.json', root / 'qualify.json', root / 'result.json', root / 'evidence.json', out)
            self.assertFalse(out.exists())

    def test_native_evidence_requires_original_result_even_if_marked_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);c, q, _, ev = bundle(root)
            _, holds, _ = assess({'evidence': ev, 'qualification': qualification_from_batch(q, c)}, c, root)
            self.assertTrue(any('original supported Evidence result' in h for h in holds))

    def test_replay_and_synthetic_markers_are_independent_holds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);c, q, r, ev = bundle(root)
            env = {'qualification': qualification_from_batch(q, c), 'evidence': ev, 'evidence_result': r, 'replay': True, 'synthetic': True}
            _, holds, _ = assess(env, c, root)
            self.assertTrue(any('Replay qualification' in h for h in holds))
            self.assertTrue(any('Synthetic handoffs' in h for h in holds))


if __name__ == '__main__':
    unittest.main()
