import { db, fail } from '../lib/lookup.js';
import { sign } from '../lib/token.js';

// No commas, parentheses or wildcards: the address goes straight into PostgREST filters.
const EMAIL = /^[^\s@,()*]+@[^\s@,()*]+\.[^\s@,()*]+$/;

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const email = String(body.email ?? '').trim().toLowerCase().slice(0, 200);
  if (!EMAIL.test(email)) return Response.json({ error: 'Enter the email you signed up with.' }, { status: 400 });
  try {
    const enc = encodeURIComponent(email);
    const [s, c] = await Promise.all([db(`signups?select=id&email=ilike.${enc}&limit=1`), db(`cases?select=case_id&owner_email=ilike.${enc}&limit=1`)]);
    // Unknown emails get the same answer and no mail, so the form cannot be used to email strangers.
    if (s.length || c.length) {
      if (!process.env.AGENTMAIL_API_KEY) throw new Error('AGENTMAIL_API_KEY is not set on the app (naive app secrets)');
      const link = `${new URL(req.url).origin}/track?t=${sign(email)}`;
      const text = `Here is the link to your Claim OS case page:\n\n${link}\n\nIt works for 24 hours. If you did not ask for it, you can ignore this email.\n\nClaim OS is a private company and is not affiliated with any government agency, county property appraiser or value adjustment board. Nothing here is a promise of a lower bill; the county decides.\n\nClaim OS\nclaimos@agentmail.to`;
      const r = await fetch('https://api.agentmail.to/v0/inboxes/claimos@agentmail.to/messages/send', {
        method: 'POST',
        headers: { authorization: `Bearer ${process.env.AGENTMAIL_API_KEY}`, 'content-type': 'application/json' },
        body: JSON.stringify({ to: [email], subject: 'Your Claim OS case page', text }),
      });
      if (!r.ok) throw new Error(`agentmail ${r.status}: ${(await r.text()).slice(0, 300)}`);
    }
    return Response.json({ ok: true }); // shortcut: no rate limit on sends, add one if the form gets abused
  } catch (e) { return fail(e); }
}
