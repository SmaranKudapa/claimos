import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PDFDocument } from 'pdf-lib';
import { parse } from '../lib/parse.js';
import type { Card, Comment } from '../lib/naive.js';
import { briefingWrites, plan, type Snapshot, type WebsiteSignup } from '../lib/engine.js';
import { buildDeck, renderHtml } from '../lib/briefing.js';
import { briefingInput } from '../lib/inputs.js';
import { renderPdf } from '../lib/pdf.js';

let n = 0;
const T = '2026-11-08T05:00:00.000Z';
const card = (title: string, body: string, extra: Partial<Card> = {}): Card => ({ id: `crd_b${(++n).toString().padStart(5, '0')}`, title, body, note: null, status: 'todo', assignee: null, created_at: T, updated_at: T, ...extra });
const cm = (card_id: string, body: string, author = 'ses_x'): Comment => ({ id: `bcm_${++n}`, card_id, author, body, created_at: '2026-11-08T06:00:00.000Z' });
const CASE = 'FL-13-2026-30507035000';
const caseJson = { schema_version: 2, status: 'candidate', case_id: CASE, jurisdiction: { county: 'Bay' }, property: { parcel_id: '30507-035-000', address: '7505  THOMAS DR 711 E', city: 'PANAMA CITY BEACH', use: 'condo' }, values: { just_value: 1097440, assessed_value: 1097440, taxable_value: 1097440 }, estimate: { defensible_value: 808281, annual_savings: 4337, annual_savings_range: [3200, 5100] }, filing_window: { closes: '2026-09-09', status: 'closed' }, full_record: { run_id: 'FL-1', file: 'candidates.jsonl' } };
const find = () => card('FL Bay 2026 · 7505 THOMAS DR 711 E, PANAMA CITY BEACH', `Find flagged this condo.\n\n\`\`\`json\n${JSON.stringify(caseJson)}\n\`\`\``, { status: 'done', note: 'QUALIFIED · savings $4,337/yr · fee $1,301 · P(win) 0.825 · DR-486 due 2026-09-09 · released' });
const snap = (cards: [Card, Comment[]?][], over: Partial<Snapshot> = {}): Snapshot => ({ today: '2026-11-08', cards: cards.map(([c, cs]) => parse(c, cs ?? [])), files: [], running: {}, lastSession: {}, awaitingApproval: [], config: { publicUrl: 'https://flow.example', presenterEmail: 'pro@example.com', bookingUrl: 'https://calendar.app.google/abc' }, ...over });
const row = (over: Partial<WebsiteSignup> = {}): WebsiteSignup => ({ id: '11111111-2222-3333-4444-555555555555', created_at: T, address: '7505 Thomas Dr Unit 711E', city: 'Panama City Beach', zip: '32408', email: 'owner@example.com', phone: null, call_ok: false, consent: true, case_id: CASE, notes: 'Requested a call with a licensed tax professional', ...over });

const full = {
  case_id: CASE, property: { address: '7505  THOMAS DR 711 E', city: 'PANAMA CITY BEACH', sqft: 2100, effective_year_built: 2006, use: 'condo' },
  values: { just_value: 1097440, assessed_value: 1097440, taxable_value: 1097440 },
  signals: { neighbor_ratio: 1.61, neighbor_count: 344, sales_ratio: 1.59, comp_count: 38 },
  evidence: { neighbors: [{ address: '7505 THOMAS DR 1522P', sqft: 3094, just_value: 1466097, value_per_sqft: 473.85 }, { address: '7505 THOMAS DR 912', sqft: 2100, just_value: 690000, value_per_sqft: 328.57 }], sales: [{ address: '4136 COBALT CIR', sale_month: '2025-08', price: 525000, price_adjusted_to_valuation_date: 501800, sqft: 2939 }] },
  estimate: { defensible_value: 808281, annual_savings: 4337, annual_savings_range: [3200, 5100], millage: 0.015 },
  warnings: ['Owner of record may have changed since the rank order'], owner: { may_have_changed: true }, filing_window: { closes: '2026-09-09', status: 'closed' },
};
const packet = { requested_just_value: 800000, current_just_value: 1097440, subject: { sqft: 2100, year_built: 2006 }, sales_approach: { comps: [{ address: '7505 THOMAS DR 905', sale_date: '2025-06-01', sale_price: 815000, adjusted_price: 790000, sqft: 2050, arms_length: true, per_sqft: 385.4 }, { address: 'NOT ARMS LENGTH', sale_date: '2025-01-01', sale_price: 1, arms_length: false }] }, equity_approach: { peers: 8, median_per_sqft: 390.1, subject_per_sqft: 522.6, indicated_just_value: 819000 }, deadlines: { petition: '2026-09-09' } };

test('intake turns a consenting website sign-up into one Sign up card, once', () => {
  const f = find();
  const d = plan('intake', snap([[f]], { signups: [row(), row({ id: 'no-consent', email: 'x@example.com', consent: false })] }));
  assert.equal(d.writes.length, 1);
  const w = d.writes[0]!;
  assert.ok(w.op === 'create');
  assert.equal(w.title, 'Sign up · 7505 Thomas Dr Unit 711E, Panama City Beach (owner@example.com)');
  assert.match(w.body, /^source: website$/m);
  assert.match(w.body, /^pro_call: yes$/m);
  assert.match(w.body, new RegExp(`^case_id: ${CASE}$`, 'm'));
  const again = plan('intake', snap([[f], [card(w.title, w.body, { status: 'blocked' })]], { signups: [row()] }));
  assert.equal(again.writes.length, 0);
});

test('a website sign-up from an owner who already has a card is held, not duplicated', () => {
  const existing = card('Sign up · 7505 Thomas Dr (owner@example.com)', 'message_id: <m1>\nfrom: owner@example.com\naddress: 7505 Thomas Dr, Panama City Beach', { status: 'blocked' });
  const d = plan('intake', snap([[find()], [existing]], { signups: [row()] }));
  assert.equal(d.writes.length, 0);
  assert.match(d.holds[0]!.reason, /already has a Sign up card/);
});

test('a professional-call request gets a deck built, then rebuilt once Evidence has a packet', () => {
  const f = find();
  const s = card('Sign up · 7505 Thomas Dr (owner@example.com)', `source: website\nsignup_id: x\nfrom: owner@example.com\naddress: 7505 Thomas Dr Unit 711E, Panama City Beach\npro_call: yes\ncase_id: ${CASE}`, { status: 'blocked' });
  const first = plan('briefing', snap([[f], [s]]));
  assert.deepEqual(first.builds, [{ caseId: CASE, findCardId: f.id, signupCardId: s.id, version: 1 }]);
  const built = { case_id: CASE, token: 'tok_abcdefghijklmnopqrstu', version: 1, has_evidence: false };
  assert.deepEqual(plan('briefing', snap([[f], [s]], { briefings: [built] })).builds, []);
  assert.equal(plan('briefing', snap([[f], [s]], { briefings: [built], evidenceReady: [CASE] })).builds![0]!.version, 2);
});

test('no deck without a request, and an unmatched request is held', () => {
  const plain = card('Sign up · 1 A St, X (a@example.com)', 'from: a@example.com\naddress: 1 A St, X\npro_call: no', { status: 'blocked' });
  assert.deepEqual(plan('briefing', snap([[find()], [plain]])).builds, []);
  const lost = card('Sign up · 1 A St, X (b@example.com)', 'from: b@example.com\naddress: 1 A St, X\npro_call: yes', { status: 'blocked' });
  const d = plan('briefing', snap([[find()], [lost]]));
  assert.match(d.holds[0]!.reason, /professional call was requested/);
});

test('the briefing card carries everything the agent needs, and updates do not re-send to the owner', () => {
  const f = find();
  const s = card('Sign up · 7505 Thomas Dr (owner@example.com)', `message_id: <m1@x>\nfrom: owner@example.com\naddress: 7505 Thomas Dr Unit 711E, Panama City Beach\npro_call: yes`, { status: 'blocked' });
  const sn = snap([[f], [s, [cm(s.id, `claim-link · case ${CASE} · find ${f.id}`)]]]);
  const [note, create] = briefingWrites(sn, { caseId: CASE, findCardId: f.id, signupCardId: s.id, version: 1 }, 'tok_abcdefghijklmnopqrstu');
  assert.ok(note!.op === 'comment' && note!.body.startsWith(`briefing-ready · v1 · case ${CASE}`));
  assert.ok(create!.op === 'create' && create!.assignee === 'briefing');
  assert.match(create!.body, /^source: email$/m);
  assert.match(create!.body, /^reply_to_message: <m1@x>$/m);
  assert.match(create!.body, /^pdf_url: https:\/\/flow\.example\/b\/tok_abcdefghijklmnopqrstu\.pdf$/m);
  assert.match(create!.body, /^booking_url: https:\/\/calendar\.app\.google\/abc$/m);
  assert.match(create!.body, /^update_only: no$/m);
  const later = snap([[f], [s, [cm(s.id, `claim-link · case ${CASE} · find ${f.id}`), cm(s.id, 'briefing-sent · v1 · 2026-11-08 · <out@x>')]], [card(`Briefing · 7505 THOMAS DR 711 E, PANAMA CITY BEACH · ${CASE}`, 'x', { status: 'done', assignee: 'briefing' })]]);
  const [, update] = briefingWrites(later, { caseId: CASE, findCardId: f.id, signupCardId: s.id, version: 2 }, 'tok_abcdefghijklmnopqrstu');
  assert.ok(update!.op === 'update' && update!.patch.status === 'todo' && update!.patch.assignee === 'briefing');
  assert.match(update!.patch.body!, /^update_only: yes$/m);
});

const presenter = { name: null, title: 'Claim OS appeal specialist', license: null };

test('the deck is built from Find, Qualify and Evidence, and never promises a win', () => {
  const f = parse(find());
  const deck = buildDeck(briefingInput(f, full, packet, 0.3), { version: 2, today: '2026-11-08', presenter, bookingUrl: 'https://calendar.app.google/abc' });
  const text = JSON.stringify(deck);
  assert.equal(deck.hasEvidence, true);
  assert.equal(deck.address, '7505 THOMAS DR 711 E, PANAMA CITY BEACH');
  assert.ok(deck.slides.length >= 8);
  assert.match(text, /\$1,097,440/);
  assert.match(text, /Lower the value to about \$800,000/);
  assert.match(text, /7505 THOMAS DR 905/);
  assert.doesNotMatch(text, /NOT ARMS LENGTH/);
  assert.match(text, /about a 83% chance of some reduction\. It is an estimate, not a promise\./);
  assert.match(text, /The 2026 petition deadline was 2026-09-09/);
  assert.match(text, /30% of the first year's tax saving/);
  assert.match(text, /owner of record may have changed/);
  assert.doesNotMatch(text, /we will win|guarantee|licensed/i);
  for (const s of deck.slides) assert.ok(s.notes.length > 20, `${s.title} has speaker notes`);
});

test('a deck still builds from the board card alone, before the full record or Evidence', () => {
  const deck = buildDeck(briefingInput(parse(find()), null, null, 0.3), { version: 1, today: '2026-11-08', presenter, bookingUrl: null });
  assert.equal(deck.hasEvidence, false);
  assert.match(JSON.stringify(deck), /Lower the value to about \$808,281/);
  assert.match(JSON.stringify(deck), /Reply to our email with a few times/);
});

test('"licensed" appears only when a license is configured', () => {
  const lic = buildDeck(briefingInput(parse(find()), full, null, 0.3), { version: 1, today: '2026-11-08', presenter: { name: 'Pat Doe', title: 'licensed tax professional', license: 'FL 12345' }, bookingUrl: null });
  assert.match(JSON.stringify(lic.slides[0]), /Pat Doe, licensed tax professional \(license FL 12345\)/);
});

test('the slideshow page escapes data and the PDF has one page per slide', async () => {
  const evil = { ...full, property: { ...full.property, address: '<script>x</script>' } };
  const deck = buildDeck(briefingInput(parse(find()), evil, packet, 0.3), { version: 1, today: '2026-11-08', presenter, bookingUrl: null });
  const html = renderHtml(deck, { present: true, pdfUrl: '/b/t.pdf' });
  assert.doesNotMatch(html, /<script>x<\/script>/);
  assert.match(html, /class="present"/);
  assert.match(html, /Speaker notes/);
  const bytes = await renderPdf(deck);
  assert.equal(Buffer.from(bytes.slice(0, 5)).toString(), '%PDF-');
  assert.equal((await PDFDocument.load(bytes)).getPageCount(), deck.slides.length);
});

test('the median bar names how many homes it was computed from', () => {
  const noPacket = buildDeck(briefingInput(parse(find()), full, null, 0.3), { version: 1, today: '2026-11-08', presenter, bookingUrl: null });
  assert.equal(noPacket.slides.find((s) => s.bars)!.bars!.items[1]!.label, 'Median of 2 similar homes');
  const withPacket = buildDeck(briefingInput(parse(find()), full, packet, 0.3), { version: 1, today: '2026-11-08', presenter, bookingUrl: null });
  assert.equal(withPacket.slides.find((s) => s.bars)!.bars!.items[1]!.label, 'Median of 8 similar homes');
});
