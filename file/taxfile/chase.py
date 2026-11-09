import json
import re
from datetime import date
from pathlib import Path
from .core import canonical, digest


def line(value, label, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or re.search(r'[\x00-\x1f\x7f\u2028\u2029]', value):
        raise ValueError(label + ' must be one non-empty line.')
    return value.strip()


def waiting_card(manifest, who, email, waiting_for, request_ref, every_days=3, last_chased='never'):
    if manifest.get('synthetic') or manifest.get('replay') or any(str(h).startswith(('Replay qualification cannot', 'Evidence replay dates', 'Synthetic handoffs cannot', 'Synthetic Evidence fixtures')) for h in manifest.get('holds', [])):
        raise ValueError('Replay and synthetic cases must not create live Chase follow-ups.')
    case_id = line(manifest.get('case_id'), 'Find case_id', 250)
    if not re.fullmatch(r'FL-\d{2}-\d{4}-.+', case_id):
        raise ValueError('A stable Find case_id is required; unknown or internal replacement IDs are not accepted.')
    candidate = manifest.get('candidate') or {}
    if candidate.get('case_id') and candidate['case_id'] != case_id:
        raise ValueError('The manifest case_id does not match its original Find candidate.')
    filing = manifest.get('filing') or {}
    if filing.get('level', 'vab_petition') != 'vab_petition':
        raise ValueError('This File adapter only creates vab_petition follow-ups.')
    who = line(who, 'Recipient name')
    email = line(email, 'Recipient email', 254)
    if not re.fullmatch(r'[^@\s,<>]+@[^@\s,<>]+\.[^@\s,<>]+', email):
        raise ValueError('A verified single recipient email is required.')
    waiting_for = line(waiting_for, 'Waiting reason')
    request_ref = line(request_ref, 'Original request reference', 1000)
    if type(every_days) is not int or not 1 <= every_days <= 30:
        raise ValueError('Follow-up frequency must be an integer from 1 to 30 days.')
    if last_chased != 'never':
        if not isinstance(last_chased, str) or date.fromisoformat(last_chased).isoformat() != last_chased:
            raise ValueError('Last chased must be never or an actual YYYY-MM-DD date.')
    body = [f'case_id: {case_id}', 'level: vab_petition', f'waiting_for: {waiting_for}', f'original_request: {request_ref}', f'follow_up: {who} {email}, every {every_days} days, last chased {last_chased}']
    receipt = manifest.get('receipt') or {}
    if receipt.get('confirmation_id'):
        body.append('confirmation_id: ' + line(receipt['confirmation_id'], 'Confirmation number'))
    deadline = manifest.get('response_deadline')
    if deadline:
        if not (manifest.get('notice') or {}).get('sha256'):
            raise ValueError('A response deadline needs its stored notice proof.')
        date.fromisoformat(deadline)
        body.append('response_deadline: ' + deadline)
    else:
        body.append('response_deadline: unknown; obtain the actual county notice')
    refiling = manifest.get('refiling')
    if refiling:
        if not isinstance(refiling, dict):
            raise ValueError('Refiling context must be an object.')
        body += ['refiling: yes', 'prior_receipt: ' + line(refiling.get('prior_receipt_ref'), 'Prior receipt reference'), 'correction: ' + line(refiling.get('reason'), 'Correction reason')]
    body.append('Submission and clerk acceptance must be established by their actual receipts; this follow-up card is not proof of filing.')
    key = 'file-wait-' + digest(canonical([case_id, 'vab_petition', email.lower(), waiting_for, request_ref]))[:24]
    return {'title': ('Waiting on ' + who + ' · ' + waiting_for)[:200], 'body': '\n'.join(body), 'status': 'blocked', 'assignee': 'File', 'key': key}


def card_from_file(manifest_path, **options):
    manifest = json.loads(Path(manifest_path).read_text())
    if not isinstance(manifest, dict):
        raise ValueError('File manifest must be an object.')
    return waiting_card(manifest, **options)
