export type Fetch = (input: string, init?: RequestInit) => Promise<Response>;

export interface Card {
  id: string;
  title: string;
  body: string;
  note: string | null;
  status: 'todo' | 'doing' | 'blocked' | 'done' | string;
  assignee: string | null;
  created_at: string;
  updated_at: string;
}

export interface Comment { id: string; card_id: string; author: string; body: string; created_at: string; }
export interface FileRow { id: string; name: string; title?: string | null; created_at: string; }
export interface SessionRow { id: string; agent_id: string; status: string; stop_reason: string | null; created_at: string; }
export interface AgentRow { id: string; name: string; }

export class NaiveError extends Error {
  constructor(message: string, readonly status: number, readonly requestId: string | null) { super(message); }
}

export class Naive {
  private readonly fetch: Fetch;
  constructor(private readonly key: string, private readonly base = 'https://api.vetta.sh', fetch?: Fetch) {
    if (!/^sk_(live|test)_[A-Za-z0-9]+$/.test(key)) throw new NaiveError('NAIVE_API_KEY is not set to a Naive API key.', 500, null);
    this.fetch = fetch ?? ((input, init) => globalThis.fetch(input, init));
  }

  async call<T>(method: 'GET' | 'POST' | 'PATCH', path: string, body?: unknown, query?: Record<string, string | number | undefined>): Promise<T> {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined) q.set(k, String(v));
    const url = `${this.base}${path}${q.size ? `?${q}` : ''}`;
    for (let attempt = 0; ; attempt++) {
      const response = await this.fetch(url, {
        method,
        headers: { authorization: `Bearer ${this.key}`, ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      const text = await response.text();
      let data: any = {};
      try { data = text ? JSON.parse(text) : {}; } catch { data = {}; }
      if (response.ok) return data as T;
      const code = String(data?.error?.code ?? data?.error?.type ?? '');
      if ((response.status === 429 || response.status === 503 || code === 'rate_limited') && attempt < 4) {
        await new Promise((r) => setTimeout(r, 400 * 2 ** attempt));
        continue;
      }
      throw new NaiveError(String(data?.error?.message ?? `Naive answered ${response.status}.`), response.status, data?.error?.request_id ?? null);
    }
  }

  async pages<T>(path: string, query: Record<string, string | number | undefined> = {}, max = 20): Promise<T[]> {
    const out: T[] = [];
    let after: string | undefined;
    for (let i = 0; i < max; i++) {
      const page = await this.call<{ data: T[]; has_more?: boolean; next_cursor?: string | null }>('GET', path, undefined, { ...query, limit: 100, after });
      out.push(...page.data);
      if (!page.has_more || !page.next_cursor) break;
      after = page.next_cursor;
    }
    return out;
  }

  cards(board: string) { return this.pages<Card>(`/v1/boards/${board}/cards`); }
  async download(id: string): Promise<string> {
    const r = await this.fetch(`${this.base}/v1/files/${id}?download=true`, { headers: { authorization: `Bearer ${this.key}` } });
    if (!r.ok) throw new NaiveError(`file ${id}: Naive answered ${r.status}.`, r.status, null);
    return r.text();
  }
  appRows<T>(app: string, table: string, query: string) { return this.call<T[]>('GET', `/v1/apps/${app}/db/rest/${table}?${query}`); }
  comments(board: string, card: string) { return this.pages<Comment>(`/v1/boards/${board}/cards/${card}/comments`, {}, 5); }
  files() { return this.pages<FileRow>('/v1/files', {}, 3); }
  agents() { return this.pages<AgentRow>('/v1/agents', {}, 2); }
  sessions(query: Record<string, string>) { return this.pages<SessionRow>('/v1/sessions', query, 1); }
  createCard(board: string, body: { title: string; body: string; status: string; assignee?: string | null; key?: string }) { return this.call<Card>('POST', `/v1/boards/${board}/cards`, body); }
  updateCard(board: string, card: string, body: Partial<Pick<Card, 'title' | 'body' | 'status' | 'assignee' | 'note'>>) { return this.call<Card>('PATCH', `/v1/boards/${board}/cards/${card}`, body); }
  comment(board: string, card: string, body: string) { return this.call<Comment>('POST', `/v1/boards/${board}/cards/${card}/comments`, { body }); }
}
