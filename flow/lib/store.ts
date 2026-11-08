import { randomBytes } from 'node:crypto';
import type { Deck } from './briefing.js';

export interface StoredBriefing { case_id: string; token: string; version: number; has_evidence: boolean; deck: Deck; built_at: string; }
export interface BriefingStore {
  list(): Promise<Omit<StoredBriefing, 'deck'>[]>;
  byCase(caseId: string): Promise<StoredBriefing | null>;
  byToken(token: string): Promise<StoredBriefing | null>;
  save(caseId: string, deck: Deck): Promise<StoredBriefing>;
}

export function newToken() { return randomBytes(18).toString('base64url'); }

export function restStore(env: { DATABASE_REST_URL?: string; DATABASE_SERVICE_KEY?: string }, fetcher: typeof fetch = fetch): BriefingStore {
  const base = (env.DATABASE_REST_URL ?? '').replace(/\/$/, '');
  const key = env.DATABASE_SERVICE_KEY ?? '';
  if (!base || !key) throw new Error('The briefing store is not configured (DATABASE_REST_URL, DATABASE_SERVICE_KEY).');
  const call = async (path: string, init: { method?: string; body?: unknown; prefer?: string } = {}) => {
    const r = await fetcher(`${base}/${path}`, { method: init.method ?? 'GET', headers: { apikey: key, authorization: `Bearer ${key}`, 'content-type': 'application/json', prefer: init.prefer ?? 'return=representation' }, ...(init.body === undefined ? {} : { body: JSON.stringify(init.body) }) });
    if (!r.ok) throw new Error(`briefing store ${r.status}: ${(await r.text()).slice(0, 200)}`);
    return r.status === 204 ? [] : r.json();
  };
  const one = (rows: StoredBriefing[]) => rows[0] ?? null;
  return {
    list: () => call('briefings?select=case_id,token,version,has_evidence,built_at'),
    byCase: async (caseId) => one(await call(`briefings?case_id=eq.${encodeURIComponent(caseId)}&limit=1`)),
    byToken: async (token) => /^[A-Za-z0-9_-]{20,40}$/.test(token) ? one(await call(`briefings?token=eq.${encodeURIComponent(token)}&limit=1`)) : null,
    save: async (caseId, deck) => {
      const existing = one(await call(`briefings?case_id=eq.${encodeURIComponent(caseId)}&select=token&limit=1`));
      const row = { case_id: caseId, token: existing?.token ?? newToken(), version: deck.version, has_evidence: deck.hasEvidence, deck, built_at: new Date().toISOString() };
      const out = await call('briefings?on_conflict=case_id', { method: 'POST', body: row, prefer: 'return=representation,resolution=merge-duplicates' });
      return out[0];
    },
  };
}
