import { createHmac, timingSafeEqual } from 'node:crypto';

// Magic-link token for /track: base64url(email).expiry_ms.base64url(hmac). The key is derived from the
// database service key so no second secret has to exist; rotating that key invalidates every link.
const key = () => createHmac('sha256', process.env.DATABASE_SERVICE_KEY as string).update('claimos-track-link').digest();
const mac = (body: string) => createHmac('sha256', key()).update(body).digest();
const b64 = (s: string | Buffer) => Buffer.from(s).toString('base64url');

export function sign(email: string, ttlMs = 24 * 3600e3) {
  const body = `${b64(email)}.${Date.now() + ttlMs}`;
  return `${body}.${b64(mac(body))}`;
}

export function verify(token: string): string | null {
  const [e, exp, sig] = token.split('.');
  if (!e || !exp || !sig) return null;
  const want = mac(`${e}.${exp}`), got = Buffer.from(sig, 'base64url');
  if (got.length !== want.length || !timingSafeEqual(got, want) || Number(exp) < Date.now()) return null;
  return Buffer.from(e, 'base64url').toString();
}
