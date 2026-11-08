import argparse
import json
from datetime import date
from pathlib import Path
from taxfile.bridge import evidence_input, evidence_handoff
from taxfile.core import digest, fetch_form, prepare


def exercise(find_jsonl, qualify, case_id, out, data_dir=None):
    from claimevidence.engine import run
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Use a new output directory for the integration run.')
    matches = []
    for line in Path(find_jsonl).open():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('case_id') == case_id:
            matches.append(row)
    if len(matches) != 1:
        raise ValueError('Find must contain exactly one original matching candidate.')
    out.mkdir(parents=True)
    candidate_path = out / 'candidate.json'
    candidate_path.write_text(json.dumps(matches[0], indent=2))
    inp = evidence_input(candidate_path, qualify)
    if not inp['upstream_replay']:
        raise ValueError('This integration exercise accepts replay decisions only.')
    input_path = out / 'evidence-input.json'
    input_path.write_text(json.dumps(inp, indent=2))
    result = run(inp, out / 'evidence', data_dir=data_dir, as_of=date.fromisoformat(inp['qualification']['judged_as_of']))
    if result['run']['processing_status'] != 'completed':
        raise ValueError('Evidence did not complete: ' + json.dumps(result['run'].get('errors', [])))
    handoff_meta = result.get('file_handoff') or {}
    if not handoff_meta.get('evidence_json'):
        raise ValueError('Evidence produced no File handoff object.')
    result_path = Path(result['packet']['pdf_path']).parent / 'result.json'
    normalized = out / 'file-input' / 'case-handoff.json'
    envelope = evidence_handoff(candidate_path, qualify, result_path, handoff_meta['evidence_json'], normalized)
    form = out / 'official-dr486.pdf'
    fetch_form(form)
    manifest, prepared = prepare(normalized, out / 'file-output', form)
    checks = {
        'original_find_candidate_preserved': manifest['candidate'] == matches[0],
        'qualify_decision_preserved': envelope['qualification']['source']['original']['find_case_id'] == case_id,
        'evidence_case_identity_preserved': result['case_id'] == case_id == manifest['case_id'],
        'actual_packet_hash_preserved': digest(Path(result['packet']['pdf_path']).read_bytes()) == result['packet']['sha256'] == envelope['evidence']['artifact']['sha256'],
        'replay_remains_explicit': bool(result.get('replay')) and envelope['replay'],
        'review_not_invented': result['review']['status'] != 'approved',
        'authorization_not_invented': not envelope['authorization'],
        'file_stays_blocked': manifest['status'] == 'blocked',
        'nothing_submitted': manifest['submitted'] is False,
        'no_receipt_created': not (prepared / 'receipts.jsonl').exists(),
    }
    if not all(checks.values()):
        raise AssertionError(json.dumps(checks))
    report = {'kind': 'sourced_replay_integration', 'case_id': case_id, 'qualification_as_of': inp['qualification']['judged_as_of'], 'evidence_run': result['run']['run_id'], 'evidence_status': envelope['evidence']['status'], 'evidence_synthetic': result.get('synthetic', False), 'file_status': manifest['status'], 'submitted': False, 'checks': checks, 'passed': sum(checks.values()), 'holds': manifest['holds'], 'evidence_result': str(result_path), 'evidence_handoff': handoff_meta['evidence_json'], 'file_handoff': str(normalized), 'file_manifest': str(prepared / 'manifest.json'), 'petition': manifest['petition'], 'note': 'Real public source records and a published Qualify replay decision; no live eligibility, consent, approval, filing or revenue is asserted.'}
    (out / 'integration-report.json').write_text(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--find', required=True)
    parser.add_argument('--qualify', required=True)
    parser.add_argument('--case-id', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--data-dir')
    a = parser.parse_args()
    print(json.dumps(exercise(a.find, a.qualify, a.case_id, a.out, a.data_dir), indent=2))
