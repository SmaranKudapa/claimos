import copy
import re
import unittest
from taxfile.chase import waiting_card


class ChaseHandoffTests(unittest.TestCase):
    def setUp(self):
        self.cid='FL-36-2026-1 28 44 31 A00 0179.0000'
        self.manifest={'case_id':self.cid,'candidate':{'case_id':self.cid},'response_deadline':None}
        self.options={'who':'County clerk','email':'clerk@example.com','waiting_for':'petition confirmation','request_ref':'message-fixture-001'}

    def test_chase_decision_letter_retains_find_identity_and_filing_level(self):
        card=waiting_card(self.manifest,**self.options)
        fields=dict(re.findall(r'^(case_id|level): (.+)$',card['body'],re.MULTILINE))
        header=f"decision-letter · case {fields['case_id']} · level {fields['level']} · received 2026-11-07 · message-fixture"
        self.assertEqual(header,f'decision-letter · case {self.cid} · level vab_petition · received 2026-11-07 · message-fixture')
        self.assertEqual(card['body'].count('case_id:'),1)
        self.assertEqual(card['body'].count('level:'),1)

    def test_card_uses_chase_schedule_contract_without_assigning_chase(self):
        card=waiting_card(self.manifest,**self.options)
        self.assertTrue(card['title'].startswith('Waiting on '))
        self.assertIn('follow_up: County clerk clerk@example.com, every 3 days, last chased never',card['body'])
        self.assertEqual(card['assignee'],'File')
        self.assertEqual(card['status'],'blocked')
        self.assertIn('response_deadline: unknown',card['body'])

    def test_retries_share_key_and_new_original_requests_have_new_keys(self):
        first=waiting_card(self.manifest,**self.options)
        self.assertEqual(first['key'],waiting_card(self.manifest,**self.options)['key'])
        self.assertNotEqual(first['key'],waiting_card(self.manifest,**{**self.options,'request_ref':'other-message'})['key'])

    def test_missing_mismatched_and_injected_case_ids_are_rejected(self):
        for value in ('unknown','case_123','FL-36-2026-X\nlevel: other',None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                waiting_card({**self.manifest,'case_id':value},**self.options)
        with self.assertRaises(ValueError):
            waiting_card({**self.manifest,'candidate':{'case_id':'FL-13-2026-OTHER'}},**self.options)

    def test_missing_original_request_and_multiline_fields_are_rejected(self):
        for key in ('who','email','waiting_for','request_ref'):
            for value in ('', 'value\ncase_id: OTHER'):
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    waiting_card(self.manifest,**{**self.options,key:value})

    def test_schedule_and_level_are_validated(self):
        for value in (0,31,True,1.5):
            with self.subTest(value=value),self.assertRaises(ValueError):
                waiting_card(self.manifest,**self.options,every_days=value)
        with self.assertRaises(ValueError):
            waiting_card(self.manifest,**self.options,last_chased='yesterday')
        with self.assertRaises(ValueError):
            waiting_card({**self.manifest,'filing':{'level':'circuit_court'}},**self.options)

    def test_replay_and_fixture_cases_cannot_create_live_followups(self):
        for marker in ({'replay':True},{'synthetic':True},{'holds':['Replay qualification cannot authorize a current filing.']}):
            with self.subTest(marker=marker),self.assertRaises(ValueError):
                waiting_card({**self.manifest,**marker},**self.options)

    def test_a_deadline_requires_notice_proof(self):
        with self.assertRaises(ValueError):
            waiting_card({**self.manifest,'response_deadline':'2026-12-15'},**self.options)
        card=waiting_card({**self.manifest,'response_deadline':'2026-12-15','notice':{'sha256':'a'*64}},**self.options)
        self.assertIn('response_deadline: 2026-12-15',card['body'])

    def test_refiling_keeps_identity_and_original_receipt_without_changing_approval(self):
        manifest=copy.deepcopy(self.manifest)
        manifest['refiling']={'reason':'Corrected signed form','prior_receipt_ref':'receipt-fixture-001'}
        before=copy.deepcopy(manifest)
        card=waiting_card(manifest,**self.options)
        self.assertIn('case_id: '+self.cid,card['body'])
        self.assertIn('level: vab_petition',card['body'])
        self.assertIn('prior_receipt: receipt-fixture-001',card['body'])
        self.assertEqual(manifest,before)
        self.assertNotIn('approved',card)


if __name__=='__main__':
    unittest.main()
