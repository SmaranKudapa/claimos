import type { FileRow, SessionRow } from './naive.js';
import { addDays, collectState, escalateResults, findAddress, firstLine, followUp, letters, lineValue, sameStreet, signupAddress, stripDemo, type Parsed } from './parse.js';

export const STEPS = ['qualify', 'intake', 'link', 'briefing', 'evidence', 'chase', 'escalate', 'collect', 'ledger'] as const;
export type Step = typeof STEPS[number];

export interface WebsiteSignup { id: string; created_at: string; address: string; city: string | null; zip: string | null; email: string; phone: string | null; call_ok: boolean | null; consent: boolean | null; case_id: string | null; notes: string | null; }
export interface BriefingRow { case_id: string; token: string; version: number; has_evidence: boolean; }
export interface FlowConfig { publicUrl: string | null; presenterEmail: string | null; bookingUrl: string | null; }

export interface Snapshot {
  today: string;
  cards: Parsed[];
  files: FileRow[];
  running: Record<string, SessionRow[]>;
  lastSession: Record<string, string | null>;
  awaitingApproval: { agent: string; session: string; since: string }[];
  signups?: WebsiteSignup[];
  briefings?: BriefingRow[];
  evidenceReady?: string[];
  config?: FlowConfig;
}

export interface Build { caseId: string; findCardId: string; signupCardId: string; version: number; }

export type Write =
  | { op: 'comment'; card_id: string; body: string; why: string }
  | { op: 'update'; card_id: string; patch: { status?: string; assignee?: string | null; body?: string; title?: string; note?: string }; why: string }
  | { op: 'create'; key: string; title: string; body: string; status: string; assignee: string | null; note?: string; why: string };

export interface Hold { case_id: string | null; card_id: string; reason: string; }

export interface Decision {
  step: Step;
  today: string;
  run: boolean;
  agent: string | null;
  message: string | null;
  reason: string;
  writes: Write[];
  holds: Hold[];
  started_by_board: string[];
  builds?: Build[];
}

export const MAX_ASSIGN = 10;

const PERSON = /^usr_/;

function decision(step: Step, snap: Snapshot, partial: Partial<Decision>): Decision {
  return { step, today: snap.today, run: false, agent: null, message: null, reason: '', writes: [], holds: [], started_by_board: [], ...partial };
}

function byKind(snap: Snapshot, kind: Parsed['kind']) { return snap.cards.filter((p) => p.kind === kind); }

function hasComment(p: Parsed, test: (body: string) => boolean) { return p.comments.some((c) => test(c.body)); }

export function qualifyNote(p: Parsed) {
  const note = p.card.note ?? '';
  const m = note.match(/^(QUALIFIED|REJECTED|NEXT_CYCLE|INCOMPLETE|NEEDS_REVIEW|EVIDENCE)\b/);
  return { verdict: m?.[1] ?? null, released: /· released\b/.test(note) };
}

function isCandidate(p: Parsed) {
  return p.kind === 'find' && p.card.status === 'todo' && !p.card.assignee && p.json?.schema_version === 2 && p.json?.status === 'candidate';
}

export function planQualify(snap: Snapshot): Decision {
  const waiting = snap.cards.filter(isCandidate).length;
  const findRun = snap.files.filter((f) => (f.title ?? '').startsWith('Find run ')).map((f) => f.created_at).sort().at(-1) ?? null;
  const qualifyRun = snap.files.filter((f) => (f.title ?? '').startsWith('Qualify run ')).map((f) => f.created_at).sort().at(-1) ?? null;
  if (snap.running.qualify?.length) return decision('qualify', snap, { reason: `Qualify is already running (${snap.running.qualify[0]!.id}).` });
  if (!findRun && waiting === 0) return decision('qualify', snap, { reason: 'No Find run has been published yet.' });
  if (waiting === 0 && qualifyRun && findRun && qualifyRun >= findRun) return decision('qualify', snap, { reason: 'No unqualified Find cards and the newest Find run is already qualified.' });
  return decision('qualify', snap, {
    run: true,
    agent: 'qualify',
    message: 'Run your Qualify pass now on the newest Find run.',
    reason: waiting ? `${waiting} Find cards are waiting for Qualify.` : `Find run of ${findRun} is newer than the last Qualify run (${qualifyRun ?? 'none'}).`,
  });
}

export interface Link { signup: Parsed; find: Parsed | null; caseId: string | null; problem: string | null; }

export function links(snap: Snapshot): Link[] {
  const finds = byKind(snap, 'find');
  return byKind(snap, 'signup').filter((s) => s.card.status !== 'done').map((s) => {
    const done = s.comments.map((c) => firstLine(c.body).match(/^claim-link · case (.+?) · find (crd_\w+)$/)).filter(Boolean).at(-1);
    if (done) return { signup: s, find: finds.find((f) => f.card.id === done[2]) ?? null, caseId: done[1]!, problem: null };
    const stated = s.card.body.match(/^case_id:\s*(.+?)\s*$/m)?.[1];
    const byCase = stated ? finds.filter((f) => f.caseId === stated) : [];
    if (byCase.length) { const find = byCase.find((h) => qualifyNote(h).verdict === 'QUALIFIED') ?? byCase[0]!; return { signup: s, find, caseId: stated!, problem: null }; }
    const addr = signupAddress(s);
    if (!addr) return { signup: s, find: null, caseId: null, problem: 'The owner has not given a full street address and city yet.' };
    const hits = finds.filter((f) => { const a = findAddress(f); return a && sameStreet(a.street, addr.street) && a.city === addr.city; });
    const cases = [...new Set(hits.map((h) => h.caseId))];
    if (cases.length === 0) return { signup: s, find: null, caseId: null, problem: `No Find case matches ${addr.street}, ${addr.city}.` };
    if (cases.length > 1) return { signup: s, find: null, caseId: null, problem: `${cases.length} Find cases match ${addr.street}, ${addr.city}; a person picks one.` };
    const find = hits.find((h) => qualifyNote(h).verdict === 'QUALIFIED') ?? hits[0]!;
    return { signup: s, find, caseId: find.caseId, problem: null };
  });
}

export function authorizations(snap: Snapshot): Map<string, string> {
  const out = new Map<string, string>();
  for (const s of byKind(snap, 'signup')) for (const c of s.comments) {
    if (!PERSON.test(c.author)) continue;
    for (const l of c.body.split('\n')) {
      const m = l.match(/^authorization:\s*case_id\s+(FL-\d{2}-\d{4}-\S+(?: \S+)*?)\s*·.*$/i);
      if (m) out.set(m[1]!, l.trim());
    }
  }
  return out;
}

function caseCards(snap: Snapshot, caseId: string, kinds: Parsed['kind'][]) {
  return snap.cards.filter((p) => p.caseId === caseId && kinds.includes(p.kind));
}

export function planLink(snap: Snapshot): Decision {
  const writes: Write[] = [];
  const holds: Hold[] = [];
  for (const l of links(snap)) {
    if (l.problem) { holds.push({ case_id: null, card_id: l.signup.card.id, reason: l.problem }); continue; }
    const linked = l.signup.comments.some((c) => firstLine(c.body).startsWith('claim-link · '));
    if (!linked && l.find) writes.push({ op: 'comment', card_id: l.signup.card.id, body: `claim-link · case ${l.caseId} · find ${l.find.card.id}\nMatched by the owner's street address and city to Find card ${l.find.card.id}.`, why: 'link Sign up to its Find case' });
  }
  for (const [caseId, line] of authorizations(snap)) {
    for (const p of caseCards(snap, caseId, ['file', 'waiting', 'collect', 'evidence'])) {
      if (p.card.status === 'done' && p.kind !== 'collect') continue;
      if (p.card.body.includes(line) || hasComment(p, (b) => b.includes(line))) continue;
      writes.push({ op: 'comment', card_id: p.card.id, body: line, why: `copy the signed authorization for ${caseId}` });
    }
  }
  return decision('link', snap, { writes, holds, reason: `${writes.length} link or authorization writes, ${holds.length} sign-ups held.` });
}

export function planEvidence(snap: Snapshot): Decision {
  const writes: Write[] = [];
  const holds: Hold[] = [];
  const started: string[] = [];
  for (const l of links(snap)) {
    if (!l.find || !l.caseId) continue;
    const q = qualifyNote(l.find);
    const confirmed = /^yes\b/i.test(lineValue(l.signup, 'owner_confirmed') ?? '');
    const busy = l.find.card.assignee === 'evidence' || q.verdict === 'EVIDENCE' || caseCards(snap, l.caseId, ['file', 'waiting', 'collect']).length > 0;
    if (busy) continue;
    if (q.verdict !== 'QUALIFIED') { holds.push({ case_id: l.caseId, card_id: l.signup.card.id, reason: `Qualify says ${q.verdict ?? 'nothing yet'} for ${l.caseId}.` }); continue; }
    if (!confirmed) { holds.push({ case_id: l.caseId, card_id: l.signup.card.id, reason: 'Waiting for the owner to confirm they are the owner of record (owner_confirmed: yes).' }); continue; }
    if (started.length >= MAX_ASSIGN) break;
    writes.push({ op: 'update', card_id: l.find.card.id, patch: { status: 'todo', assignee: 'evidence' }, why: `owner confirmed on ${l.signup.card.id}; start Evidence for ${l.caseId}` });
    started.push(l.find.card.id);
  }
  for (const e of byKind(snap, 'evidence')) if (e.card.status === 'todo' && !e.card.assignee) holds.push({ case_id: e.caseId, card_id: e.card.id, reason: 'Evidence hand-off card has nobody on it.' });
  for (const f of byKind(snap, 'find')) {
    const note = f.card.note ?? '';
    if (/^EVIDENCE ready\b/.test(note) && f.caseId && caseCards(snap, f.caseId, ['file', 'waiting', 'collect']).length === 0) holds.push({ case_id: f.caseId, card_id: f.card.id, reason: 'Evidence is ready but there is no File card.' });
  }
  return decision('evidence', snap, { writes, holds, started_by_board: started, reason: started.length ? `Assigning ${started.length} confirmed case(s) to Evidence; the board starts its sessions.` : 'No confirmed case is waiting for Evidence.' });
}

export function dueFollowUps(snap: Snapshot): Parsed[] {
  return byKind(snap, 'waiting').filter((p) => {
    if (p.card.status === 'done') return false;
    const f = followUp(p);
    if (!f || f.escalated || f.chased >= 3) return false;
    return !f.last || addDays(f.last, f.every) <= snap.today;
  });
}

export function planChase(snap: Snapshot): Decision {
  if (snap.running.chase?.length) return decision('chase', snap, { reason: 'Chase is already running.' });
  const due = dueFollowUps(snap);
  const open = byKind(snap, 'waiting').filter((p) => p.card.status !== 'done' && !p.demo);
  const last = snap.lastSession.chase;
  const stale = open.length > 0 && (!last || Date.parse(last) < Date.parse(`${snap.today}T00:00:00Z`) - 12 * 3600e3);
  if (!due.length && !stale) return decision('chase', snap, { reason: open.length ? 'No follow-up is due and Chase ran in the last 12 hours.' : 'No case is waiting on the county.' });
  return decision('chase', snap, { run: true, agent: 'chase', message: 'Run your chase pass now.', reason: due.length ? `${due.length} follow-up(s) due: ${due.map((d) => d.card.id).join(', ')}.` : `${open.length} case(s) wait on the county and Chase has not read the inbox in 12 hours.` });
}

export function newLetters(snap: Snapshot): { card: Parsed; messageId: string }[] {
  const out: { card: Parsed; messageId: string }[] = [];
  for (const p of byKind(snap, 'waiting')) {
    const results = escalateResults(p);
    for (const l of letters(p)) {
      const mine = results.filter((r) => r.messageId === l.messageId);
      const latest = mine.at(-1);
      if (!latest || (latest.status === 'PENDING' && latest.checkAgain && latest.checkAgain <= snap.today)) out.push({ card: p, messageId: l.messageId });
    }
  }
  return out;
}

export function planEscalate(snap: Snapshot): Decision {
  if (snap.running.escalate?.length) return decision('escalate', snap, { reason: 'Escalate is already running.' });
  const found = newLetters(snap);
  if (!found.length) return decision('escalate', snap, { reason: 'No new decision letter.' });
  const cards = [...new Set(found.map((f) => f.card.card.id))];
  return decision('escalate', snap, { run: true, agent: 'escalate', message: `Run your Escalate pass now. New decision letters are on ${cards.join(', ')}.`, reason: `${found.length} letter(s) without an escalate-result: ${found.map((f) => f.messageId).join(', ')}.` });
}

export function collectDue(p: Parsed, today: string): string | null {
  if (p.card.status === 'done') return null;
  const s = collectState(p);
  if (!s.status) return 'no Collect result yet';
  if (s.paid && s.status === 'PAID') return null;
  if (s.billAt && s.resultAt && s.billAt > s.resultAt) return 'a tax bill arrived after the last result';
  if (s.paymentRequest && !s.link) return 'the invoice still has no payment link';
  if (s.checkAgain && s.checkAgain <= today) return `its check-again date ${s.checkAgain} has come`;
  return null;
}

function signupFor(snap: Snapshot, caseId: string): Parsed | null {
  return links(snap).find((l) => l.caseId === caseId && !l.problem)?.signup ?? null;
}

function countyOf(snap: Snapshot, caseId: string): { county: string | null; parcel: string | null; address: string | null } {
  const j = snap.cards.find((p) => p.caseId === caseId && p.json)?.json;
  return { county: j?.jurisdiction?.county ?? null, parcel: j?.property?.parcel_id ?? null, address: j?.property ? `${String(j.property.address).replace(/\s+/g, ' ')}, ${j.property.city}` : null };
}

export function planCollect(snap: Snapshot): Decision {
  const writes: Write[] = [];
  const holds: Hold[] = [];
  const started: string[] = [];
  const auth = authorizations(snap);
  for (const p of byKind(snap, 'collect')) {
    if (!p.caseId) continue;
    const s = collectState(p);
    if (s.code === 'P_AWAIT_BILL' && p.card.status !== 'done') {
      const existing = byKind(snap, 'billreq').find((b) => b.caseId === p.caseId);
      if (!existing) {
        const where = countyOf(snap, p.caseId);
        const authLine = auth.get(p.caseId);
        if (!authLine) holds.push({ case_id: p.caseId, card_id: p.card.id, reason: 'Corrected tax bill needed, but there is no signed authorization line to let Outreach name the parcel.' });
        else if (started.length < MAX_ASSIGN) {
          writes.push({
            op: 'create',
            key: `flow-billreq-${p.caseId}`,
            title: `${p.demo ? 'DEMO · ' : ''}County question · corrected tax bill · ${where.address ?? 'address on Collect card'} · ${p.caseId}`,
            status: 'todo',
            assignee: 'outreach',
            body: [
              `case_id: ${p.caseId}`,
              `collect_card: ${p.card.id}`,
              `office: ${where.county ?? 'the'} County Tax Collector`,
              `parcel: ${where.parcel ?? 'see the Collect card'}`,
              `address: ${where.address ?? 'see the Collect card'}`,
              'owner_authorized: yes (signed authorization on file)',
              authLine,
              'ask: the corrected tax bill issued after the Value Adjustment Board lowered this parcel\'s value, as text in the reply',
              `when answered: post the bill on the Collect card as described in your instructions (tax-bill · case ${p.caseId} · received <YYYY-MM-DD> · <messageId>).`,
            ].join('\n'),
            why: `Collect ${p.card.id} is waiting for the corrected bill`,
          });
          started.push(`flow-billreq-${p.caseId}`);
        }
      }
    }
    const om = s.ownerMessage;
    if (s.invoice && s.link && om && !s.paid) {
      const signup = signupFor(snap, p.caseId);
      if (!signup) holds.push({ case_id: p.caseId, card_id: p.card.id, reason: `Invoice ${s.invoice} has a payment link but no owner email thread is linked to ${p.caseId}.` });
      else if (!hasComment(signup, (b) => firstLine(b).startsWith(`invoice-ready · ${s.invoice} `))) {
        const to = signup.card.body.match(/^from:\s*(\S+)/im)?.[1] ?? 'the sender on this card';
        writes.push({
          op: 'comment',
          card_id: signup.card.id,
          body: [`invoice-ready · ${s.invoice} · case ${p.caseId} · collect ${p.card.id}`, `to: ${to}`, `subject: ${om.subject}`, 'text:', om.body, '', `Pay online: ${s.link.url}`].join('\n'),
          why: `deliver invoice ${s.invoice} to the owner after approval`,
        });
      }
    }
  }
  const due = byKind(snap, 'collect').map((p) => ({ p, why: collectDue(p, snap.today) })).filter((d) => d.why).slice(0, 10);
  const running = snap.running.collect?.length;
  return decision('collect', snap, {
    writes, holds, started_by_board: started,
    run: !!due.length && !running,
    agent: due.length && !running ? 'collect' : null,
    message: due.length && !running ? `Run Collect now on these cards: ${due.map((d) => d.p.card.id).join(', ')}.` : null,
    reason: running ? 'Collect is already running.' : due.length ? due.map((d) => `${d.p.card.id}: ${d.why}`).join('; ') : 'No Collect card is due.',
  });
}

export interface Claim {
  caseId: string;
  demo: boolean;
  stage: string;
  status: 'doing' | 'blocked' | 'done';
  waitingOn: string;
  cards: Record<string, string>;
  events: { at: string; text: string }[];
  address: string | null;
  authorization: boolean;
}

export function claims(snap: Snapshot): Claim[] {
  const ids = new Set<string>();
  const link = links(snap);
  for (const l of link) if (l.caseId) ids.add(l.caseId);
  for (const p of snap.cards) {
    if (!p.caseId) continue;
    if (['evidence', 'file', 'waiting', 'collect'].includes(p.kind)) ids.add(p.caseId);
    if (p.kind === 'find' && (p.card.assignee === 'evidence' || qualifyNote(p).verdict === 'EVIDENCE')) ids.add(p.caseId);
  }
  const auth = authorizations(snap);
  const out: Claim[] = [];
  for (const caseId of ids) {
    const mine = snap.cards.filter((p) => p.caseId === caseId && p.kind !== 'claim');
    const signup = link.find((l) => l.caseId === caseId)?.signup;
    const cards: Record<string, string> = {};
    for (const p of mine) cards[p.kind] = p.card.id;
    if (signup) cards.signup = signup.card.id;
    const events: { at: string; text: string }[] = [];
    const push = (at: string, text: string) => events.push({ at: at.slice(0, 10), text });
    for (const p of mine) {
      if (p.kind === 'find' && p.card.note) push(p.card.updated_at, `Find/Qualify: ${firstLine(p.card.note).slice(0, 160)}`);
      if (p.kind === 'file') push(p.card.updated_at, `File: ${firstLine(p.card.note ?? p.card.status).slice(0, 160)}`);
      if (p.kind === 'waiting') {
        push(p.card.created_at, `Waiting on the county (${p.card.id})`);
        for (const l of letters(p)) push(l.at, `Decision letter received (${l.messageId})`);
        for (const r of escalateResults(p)) push(r.at, `Escalate: ${r.status} · ${r.code}${r.checkAgain ? ` · check again ${r.checkAgain}` : ''}`);
      }
      if (p.kind === 'collect') {
        for (const c of p.comments) {
          const h = firstLine(c.body);
          if (/^(collect-result|payment-link|payment-receipt|tax-bill) · /.test(h)) push(c.created_at, h.replace(/ · https:\/\/\S+/, ' · link').slice(0, 180));
        }
      }
    }
    if (signup) {
      push(signup.card.created_at, `${/^source:\s*website/im.test(signup.card.body) ? 'Owner signed up on the website' : 'Owner wrote in'} (${signup.card.id})`);
      for (const c of signup.comments) { const h = firstLine(c.body); if (/^(invoice-ready|invoice-sent|invoice-held|briefing-ready|briefing-sent|meeting-booked) · /.test(h)) push(c.created_at, h); }
    }
    events.sort((a, b) => a.at.localeCompare(b.at));
    const collect = mine.find((p) => p.kind === 'collect');
    const waiting = mine.find((p) => p.kind === 'waiting');
    const cs = collect ? collectState(collect) : null;
    let stage = 'signed up', waitingOn = 'owner to confirm they own the home', status: Claim['status'] = 'doing';
    const findCard = mine.find((p) => p.kind === 'find');
    if (signup && lineValue(signup, 'owner_confirmed')?.match(/^yes/i)) { stage = 'confirmed'; waitingOn = 'Evidence to start'; }
    if (findCard && (findCard.card.assignee === 'evidence' || qualifyNote(findCard).verdict === 'EVIDENCE')) { stage = 'evidence'; waitingOn = 'Evidence packet'; }
    if (mine.some((p) => p.kind === 'file')) { stage = 'file'; waitingOn = 'operator approval of the filing, then File'; }
    if (waiting) {
      stage = 'awaiting county'; waitingOn = 'the county decision (Chase follows up)';
      const r = escalateResults(waiting).at(-1);
      if (newLetters(snap).some((n) => n.card === waiting)) waitingOn = 'Escalate to read the new decision letter';
      else if (r?.status === 'PENDING') waitingOn = `the county; Escalate checks again ${r.checkAgain ?? 'later'}`;
      else if (r?.status === 'ESCALATE') { stage = 'refiling'; waitingOn = 'Evidence → File for the next level'; }
      else if (r?.status === 'CLOSED') { stage = 'closed'; waitingOn = 'nothing'; status = 'done'; }
    }
    if (collect && cs) {
      stage = 'collect';
      if (cs.paid) { stage = 'paid'; waitingOn = 'nothing'; status = 'done'; }
      else if (cs.code === 'P_AWAIT_BILL') waitingOn = 'the corrected tax bill (Outreach asks the tax collector)';
      else if (cs.link) waitingOn = `the owner to pay ${cs.invoice}`;
      else if (cs.paymentRequest) waitingOn = 'a payment link for the invoice';
      else if (cs.status === 'CLOSED') { stage = 'closed'; waitingOn = 'nothing'; status = 'done'; }
      else waitingOn = `Collect (${cs.status ?? 'not run'})`;
    }
    if (status !== 'done' && !auth.has(caseId) && ['file', 'awaiting county', 'refiling', 'collect'].includes(stage)) { status = 'blocked'; waitingOn += '; signed authorization line missing'; }
    const where = countyOf(snap, caseId);
    out.push({ caseId, demo: mine.some((p) => p.demo), stage, status, waitingOn, cards, events, address: where.address, authorization: auth.has(caseId) });
  }
  return out.sort((a, b) => a.caseId.localeCompare(b.caseId));
}

export function claimTitle(c: Claim) { return `${c.demo ? 'DEMO · ' : ''}Claim · ${c.caseId}${c.address ? ` · ${c.address}` : ''}`; }

export function claimBody(c: Claim) {
  return [
    `claim · case ${c.caseId} · stage ${c.stage}`,
    `waiting_on: ${c.waitingOn}`,
    `authorization: ${c.authorization ? 'signed line on file' : 'missing'}`,
    `cards: ${Object.entries(c.cards).map(([k, v]) => `${k} ${v}`).join(' · ')}`,
    '',
    ...c.events.map((e) => `${e.at} · ${e.text}`),
    '',
    'Kept by the coordinator from the step cards; edits here are overwritten.',
  ].join('\n');
}

export function planLedger(snap: Snapshot): Decision {
  const writes: Write[] = [];
  const existing = byKind(snap, 'claim');
  for (const c of claims(snap)) {
    const card = existing.find((e) => stripDemo(e.card.title).startsWith(`Claim · ${c.caseId}`));
    const body = claimBody(c);
    if (!card) writes.push({ op: 'create', key: `flow-claim-${c.caseId}`, title: claimTitle(c), body, status: c.status, assignee: null, ...(c.status === 'done' ? { note: `${c.stage} · ${c.caseId}` } : {}), why: `start tracking ${c.caseId}` });
    else if (card.card.body !== body || card.card.status !== c.status) writes.push({ op: 'update', card_id: card.card.id, patch: { body, status: c.status, ...(c.status === 'done' ? { note: `${c.stage} · ${c.caseId}` } : {}) }, why: `${c.caseId} is at ${c.stage}` });
  }
  const holds: Hold[] = snap.awaitingApproval.map((a) => ({ case_id: null, card_id: a.session, reason: `${a.agent} has waited for your approval since ${a.since}.` }));
  return decision('ledger', snap, { writes, holds, reason: `${claims(snap).length} claims tracked, ${writes.length} claim cards to write.` });
}

export function plan(step: Step, snap: Snapshot): Decision {
  switch (step) {
    case 'qualify': return planQualify(snap);
    case 'link': return planLink(snap);
    case 'evidence': return planEvidence(snap);
    case 'chase': return planChase(snap);
    case 'escalate': return planEscalate(snap);
    case 'collect': return planCollect(snap);
    case 'ledger': return planLedger(snap);
    case 'intake': return planIntake(snap);
    case 'briefing': return planBriefing(snap);
  }
}

export function signupTitle(row: WebsiteSignup) {
  const where = [row.address, row.city].filter(Boolean).join(', ');
  return `Sign up · ${where} (${row.email})`;
}

export function planIntake(snap: Snapshot): Decision {
  const writes: Write[] = [];
  const seen = new Set(byKind(snap, 'signup').map((s) => s.card.body.match(/^signup_id:\s*(\S+)/m)?.[1]).filter(Boolean));
  const emails = new Set(byKind(snap, 'signup').map((s) => s.card.body.match(/^from:\s*(\S+)/im)?.[1]?.toLowerCase()).filter(Boolean));
  const holds: Hold[] = [];
  for (const row of snap.signups ?? []) {
    if (seen.has(row.id)) continue;
    if (!row.consent) continue;
    if (emails.has(row.email.toLowerCase())) { holds.push({ case_id: row.case_id, card_id: `signup ${row.id}`, reason: `${row.email} already has a Sign up card; the website request ${row.id} needs a person to merge.` }); continue; }
    if (writes.length >= MAX_ASSIGN) break;
    const pro = /licensed tax professional/i.test(row.notes ?? '');
    const find = row.case_id ? snap.cards.find((p) => p.kind === 'find' && p.caseId === row.case_id) : null;
    writes.push({
      op: 'create',
      key: `flow-signup-${row.id}`,
      title: signupTitle(row),
      status: 'blocked',
      assignee: null,
      body: [
        'source: website',
        `signup_id: ${row.id}`,
        `from: ${row.email}`,
        `address: ${[row.address, row.city, row.zip ? `FL ${row.zip}` : null].filter(Boolean).join(', ')} (as entered on the website)`,
        `phone: ${row.phone || 'none'}`,
        `call_ok: ${row.call_ok ? 'yes' : 'no'}`,
        `pro_call: ${pro ? 'yes' : 'no'}`,
        'consent: yes (website form)',
        `date: ${row.created_at}`,
        ...(find && row.case_id ? [`case_id: ${row.case_id}`] : []),
        ...(row.notes ? [`website_notes: ${row.notes}`] : []),
      ].join('\n'),
      why: `website sign-up ${row.id}${pro ? ' asked for a professional call' : ''}`,
    });
  }
  return decision('intake', snap, { writes, holds, reason: `${writes.length} website sign-up(s) to put on the board.` });
}

export function wantsCall(p: Parsed) { return /^\s*pro_call:\s*yes\b/im.test(p.card.body) || p.comments.some((c) => /^\s*pro_call:\s*yes\b/im.test(c.body)); }

export function briefingUrls(cfg: FlowConfig | undefined, token: string) {
  const base = (cfg?.publicUrl ?? '').replace(/\/$/, '');
  return { present: `${base}/b/${token}?present=1`, view: `${base}/b/${token}`, pdf: `${base}/b/${token}.pdf` };
}

export function planBriefing(snap: Snapshot): Decision {
  const holds: Hold[] = [];
  const builds: Build[] = [];
  const decks = new Map((snap.briefings ?? []).map((b) => [b.case_id, b]));
  const ready = new Set(snap.evidenceReady ?? []);
  for (const s of byKind(snap, 'signup')) {
    if (s.card.status === 'done' || !wantsCall(s)) continue;
    if (s.comments.some((c) => /^STOP\b/.test(c.body))) continue;
    const l = links(snap).find((x) => x.signup === s);
    if (!l?.find || !l.caseId) { holds.push({ case_id: null, card_id: s.card.id, reason: `A professional call was requested, but ${l?.problem ?? 'no Find case is linked'}` }); continue; }
    const deck = decks.get(l.caseId);
    if (!deck) builds.push({ caseId: l.caseId, findCardId: l.find.card.id, signupCardId: s.card.id, version: 1 });
    else if (!deck.has_evidence && ready.has(l.caseId)) builds.push({ caseId: l.caseId, findCardId: l.find.card.id, signupCardId: s.card.id, version: deck.version + 1 });
    if (builds.length >= MAX_ASSIGN) break;
  }
  return decision('briefing', snap, { holds, builds, reason: builds.length ? `${builds.length} briefing deck(s) to build.` : 'No briefing deck to build.' });
}

export function briefingWrites(snap: Snapshot, b: Build, token: string): Write[] {
  const s = snap.cards.find((p) => p.card.id === b.signupCardId)!;
  const urls = briefingUrls(snap.config, token);
  const sent = s.comments.some((c) => firstLine(c.body).startsWith('briefing-sent · '));
  const website = /^source:\s*website/im.test(s.card.body);
  const body = [
    `case_id: ${b.caseId}`,
    `signup_card: ${s.card.id}`,
    `source: ${website ? 'website' : 'email'}`,
    `to: ${s.card.body.match(/^from:\s*(\S+)/im)?.[1] ?? 'unknown'}`,
    `reply_to_message: ${website ? 'none' : (s.card.body.match(/^message_id:\s*(\S+)/im)?.[1] ?? 'none')}`,
    `deck_version: ${b.version}`,
    `present_url: ${urls.present}`,
    `pdf_url: ${urls.pdf}`,
    `booking_url: ${snap.config?.bookingUrl ?? 'none'}`,
    `presenter_email: ${snap.config?.presenterEmail ?? 'none'}`,
    `update_only: ${sent ? 'yes' : 'no'}`,
  ].join('\n');
  const existing = byKind(snap, 'briefing').find((p) => p.caseId === b.caseId);
  const address = snap.cards.find((p) => p.card.id === b.findCardId)?.json?.property;
  const where = address ? `${String(address.address).replace(/\s+/g, ' ')}, ${address.city}` : b.caseId;
  return [
    { op: 'comment', card_id: s.card.id, body: `briefing-ready · v${b.version} · case ${b.caseId}\npresent: ${urls.present}\npdf: ${urls.pdf}`, why: `briefing deck v${b.version} for ${b.caseId}` },
    existing
      ? { op: 'update', card_id: existing.card.id, patch: { body, status: 'todo', assignee: 'briefing' }, why: `send briefing v${b.version}` }
      : { op: 'create', key: `flow-briefing-${b.caseId}`, title: `${s.demo ? 'DEMO · ' : ''}Briefing · ${where} · ${b.caseId}`, body, status: 'todo', assignee: 'briefing', why: `send briefing v${b.version}` },
  ];
}
