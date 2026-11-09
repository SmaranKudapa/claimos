import { findCandidate, fail } from '../lib/lookup.js';

const headers = { 'cache-control': 'no-store' };

export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  const row = await findCandidate(q.get('address') ?? '', q.get('zip') ?? '', q.get('unit') ?? '').catch(fail);
  if (row instanceof Response) return row;
  if (!row) return Response.json({ found: false }, { headers });
  if (Array.isArray(row)) {
    // several units share this address: the page asks which one (units may be null in the county roll)
    const units = row.map((r) => r.unit).filter((u): u is string => Boolean(u)).sort((a, b) => a.localeCompare(b, 'en', { numeric: true }));
    return Response.json({ found: false, several: true, address: row[0].address.trim().replace(/\s+/g, ' '), units }, { headers });
  }
  // run_id looks like FL-20261107T232805Z; its date is the Find run the numbers come from
  const d = row.run_id?.match(/(\d{4})(\d{2})(\d{2})T/);
  return Response.json({
    found: true,
    case_id: row.case_id,
    address: row.address.trim().replace(/\s+/g, ' '),
    unit: row.unit,
    city: row.city,
    zip: row.zip,
    tier: row.tier,
    just_value: Number(row.just_value),
    defensible_value: Number(row.defensible_value),
    annual_savings: Number(row.annual_savings),
    run_date: d ? `${d[1]}-${d[2]}-${d[3]}` : null,
  }, { headers });
}
