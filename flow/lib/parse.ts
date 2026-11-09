import type { Card, Comment } from './naive.js';

export type Kind = 'claim' | 'signup' | 'evidence' | 'file' | 'waiting' | 'collect' | 'billreq' | 'briefing' | 'find' | 'other';

export interface Parsed {
  card: Card;
  comments: Comment[];
  kind: Kind;
  demo: boolean;
  caseId: string | null;
  json: any | null;
}

const CASE = /^FL-\d{2}-\d{4}-\S.*$/;

export function stripDemo(title: string) { return title.replace(/^DEMO · /, ''); }

export function caseBlock(body: string): any | null {
  const blocks = [...body.matchAll(/```json\s*\n([\s\S]*?)\n```/g)];
  for (const b of blocks.reverse()) {
    try { const j = JSON.parse(b[1]!); if (j && typeof j === 'object' && typeof j.case_id === 'string') return j; } catch {}
  }
  return null;
}

export function kindOf(card: Card, json: any | null): Kind {
  const t = stripDemo(card.title);
  if (t.startsWith('Claim · ')) return 'claim';
  if (t.startsWith('Sign up · ')) return 'signup';
  if (t.startsWith('Evidence · ')) return 'evidence';
  if (t.startsWith('File · ')) return 'file';
  if (t.startsWith('Waiting on')) return 'waiting';
  if (t.startsWith('Collect · ')) return 'collect';
  if (t.startsWith('County question · corrected tax bill · ')) return 'billreq';
  if (t.startsWith('Briefing · ')) return 'briefing';
  if (json && (json.schema_version === 1 || json.schema_version === 2) && json.property) return 'find';
  return 'other';
}

export function caseIdOf(card: Card, json: any | null): string | null {
  if (json?.case_id) return String(json.case_id);
  const line = card.body.match(/^case_id:\s*(FL-\d{2}-\d{4}-[^\n]+?)\s*$/im)
    ?? card.body.match(/collect-handoff · case (\S+)/)
    ?? card.body.match(/\bCase:\s*(FL-\d{2}-\d{4}-[^\s.]+(?: [^\s.]+)*?)\.\s/);
  if (line) return line[1]!.trim();
  const last = stripDemo(card.title).split(' · ').at(-1)?.trim() ?? '';
  return CASE.test(last) ? last : null;
}

export function parse(card: Card, comments: Comment[] = []): Parsed {
  const json = caseBlock(card.body);
  const kind = kindOf(card, json);
  return { card, comments, kind, demo: card.title.startsWith('DEMO · '), caseId: kind === 'signup' || kind === 'claim' || kind === 'other' ? caseIdOf(card, null) : caseIdOf(card, json), json };
}

export function firstLine(s: string) { return s.split('\n')[0] ?? ''; }

export function lines(p: Parsed): { text: string; at: string; author: string }[] {
  return [
    ...p.card.body.split('\n').map((text) => ({ text, at: p.card.created_at, author: 'body' })),
    ...p.comments.flatMap((c) => c.body.split('\n').map((text) => ({ text, at: c.created_at, author: c.author }))),
  ];
}

export function lineValue(p: Parsed, key: string): string | null {
  const re = new RegExp(`^\\s*${key}:\\s*(.+)$`, 'i');
  let hit: string | null = null;
  for (const l of lines(p)) { const m = l.text.match(re); if (m) hit = m[1]!.trim(); }
  return hit;
}

export const SUFFIX: Record<string, string> = {
  AVENUE: 'AVE', AV: 'AVE', STREET: 'ST', DRIVE: 'DR', COURT: 'CT', PLACE: 'PL', BOULEVARD: 'BLVD', ROAD: 'RD', LANE: 'LN',
  TERRACE: 'TER', CIRCLE: 'CIR', PARKWAY: 'PKWY', HIGHWAY: 'HWY', TRAIL: 'TRL', NORTH: 'N', SOUTH: 'S', EAST: 'E', WEST: 'W',
};

const SUFFIXES = new Set(['AVE', 'ST', 'DR', 'CT', 'PL', 'BLVD', 'RD', 'LN', 'TER', 'CIR', 'PKWY', 'HWY', 'TRL', 'WAY', 'LOOP', 'RUN', 'PATH', 'ROW', 'XING', 'PT', 'CV', 'SQ']);

export function streetKey(street: string): string {
  const words = street.toUpperCase().replace(/#/g, ' UNIT ').replace(/[^A-Z0-9 ]/g, ' ').split(/\s+/).filter(Boolean).map((w) => SUFFIX[w] ?? w);
  const at = words.findIndex((w, i) => i > 0 && SUFFIXES.has(w));
  const marker = words.findIndex((w) => /^(UNIT|APT|STE|SUITE)$/.test(w));
  const end = at >= 0 ? at + 1 : marker >= 0 ? marker : words.length;
  const base = words.slice(0, end).join(' ');
  const unit = words.slice(end).filter((w) => !/^(UNIT|APT|STE|SUITE)$/.test(w)).join('');
  return unit ? `${base}|${unit}` : base;
}

export function sameStreet(a: string, b: string): boolean {
  const [ab, au] = a.split('|');
  const [bb, bu] = b.split('|');
  return ab === bb && (!au || !bu || au === bu);
}

export function cityKey(city: string) { return city.toUpperCase().replace(/[^A-Z ]/g, ' ').split(/\s+/).filter(Boolean).join(' '); }

export function signupAddress(p: Parsed): { street: string; city: string } | null {
  const raw = p.card.body.match(/^address:\s*(.+)$/im)?.[1]?.replace(/\s*\(.*$/, '').trim();
  if (!raw || /^not given/i.test(raw)) return null;
  const parts = raw.split(',').map((s) => s.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  return { street: streetKey(parts[0]!), city: cityKey(parts[1]!) };
}

export function findAddress(p: Parsed): { street: string; city: string } | null {
  const a = p.json?.property;
  if (!a?.address || !a?.city) return null;
  return { street: streetKey(String(a.address)), city: cityKey(String(a.city)) };
}

export interface Letter { messageId: string; at: string; }
export interface EscalateResult { status: string; code: string; messageId: string; checkAgain: string | null; at: string; }

export function letters(p: Parsed): Letter[] {
  return p.comments.filter((c) => firstLine(c.body).startsWith('decision-letter · ')).map((c) => ({ messageId: firstLine(c.body).split(' · ').at(-1)!.trim(), at: c.created_at }));
}

export function escalateResults(p: Parsed): EscalateResult[] {
  return p.comments.filter((c) => firstLine(c.body).startsWith('escalate-result · ')).map((c) => {
    const f = firstLine(c.body).split(' · ');
    return { status: f[1] ?? '', code: f[2] ?? '', messageId: (f.at(-1) ?? '').trim(), checkAgain: c.body.match(/check again (\d{4}-\d{2}-\d{2})/)?.[1] ?? null, at: c.created_at };
  });
}

export interface CollectState {
  status: string | null;
  code: string | null;
  invoice: string | null;
  checkAgain: string | null;
  resultAt: string | null;
  paymentRequest: boolean;
  ownerMessage: { channel: string; subject: string; body: string } | null;
  invoiceState: any | null;
  link: { url: string; id: string; at: string } | null;
  linkUnavailable: boolean;
  billAt: string | null;
  paid: { on: string; ref: string } | null;
}

export function collectState(p: Parsed): CollectState {
  const s: CollectState = { status: null, code: null, invoice: null, checkAgain: null, resultAt: null, paymentRequest: false, ownerMessage: null, invoiceState: null, link: null, linkUnavailable: false, billAt: null, paid: null };
  for (const c of p.comments) {
    const head = firstLine(c.body);
    if (head.startsWith('collect-result · ')) {
      const f = head.split(' · ');
      s.status = f[1] ?? null; s.code = f[2] ?? null; s.invoice = f[3] ?? null; s.resultAt = c.created_at;
      s.checkAgain = c.body.match(/check again (\d{4}-\d{2}-\d{2})/)?.[1] ?? null;
      s.paymentRequest = /^payment-request: /m.test(c.body);
      const om = c.body.match(/^owner-message \(([^,)]+)[^)]*\):\s*([^:\n]+):\s*(.+)$/m);
      s.ownerMessage = om ? { channel: om[1]!, subject: om[2]!.trim(), body: om[3]!.trim() } : null;
      const inv = c.body.match(/^invoice-state: (.+)$/m);
      if (inv) { try { s.invoiceState = JSON.parse(inv[1]!); } catch {} }
    } else if (head.startsWith('payment-link · ')) {
      const f = head.split(' · ');
      if (f[2] === 'unavailable') { s.linkUnavailable = true; s.link = null; }
      else if (f[2] && /^https:\/\//.test(f[2])) { s.link = { url: f[2], id: (f[3] ?? '').trim(), at: c.created_at }; s.linkUnavailable = false; }
    } else if (head.startsWith('tax-bill · ')) {
      s.billAt = c.created_at;
    } else if (head.startsWith('payment-receipt · ')) {
      const m = head.match(/paid (\d{4}-\d{2}-\d{2}) · (\S+)/);
      if (m) s.paid = { on: m[1]!, ref: m[2]! };
    }
  }
  if (s.invoiceState?.paid) s.paid = { on: s.invoiceState.paid.on, ref: s.invoiceState.paid.ref };
  return s;
}

export interface FollowUp { every: number; last: string | null; chased: number; reopened: boolean; escalated: boolean; }

export function followUp(p: Parsed): FollowUp | null {
  const m = p.card.body.match(/^follow_up:.*every (\d+) days?, last chased (\S+)/im);
  if (!m) return null;
  const results = escalateResults(p);
  const lastResult = results.at(-1);
  const reopened = !!lastResult && /^(PENDING|INCOMPLETE)$/.test(lastResult.status);
  const since = reopened ? lastResult!.at : '';
  const chasedDates = p.comments.filter((c) => /^chased: \d{4}-\d{2}-\d{2}/.test(c.body) && c.created_at > since).map((c) => c.body.match(/^chased: (\d{4}-\d{2}-\d{2})/)![1]!);
  const escalated = p.comments.some((c) => c.body.trim() === 'escalate' && c.created_at > since);
  const bodyLast = /^\d{4}-\d{2}-\d{2}$/.test(m[2]!) ? m[2]! : null;
  return { every: Number(m[1]), last: chasedDates.at(-1) ?? (reopened ? null : bodyLast), chased: chasedDates.length, reopened, escalated };
}

export function addDays(day: string, n: number) {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
