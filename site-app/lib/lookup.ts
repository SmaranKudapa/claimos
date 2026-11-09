// The app's managed database speaks PostgREST; the platform hands the app its URL and service key.
const REST = (process.env.DATABASE_REST_URL as string).replace(/\/$/, '');
const KEY = process.env.DATABASE_SERVICE_KEY as string;

export type Candidate = {
  case_id: string; address: string; unit: string | null; city: string | null; zip: string; addr_key: string; tier: string;
  just_value: string | number; defensible_value: string | number; annual_savings: string | number; run_id: string | null;
};

export async function db(path: string, init: { method?: string; body?: string; prefer?: string } = {}) {
  const r = await fetch(`${REST}/${path}`, {
    method: init.method, body: init.body,
    headers: { apikey: KEY, authorization: `Bearer ${KEY}`, 'content-type': 'application/json', prefer: init.prefer ?? 'return=representation' },
  });
  if (!r.ok) throw new Error(`db ${r.status}: ${(await r.text()).slice(0, 300)}`);
  return r.json();
}

// Exact row count from the Content-Range header: a plain read returns at most 1,000 rows, whatever `limit` says.
export async function count(path: string) {
  const r = await fetch(`${REST}/${path}`, { method: 'HEAD', headers: { apikey: KEY, authorization: `Bearer ${KEY}`, prefer: 'count=exact' } });
  const total = r.headers.get('content-range')?.split('/')[1] ?? '';
  if (!r.ok || !/^\d+$/.test(total)) throw new Error(`db count ${r.status}: ${path}`);
  return Number(total);
}

// One JSON error shape for both handlers instead of a bare platform 500.
export function fail(e: unknown) {
  console.error(e);
  return Response.json({ error: 'database_error', detail: String(e) }, { status: 500 });
}

// Same normalisation as candidates.addr_key: upper(collapse spaces(trim(address))) || '|' || zip
export function addrKey(address: string, zip: string) {
  return address.trim().replace(/\s+/g, ' ').toUpperCase() + '|' + zip.trim();
}

const unitKey = (u: string | null | undefined) => (u ?? '').replace(/^\s*(#|unit|apt)\s*/i, '').trim().toUpperCase();

// zip + house number narrow the rows; exact addr_key wins, else the first street token must appear.
// Condo buildings share one addr_key with a row per unit: without a unit that pick returns the whole list.
export async function findCandidate(address: string, zip: string, unit = ''): Promise<Candidate | Candidate[] | null> {
  const key = addrKey(address, zip);
  const [house, street] = key.split('|')[0].split(' ');
  if (!/^\d{5}$/.test(zip.trim()) || !/^\d+$/.test(house) || !street) return null;
  const q = [
    'select=case_id,address,unit,city,zip,addr_key,tier,just_value,defensible_value,annual_savings,run_id',
    `zip=eq.${zip.trim()}`,
    `addr_key=like.${encodeURIComponent(house + ' *')}`,
    'order=imported_at.desc',
  ].join('&');
  const rows = (await db(`candidates?${q}`)) as Candidate[];
  const exact = rows.filter((r) => r.addr_key === key);
  const hits = exact.length ? exact : rows.filter((r) => r.addr_key.split('|')[0].split(' ').includes(street));
  if (unitKey(unit)) return hits.find((r) => unitKey(r.unit) === unitKey(unit)) ?? (hits.length === 1 ? hits[0] : null);
  if (hits.length > 1 && new Set(hits.map((r) => r.addr_key)).size === 1) return hits;
  return hits[0] ?? null;
}
