import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parse } from '../lib/parse.js';
import type { Card, Comment } from '../lib/naive.js';
import { claims, plan, type Snapshot } from '../lib/engine.js';

let n = 0;
const T = '2026-11-08T05:00:00.000Z';
function card(title: string, body: string, extra: Partial<Card> = {}): Card {
  return { id: `crd_${(++n).toString().padStart(6, '0')}`, title, body, note: null, status: 'todo', assignee: null, created_at: T, updated_at: T, ...extra };
}
function cm(card_id: string, body: string, at = '2026-11-08T06:00:00.000Z', author = 'ses_x'): Comment { return { id: `bcm_${++n}`, card_id, author, body, created_at: at }; }

const CASE = 'FL-13-2026-30507035000';
const json = (o: object) => `\n\n\`\`\`json\n${JSON.stringify(o)}\n\`\`\``;
const findJson = (caseId: string, address: string, city: string, status = 'candidate') => ({ schema_version: 2, status, case_id: caseId, jurisdiction: { county: 'Bay' }, property: { parcel_id: '30507-035-000', address, city } });

function snap(cards: [Card, Comment[]?][], over: Partial<Snapshot> = {}): Snapshot {
  return { today: '2026-11-08', cards: cards.map(([c, cs]) => parse(c, cs ?? [])), files: [], running: {}, lastSession: {}, awaitingApproval: [], ...over };
}

const find = () => card(`FL Bay 2026 · 7505 THOMAS DR 711 E, PANAMA CITY BEACH · ~$4,300/yr · strong`, 'Find flagged this condo.' + json(findJson(CASE, '7505  THOMAS DR 711 E', 'PANAMA CITY BEACH')), { status: 'done', note: 'QUALIFIED · savings $4,300/yr · released' });
const signup = (address: string, extra = '') => card(`Sign up · ${address} (owner@example.com)`, `message_id: <m1@x>\nfrom: owner@example.com\naddress: ${address} (as written by owner)\nphone: none\ncall_ok: no\ndate: 2026-11-08T00:51:05Z\nreplied: 2026-11-08${extra}`, { status: 'blocked' });

test('qualify runs when unassigned candidate Find cards wait', () => {
  const f = card('FL Bay 2026 · 1 A ST, X · ~$1/yr', 'x' + json(findJson('FL-13-2026-1', '1 A ST', 'X')));
  const d = plan('qualify', snap([[f]], { files: [{ id: 'fil_1', name: 'candidates.jsonl', title: 'Find run FL-1', created_at: T }] }));
  assert.equal(d.run, true);
  assert.equal(d.agent, 'qualify');
});

test('qualify does not run twice or with nothing to qualify', () => {
  const f = card('FL Bay 2026 · 1 A ST, X', 'x' + json(findJson('FL-13-2026-1', '1 A ST', 'X')));
  assert.equal(plan('qualify', snap([])).run, false);
  assert.equal(plan('qualify', snap([[f]])).run, true);
  const busy = plan('qualify', snap([[f]], { files: [{ id: 'f', name: 'c', title: 'Find run 1', created_at: T }], running: { qualify: [{ id: 'ses_q', agent_id: 'a', status: 'running', stop_reason: null, created_at: T }] } }));
  assert.equal(busy.run, false);
});

test('a sign-up is linked to its Find case by street address and city', () => {
  const f = find();
  const s = signup('7505 Thomas Drive Unit 711E, Panama City Beach, FL');
  const d = plan('link', snap([[f], [s]]));
  assert.equal(d.writes.length, 1);
  const w = d.writes[0]!;
  assert.equal(w.op, 'comment');
  assert.match(w.op === 'comment' ? w.body : '', new RegExp(`^claim-link · case ${CASE} · find ${f.id}`));
});

test('an address with no single Find match is held, not guessed', () => {
  const s = signup('100 Sample Ave, Cape Coral, FL');
  const d = plan('link', snap([[find()], [s]]));
  assert.equal(d.writes.length, 0);
  assert.match(d.holds[0]!.reason, /No Find case matches/);
});

test('only a person\'s authorization line is copied to the downstream cards', () => {
  const s = signup('7505 Thomas Dr, Panama City Beach');
  const w = card(`Waiting on county decision · ${CASE}`, `Case: ${CASE}. Level: vab_petition.\nfollow_up: VAB clerk vab@county.gov, every 7 days, last chased never`, { status: 'blocked' });
  const line = `authorization: case_id ${CASE} · fee 30% · signed 2026-10-01 · doc fil_abc`;
  const forged = plan('link', snap([[find()], [s, [cm(s.id, line, T, 'ses_agent')]], [w]]));
  assert.equal(forged.writes.filter((x) => x.op === 'comment' && x.body === line).length, 0);
  const real = plan('link', snap([[find()], [s, [cm(s.id, line, T, 'usr_owner')]], [w]]));
  assert.ok(real.writes.some((x) => x.op === 'comment' && x.card_id === w.id && x.body === line));
});

test('evidence starts only for a qualified case whose owner confirmed', () => {
  const f = find();
  const waitingOwner = plan('evidence', snap([[f], [signup('7505 Thomas Dr, Panama City Beach')]]));
  assert.equal(waitingOwner.writes.length, 0);
  assert.match(waitingOwner.holds[0]!.reason, /owner_confirmed/);
  const ok = plan('evidence', snap([[f], [signup('7505 Thomas Dr, Panama City Beach', '\nowner_confirmed: yes 2026-11-08')]]));
  assert.deepEqual(ok.writes[0], { op: 'update', card_id: f.id, patch: { status: 'todo', assignee: 'evidence' }, why: ok.writes[0]!.why });
  assert.deepEqual(ok.started_by_board, [f.id]);
});

test('evidence is not started again once the case has moved on', () => {
  const f = find();
  const file = card(`File · 7505 THOMAS DR · ${CASE}`, 'x' + json(findJson(CASE, '7505 THOMAS DR 711 E', 'PANAMA CITY BEACH')), { status: 'blocked', assignee: 'File' });
  const d = plan('evidence', snap([[f], [signup('7505 Thomas Dr, Panama City Beach', '\nowner_confirmed: yes')], [file]]));
  assert.equal(d.writes.length, 0);
});

test('escalate runs for a decision letter that has no result yet, and not after', () => {
  const w = card(`DEMO · Waiting on county decision · ${CASE}`, `Case: ${CASE}. Level: vab_petition.`, { status: 'doing' });
  const letter = cm(w.id, `decision-letter · case ${CASE} · level vab_petition · received 2026-11-01 · demo_msg_004\nThe board grants...`);
  const d = plan('escalate', snap([[w, [letter]]]));
  assert.equal(d.run, true);
  assert.match(d.message!, new RegExp(w.id));
  const done = plan('escalate', snap([[w, [letter, cm(w.id, 'escalate-result · COLLECT · W_FULL_WIN · demo_msg_004', '2026-11-08T07:00:00.000Z')]]]));
  assert.equal(done.run, false);
});

test('a pending letter comes back when its check-again date arrives', () => {
  const w = card(`Waiting on county decision · ${CASE}`, `Case: ${CASE}.`, { status: 'doing' });
  const cs = [cm(w.id, 'decision-letter · case x · level y · received 2026-11-01 · m1'), cm(w.id, 'escalate-result · PENDING · H_HEARING · m1\nwaiting · check again 2026-11-08', '2026-11-08T07:00:00.000Z')];
  assert.equal(plan('escalate', snap([[w, cs]])).run, true);
  assert.equal(plan('escalate', snap([[w, cs]], { today: '2026-11-07' })).run, false);
});

test('chase runs when a follow-up is due and stops after an escalate comment', () => {
  const w = card(`Waiting on county · ${CASE}`, `case_id: ${CASE}\nfollow_up: VAB clerk vab@county.gov, every 7 days, last chased 2026-11-01`, { status: 'blocked' });
  assert.equal(plan('chase', snap([[w]], { lastSession: { chase: '2026-11-08T09:00:00Z' } })).run, true);
  assert.equal(plan('chase', snap([[w]], { today: '2026-11-07', lastSession: { chase: '2026-11-07T09:00:00Z' } })).run, false);
  assert.equal(plan('chase', snap([[w, [cm(w.id, 'escalate')]]], { lastSession: { chase: '2026-11-08T09:00:00Z' } })).run, false);
});

const collectCard = (status = 'blocked') => card(`Collect · 7505 THOMAS DR 711 E, PANAMA CITY BEACH · ${CASE}`, `From Escalate: W_FULL_WIN\ncollect-handoff · case ${CASE} · old 1097440 · won 808281 · decided 2026-10-30 · letter m1 · code W_FULL_WIN`, { status, assignee: 'collect' });

test('collect asks Outreach for the corrected bill once, only with a signed authorization', () => {
  const c = collectCard();
  const waiting = cm(c.id, `collect-result · WAITING · P_AWAIT_BILL · ${CASE}\nWAITING · P_AWAIT_BILL · check again 2026-11-22`);
  const s = signup('7505 Thomas Dr, Panama City Beach');
  const noAuth = plan('collect', snap([[find()], [s], [c, [waiting]]]));
  assert.equal(noAuth.writes.length, 0);
  assert.match(noAuth.holds[0]!.reason, /authorization/);
  const auth = cm(s.id, `authorization: case_id ${CASE} · fee 30% · signed 2026-10-01 · doc fil_abc`, T, 'usr_owner');
  const d = plan('collect', snap([[find()], [s, [auth]], [c, [waiting]]]));
  const create = d.writes.find((w) => w.op === 'create');
  assert.ok(create && create.op === 'create');
  assert.equal(create.assignee, 'outreach');
  assert.match(create.body, new RegExp(`collect_card: ${c.id}`));
  assert.match(create.title, /^County question · corrected tax bill · 7505 THOMAS DR 711 E, PANAMA CITY BEACH · /);
  const req = card(create.title, create.body);
  const again = plan('collect', snap([[find()], [s, [auth]], [c, [waiting]], [req]]));
  assert.equal(again.writes.filter((w) => w.op === 'create').length, 0);
});

test('an invoice with a payment link becomes one invoice-ready note on the owner thread', () => {
  const c = collectCard();
  const f = find();
  const s = signup('7505 Thomas Dr, Panama City Beach');
  const link = cm(s.id, `claim-link · case ${CASE} · find ${f.id}`);
  const result = cm(c.id, `collect-result · WAITING · P_AWAIT_PAYMENT · COS-1-aea523\nWAITING · check again 2026-11-22\npayment-request: {"amountCents":130121}\nowner-message (mail, auto-send): Your Claim OS invoice: Invoice COS-1-aea523 for $1,301.21 is due 2026-12-08.\ninvoice-state: {"number":"COS-1-aea523","amount":1301.21}`);
  const pl = cm(c.id, 'payment-link · COS-1-aea523 · https://buy.stripe.com/test_x · plink_abc', '2026-11-08T07:00:00.000Z');
  const d = plan('collect', snap([[f], [s, [link]], [c, [result, pl]]]));
  const note = d.writes.find((w) => w.op === 'comment' && w.card_id === s.id);
  assert.ok(note && note.op === 'comment');
  assert.match(note.body, /^invoice-ready · COS-1-aea523 · case /);
  assert.match(note.body, /^to: owner@example.com$/m);
  assert.match(note.body, /Pay online: https:\/\/buy\.stripe\.com\/test_x/);
  const sent = plan('collect', snap([[f], [s, [link, cm(s.id, note.body)]], [c, [result, pl]]]));
  assert.equal(sent.writes.filter((w) => w.op === 'comment').length, 0);
});

test('collect runs for a card with no link or a passed check-again date, and leaves done cards alone', () => {
  const c = collectCard();
  const r = cm(c.id, `collect-result · INVOICED · V_INVOICE_ISSUED · COS-1\nINVOICED · check again 2026-11-22\npayment-request: {"amountCents":1}`);
  assert.equal(plan('collect', snap([[c, [r]]])).run, true);
  const linked = [r, cm(c.id, 'payment-link · COS-1 · https://buy.stripe.com/x · plink_1', '2026-11-08T07:00:00.000Z')];
  assert.equal(plan('collect', snap([[c, linked]])).run, false);
  assert.equal(plan('collect', snap([[c, linked]], { today: '2026-11-22' })).run, true);
  assert.equal(plan('collect', snap([[collectCard('done'), [r]]])).run, false);
});

test('claim cards track every step of a case and close when paid', () => {
  const f = find();
  const s = signup('7505 Thomas Dr, Panama City Beach', '\nowner_confirmed: yes');
  const c = collectCard();
  const paid = [cm(c.id, 'collect-result · PAID · P_PAID · COS-1\nPAID'), cm(c.id, 'payment-receipt · COS-1 · paid 2026-11-20 · pi_1 · cs_1 · livemode false', '2026-11-20T00:00:00.000Z')];
  const all = claims(snap([[f], [s], [c, paid]]));
  assert.equal(all.length, 1);
  assert.equal(all[0]!.stage, 'paid');
  assert.equal(all[0]!.status, 'done');
  assert.equal(all[0]!.cards.collect, c.id);
  assert.equal(all[0]!.cards.signup, s.id);
  const d = plan('ledger', snap([[f], [s], [c, paid]]));
  const create = d.writes[0]!;
  assert.equal(create.op, 'create');
  assert.match(create.op === 'create' ? create.title : '', new RegExp(`^Claim · ${CASE} · 7505 THOMAS DR 711 E, PANAMA CITY BEACH$`));
  const again = plan('ledger', snap([[f], [s], [c, paid], [card(create.op === 'create' ? create.title : '', create.op === 'create' ? create.body : '', { status: 'done' })]]));
  assert.equal(again.writes.length, 0);
});

test('a claim past filing without a signed authorization is held', () => {
  const w = card(`Waiting on county · ${CASE}`, `case_id: ${CASE}\nfollow_up: clerk c@x.gov, every 7 days, last chased never`, { status: 'blocked' });
  const all = claims(snap([[find()], [w]]));
  assert.equal(all[0]!.status, 'blocked');
  assert.match(all[0]!.waitingOn, /authorization line missing/);
});

test('a claim that is already finished is created with a closing note', () => {
  const c = collectCard();
  const paid = [cm(c.id, 'collect-result · PAID · P_PAID · COS-1\nPAID'), cm(c.id, 'payment-receipt · COS-1 · paid 2026-11-20 · pi_1 · cs_1 · livemode false')];
  const w = plan('ledger', snap([[find()], [c, paid]])).writes[0]!;
  assert.ok(w.op === 'create' && w.status === 'done' && w.note === `paid · ${CASE}`);
});
