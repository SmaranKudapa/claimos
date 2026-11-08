import { Naive, type SessionRow } from './naive.js';
import { parse, type Parsed } from './parse.js';
import { plan, type Decision, type Snapshot, type Step, type Write } from './engine.js';

export const BOARD = 'brd_3kb4zft8yttkhm04sv6vn8ydw2';
const WITH_COMMENTS = new Set(['signup', 'evidence', 'file', 'waiting', 'collect', 'billreq']);
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

export async function snapshot(naive: Naive, board = BOARD, now = new Date(), warnings: string[] = []): Promise<Snapshot> {
  const soft = <T>(what: string, p: Promise<T[]>) => p.catch((e) => { warnings.push(`${what}: ${e instanceof Error ? e.message : 'failed'}`); return [] as T[]; });
  const [cards, files, agents, approvals] = await Promise.all([
    naive.cards(board),
    soft('files', naive.files()),
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

export interface StepResult extends Omit<Decision, 'writes'> { applied: Applied[]; warnings: string[]; }

export async function runStep(naive: Naive, step: Step, dryRun = false, now = new Date()): Promise<StepResult> {
  const warnings: string[] = [];
  const snap = await snapshot(naive, BOARD, now, warnings);
  const d = plan(step, snap);
  const applied = dryRun ? d.writes.map((w) => ({ op: w.op, card_id: w.op === 'create' ? null : w.card_id, why: w.why, ok: true })) : await apply(naive, d.writes);
  const { writes, ...rest } = d;
  return { ...rest, applied, warnings: [...new Set(warnings)] };
}
