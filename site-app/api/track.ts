import {getWorkflow} from '../lib/workflow.js';
import {mergeProgress} from '../lib/workflow-model.js';
import { db, fail } from '../lib/lookup.js';
import { verify } from '../lib/token.js';

const headers = { 'cache-control': 'no-store' };
type Signup = { email: string; address: string; city: string | null; zip: string | null; created_at: string; case_id: string | null };
type Case = { case_id: string; owner_email: string | null } & Record<string, unknown>;

// The owner's cases: those carrying their email, plus those their sign-ups point at.
export async function GET(req: Request) {
  const email = verify(new URL(req.url).searchParams.get('t') ?? '');
  if (!email) return Response.json({ error: 'expired' }, { status: 401, headers });
  try {
    const enc = encodeURIComponent(email);
    // ilike makes the match case-insensitive; the filter below removes what its "_" wildcard lets through
    const signups = ((await db(`signups?select=email,address,city,zip,created_at,case_id&email=ilike.${enc}&order=created_at.desc`)) as Signup[])
      .filter((s) => s.email.toLowerCase() === email);
    const ids = signups.map((s) => s.case_id).filter((id): id is string => Boolean(id));
    const or = [`owner_email.ilike.${enc}`, ids.length && `case_id.in.(${ids.map(encodeURIComponent).join(',')})`].filter(Boolean).join(',');
    const cases = ((await db(`cases?select=case_id,address,county,owner_email,stage,status,county_value,requested_value,annual_savings,filing_deadline,needs_from_owner,history,updated_at&or=(${or})&order=updated_at.desc`)) as Case[])
      .filter((c) => ids.includes(c.case_id) || (c.owner_email ?? '').toLowerCase() === email)
      .map(({ owner_email, ...c }) => c);
    let workflow = null;
    try { workflow = await getWorkflow(); } catch {}
    const progressCases = cases.map(c => mergeProgress(c, workflow?.snapshot.cases[c.case_id]));
    return Response.json({ email, signups: signups.map(({ email, ...s }) => s), cases: progressCases, workflow_sync: workflow ? {observed_at: workflow.snapshot.observed_at, stale: workflow.stale, automatic_refresh:Boolean(process.env.CLAIMOS_WORKFLOW_READ_KEY)} : {stale:true, unavailable:true} }, { headers });
  } catch (e) { return fail(e); }
}
