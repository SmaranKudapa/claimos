import { db, count, fail } from '../lib/lookup.js';

// Homes screened per county come from Find's run summaries; the candidates table only holds flagged homes.
// shortcut: constants keyed by county, replace with a runs table once Find publishes one.
const SCREENED: Record<string, number> = { Hendry: 8998, Bay: 86114 };

type Row = { county: string | null; run_id: string | null; annual_savings: string | number | null };

// Proof-strip and live-counter numbers for the home page. One read returns at most 1,000 rows, so the
// strong cases are paged and the plain totals come from count headers.
export async function GET() {
  try {
    const strong: Row[] = [];
    for (let offset = 0; ; offset += 1000) {
      const page = (await db(`candidates?select=county,run_id,annual_savings&tier=eq.strong&order=case_id&offset=${offset}`)) as Row[];
      strong.push(...page);
      if (page.length < 1000) break;
    }
    const counties = [...new Set(strong.map((r) => r.county).filter((c): c is string => Boolean(c)))];
    const run = strong.map((r) => r.run_id ?? '').sort().at(-1)?.match(/(\d{4})(\d{2})(\d{2})T/);
    return Response.json({
      counties: counties.length,
      screened: counties.reduce((n, c) => n + (SCREENED[c] ?? 0), 0),
      candidates: await count('candidates?select=case_id'),
      strong: strong.length,
      savings: Math.round(strong.reduce((n, r) => n + Number(r.annual_savings ?? 0), 0)),
      signups: await count('signups?select=id'),
      run_date: run ? `${run[1]}-${run[2]}-${run[3]}` : null,
    }, { headers: { 'cache-control': 'public, max-age=300' } });
  } catch (e) { return fail(e); }
}
