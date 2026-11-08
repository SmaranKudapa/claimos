import { db, findCandidate, fail } from '../lib/lookup';

const str = (v: unknown) => (typeof v === 'string' ? v.trim().slice(0, 200) : '');

export async function POST(req: Request) {
  let b: Record<string, unknown>;
  try { b = await req.json(); } catch { return Response.json({ errors: { form: 'Send JSON.' } }, { status: 400 }); }

  const address = str(b.address), city = str(b.city), zip = str(b.zip), email = str(b.email), phone = str(b.phone), unit = str(b.unit);
  const errors: Record<string, string> = {};
  if (!address) errors.address = 'Enter your street address.';
  if (!/^\d{5}$/.test(zip)) errors.zip = 'Enter a 5-digit ZIP.';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'Enter an email we can reply to.';
  if (b.consent !== true) errors.consent = 'We need your agreement before we can review the records.';
  if (Object.keys(errors).length) return Response.json({ errors }, { status: 400 });

  try {
    const found = await findCandidate(address, zip, unit);
    const match = Array.isArray(found) ? null : found;
    const verdict = match ? 'found' : 'not_found';
    const notes = [
      unit && `Unit ${unit}`,
      Array.isArray(found) && 'Several units share this address; unit not given',
      b.pro_call === true && 'Requested a call with a licensed tax professional',
    ].filter(Boolean).join('; ') || null;
    const [row] = await db('signups', { method: 'POST', body: JSON.stringify({
      address, city: city || null, zip, email, phone: phone || null, call_ok: Boolean(phone) && b.call_ok === true,
      consent: true, case_id: match?.case_id ?? null, verdict, notes,
    }) });
    return Response.json({ id: row.id, verdict }, { status: 201 });
  } catch (e) { return fail(e); }
}
