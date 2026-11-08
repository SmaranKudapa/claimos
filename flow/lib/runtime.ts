import { Naive, type SessionRow } from './naive.js';
import { parse, type Parsed } from './parse.js';
import { briefingWrites, plan, type Decision, type FlowConfig, type Snapshot, type Step, type WebsiteSignup, type Write } from './engine.js';
import { buildDeck, type Presenter } from './briefing.js';
import { briefingInput } from './inputs.js';
import type { BriefingStore } from './store.js';

export const BOARD = 'brd_3kb4zft8yttkhm04sv6vn8ydw2';
const WITH_COMMENTS = new Set(['signup', 'evidence', 'file', 'waiting', 'collect', 'billreq', 'briefing']);
export const SITE_APP = 'app_nkhc92xe21cyzfd5qakpkcj4g4';
const TRACKED = ['qualify', 'chase', 'escalate', 'collect', 'evidence', 'outreach', 'signup', 'File'];

export function todayIn(zone = 'America/New_York', now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
}

async function limited<T, R>(items: T[], n: number, fn: (t: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => { while (i < items.length) { const k = i++; out[k] = await fn(items[k]!); } }));
  return out;
}

export interface Deps { store: BriefingStore | null; config: FlowConfig; presenter: Presenter; feePct: number; files?: Naive; }

export async function snapshot(naive: Naive, board = BOARD, now = new Date(), warnings: string[] = [], deps: Deps | null = null): Promise<Snapshot> {
  const soft = <T>(what: string, p: Promise<T[]>) => p.catch((e) => { warnings.push(`${what}: ${e instanceof Error ? e.message : 'failed'}`); return [] as T[]; });
  const [cards, files, agents, approvals] = await Promise.all([
    naive.cards(board),
    soft('files', (deps?.files ?? naive).files()),
    soft('agents', naive.agents()),
    soft('approvals', naive.sessions({ status: 'idle', stop_reason: 'awaiting_approval' })),
  ]);
  const first = cards.map((c) => parse(c));
  const parsed: Parsed[] = await limited(first, 6, async (p) => WITH_COMMENTS.has(p.kind) ? parse(p.card, await naive.comments(board, p.card.id)) : p);
  const nameOf = new Map(agents.map((a) => [a.id, a.name]));
  const running: Record<string, SessionRow[]> = {};
  const lastSession: Record<string, string | null> = {};
  await limited(TRACKED, 4, async (name) => {
    const agent = agents.find((a) => a.name === name);
    if (!agent) { running[name.toLowerCase()] = []; lastSession[name.toLowerCase()] = null; return; }
    const recent = await naive.call<{ data: SessionRow[] }>('GET', '/v1/sessions', undefined, { agent_id: agent.id, limit: 5 }).then((r) => r.data).catch((e) => { warnings.push(`sessions of ${name}: ${e instanceof Error ? e.message : 'failed'}`); return [] as SessionRow[]; });
    running[name.toLowerCase()] = recent.filter((s) => s.status === 'running' || s.status === 'queued');
    lastSession[name.toLowerCase()] = recent[0]?.created_at ?? null;
  });
  return {
    today: todayIn('America/New_York', now),
    cards: parsed,
    files,
    running,
    lastSession,
    signups: await naive.appRows<WebsiteSignup>(SITE_APP, 'signups', 'select=id,created_at,address,city,zip,email,phone,call_ok,consent,case_id,notes&order=created_at.asc&limit=500').catch((e) => { warnings.push(`website sign-ups: ${e instanceof Error ? e.message : 'failed'}`); return []; }),
    briefings: deps?.store ? await deps.store.list().catch((e) => { warnings.push(`briefing store: ${e instanceof Error ? e.message : 'failed'}`); return []; }) : [],
    evidenceReady: [...new Set(files.filter((f) => f.name === 'packet.json' && (f.title ?? '').startsWith('Evidence ')).map((f) => packetCase(f.title!)))],
    config: deps?.config ?? { publicUrl: null, presenterEmail: null, bookingUrl: null },
    awaitingApproval: approvals.filter((s) => s.stop_reason === 'awaiting_approval').map((s) => ({ agent: nameOf.get(s.agent_id) ?? s.agent_id, session: s.id, since: s.created_at })),
  };
}

export interface Applied { op: string; card_id: string | null; why: string; ok: boolean; error?: string; }

export async function apply(naive: Naive, writes: Write[], board = BOARD): Promise<Applied[]> {
  const out: Applied[] = [];
  for (const w of writes) {
    try {
      if (w.op === 'comment') { await naive.comment(board, w.card_id, w.body); out.push({ op: 'comment', card_id: w.card_id, why: w.why, ok: true }); }
      else if (w.op === 'update') { await naive.updateCard(board, w.card_id, w.patch); out.push({ op: 'update', card_id: w.card_id, why: w.why, ok: true }); }
      else {
        const c = await naive.createCard(board, { title: w.title, body: w.body, status: w.status === 'done' ? 'doing' : w.status, assignee: w.assignee, key: w.key });
        if (w.status === 'done') await naive.updateCard(board, c.id, { status: 'done', note: w.note ?? 'done' });
        out.push({ op: 'create', card_id: c.id, why: w.why, ok: true });
      }
    } catch (e) {
      out.push({ op: w.op, card_id: w.op === 'create' ? null : w.card_id, why: w.why, ok: false, error: e instanceof Error ? e.message.slice(0, 200) : 'failed' });
    }
  }
  return out;
}

export function packetCase(title: string) {
  const rest = title.slice('Evidence '.length);
  return (rest.includes('/') ? rest.slice(0, rest.indexOf('/')) : rest.replace(/ packet\.json$/, '')).trim();
}

export async function fullRecord(naive: Naive, snap: Snapshot, caseId: string, runId: string | null): Promise<any | null> {
  if (!runId) return null;
  const file = snap.files.filter((f) => f.name === 'candidates.jsonl' && f.title === `Find run ${runId}`).sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  if (!file) return null;
  const text = await naive.download(file.id);
  for (const line of text.split('\n')) { if (line.includes(caseId)) { try { const j = JSON.parse(line); if (j.case_id === caseId) return j; } catch {} } }
  return null;
}

export async function packetFor(naive: Naive, snap: Snapshot, caseId: string): Promise<any | null> {
  const file = snap.files.filter((f) => f.name === 'packet.json' && (f.title ?? '').startsWith('Evidence ') && packetCase(f.title!) === caseId).sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  if (!file) return null;
  try { return JSON.parse(await naive.download(file.id)); } catch { return null; }
}

export interface StepResult extends Omit<Decision, 'writes' | 'builds'> { applied: Applied[]; warnings: string[]; built: { case_id: string; version: number; has_evidence: boolean; ok: boolean; error?: string }[]; }

export async function runStep(naive: Naive, step: Step, dryRun = false, now = new Date(), deps: Deps | null = null): Promise<StepResult> {
  const warnings: string[] = [];
  const snap = await snapshot(naive, BOARD, now, warnings, deps);
  const d = plan(step, snap);
  const built: StepResult['built'] = [];
  let writes = d.writes;
  if (step === 'briefing' && d.builds?.length) {
    if (!deps?.store || !deps.config.publicUrl) warnings.push('briefing decks need the store and FLOW_PUBLIC_URL');
    else for (const b of d.builds) {
      try {
        const find = snap.cards.find((p) => p.card.id === b.findCardId)!;
        const runId = find.json?.full_record?.run_id ?? find.json?.source?.run_id ?? null;
        const [full, packet] = await Promise.all([
          fullRecord(deps.files ?? naive, snap, b.caseId, runId).catch((e) => { warnings.push(`Find record for ${b.caseId}: ${e instanceof Error ? e.message : 'failed'}`); return null; }),
          packetFor(deps.files ?? naive, snap, b.caseId).catch(() => null),
        ]);
        const deck = buildDeck(briefingInput(find, full, packet, deps.feePct), { version: b.version, today: snap.today, presenter: deps.presenter, bookingUrl: deps.config.bookingUrl });
        if (dryRun) { built.push({ case_id: b.caseId, version: b.version, has_evidence: deck.hasEvidence, ok: true }); continue; }
        const row = await deps.store.save(b.caseId, deck);
        built.push({ case_id: b.caseId, version: b.version, has_evidence: deck.hasEvidence, ok: true });
        writes = [...writes, ...briefingWrites(snap, b, row.token)];
      } catch (e) {
        built.push({ case_id: b.caseId, version: b.version, has_evidence: false, ok: false, error: e instanceof Error ? e.message.slice(0, 200) : 'failed' });
      }
    }
  }
  const applied = dryRun ? writes.map((w) => ({ op: w.op, card_id: w.op === 'create' ? null : w.card_id, why: w.why, ok: true })) : await apply(naive, writes);
  const { writes: _w, builds: _b, ...rest } = d;
  return { ...rest, applied, built, warnings: [...new Set(warnings)] };
}
