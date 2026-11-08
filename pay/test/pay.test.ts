import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handle, authorized } from '../lib/mcp.js';

type Call = { method: string; url: string; body: string; headers: Record<string, string> };

function stripe(routes: (c: Call) => { status?: number; body: unknown }) {
  const calls: Call[] = [];
  const fetch = async (url: string, init?: RequestInit) => {
    const c: Call = { method: String(init?.method), url, body: String(init?.body ?? ''), headers: init?.headers as Record<string, string> };
    calls.push(c);
    const r = routes(c);
    return new Response(JSON.stringify(r.body), { status: r.status ?? 200, headers: { 'request-id': `req_${calls.length}` } });
  };
  return { calls, fetch };
}

const env = { VETTA_MCP_TOKEN: 'tok_abc', STRIPE_SECRET_KEY: 'rk_test_123abc' };
const args = { reference: 'COS-FL-13-2026-30507035000-aea523', amount_cents: 130121, currency: 'usd', description: 'Claim OS success fee, case FL-13-2026-30507035000', case_id: 'FL-13-2026-30507035000' };
const call = (name: string, a: unknown) => ({ jsonrpc: '2.0', id: 7, method: 'tools/call', params: { name, arguments: a } });
const payload = (out: any) => JSON.parse(out.result.content[0].text);

test('bearer must match the platform token exactly', () => {
  assert.equal(authorized('Bearer tok_abc', env), true);
  assert.equal(authorized('Bearer tok_abd', env), false);
  assert.equal(authorized(null, env), false);
  assert.equal(authorized('Bearer ', {}), false);
});

test('creates a price and a single-use payment link with the invoice reference', async () => {
  const s = stripe((c) => {
    if (c.method === 'GET') return { body: { data: [], has_more: false } };
    if (c.url.endsWith('/v1/prices')) return { body: { id: 'price_1' } };
    return { body: { id: 'plink_abc123', url: 'https://buy.stripe.com/test_x', livemode: false } };
  });
  const out: any = await handle(call('create_payment_link', args), env, s.fetch);
  const r = payload(out);
  assert.equal(out.result.isError, undefined);
  assert.equal(r.payment_link_id, 'plink_abc123');
  assert.equal(r.price_id, 'price_1');
  assert.equal(r.reused, false);
  assert.equal(r.livemode, false);
  assert.deepEqual(r.stripe_request_ids, ['req_1', 'req_2', 'req_3']);
  const price = new URLSearchParams(s.calls[1]!.body);
  assert.equal(price.get('unit_amount'), '130121');
  assert.equal(price.get('currency'), 'usd');
  const link = new URLSearchParams(s.calls[2]!.body);
  assert.equal(link.get('line_items[0][price]'), 'price_1');
  assert.equal(link.get('restrictions[completed_sessions][limit]'), '1');
  assert.equal(link.get('metadata[reference]'), args.reference);
  assert.equal(s.calls[2]!.headers['idempotency-key'], `claimos-pay:${args.reference}:130121:link`);
  assert.equal(s.calls[2]!.headers.authorization, 'Bearer rk_test_123abc');
});

test('returns the existing link for the same invoice instead of a second one', async () => {
  const s = stripe(() => ({ body: { data: [{ id: 'plink_old111', url: 'https://buy.stripe.com/o', livemode: false, metadata: { reference: args.reference, amount_cents: '130121', price_id: 'price_0' } }], has_more: false } }));
  const r = payload(await handle(call('create_payment_link', args), env, s.fetch));
  assert.equal(r.reused, true);
  assert.equal(r.payment_link_id, 'plink_old111');
  assert.equal(s.calls.length, 1);
});

test('refuses a different amount for an invoice that already has a link', async () => {
  const s = stripe(() => ({ body: { data: [{ id: 'plink_old111', metadata: { reference: args.reference, amount_cents: '99' } }], has_more: false } }));
  const out: any = await handle(call('create_payment_link', args), env, s.fetch);
  assert.equal(out.result.isError, true);
  assert.equal(payload(out).code, 'reference_amount_mismatch');
});

test('rejects malformed arguments before calling Stripe', async () => {
  const s = stripe(() => ({ body: {} }));
  for (const bad of [{ ...args, amount_cents: 12.5 }, { ...args, currency: 'eur' }, { ...args, reference: 'x' }, { ...args, extra: 1 }]) {
    const out: any = await handle(call('create_payment_link', bad), env, s.fetch);
    assert.equal(out.result.isError, true);
    assert.equal(payload(out).error, 'invalid_arguments');
  }
  assert.equal(s.calls.length, 0);
});

test('reports a Stripe refusal with its request id and never the key', async () => {
  const s = stripe(() => ({ status: 403, body: { error: { type: 'invalid_request_error', code: 'secret_key_required', message: 'The provided key does not have the required permissions.' } } }));
  const out: any = await handle(call('create_payment_link', args), env, s.fetch);
  const text = out.result.content[0].text;
  assert.equal(out.result.isError, true);
  assert.equal(payload(out).stripe_request_id, 'req_1');
  assert.doesNotMatch(text, /rk_test_123abc/);
});

test('missing key is reported as not configured', async () => {
  const out: any = await handle(call('create_payment_link', args), { VETTA_MCP_TOKEN: 't' });
  assert.equal(payload(out).code, 'not_configured');
});

test('payment status reads paid checkout sessions for the link', async () => {
  const s = stripe((c) => c.url.includes('/v1/payment_links/')
    ? { body: { id: 'plink_abc123', livemode: false, metadata: { reference: args.reference } } }
    : { body: { data: [{ id: 'cs_test_1', payment_status: 'paid', payment_intent: 'pi_1', created: 1795000000, amount_total: 130121, currency: 'usd' }] } });
  const r = payload(await handle(call('payment_status', { reference: args.reference, payment_link_id: 'plink_abc123' }), env, s.fetch));
  assert.equal(r.paid, true);
  assert.equal(r.payment_ref, 'pi_1');
  assert.equal(r.checkout_session_id, 'cs_test_1');
  assert.equal(r.paid_on, '2026-11-18');
  assert.match(s.calls[1]!.url, /payment_link=plink_abc123/);
  assert.match(s.calls[1]!.url, /status=complete/);
});

test('payment status refuses a link that belongs to another invoice', async () => {
  const s = stripe(() => ({ body: { id: 'plink_abc123', metadata: { reference: 'COS-OTHER-1' } } }));
  const out: any = await handle(call('payment_status', { reference: args.reference, payment_link_id: 'plink_abc123' }), env, s.fetch);
  assert.equal(payload(out).code, 'reference_mismatch');
});

test('lists exactly the two tools', async () => {
  const out: any = await handle({ jsonrpc: '2.0', id: 1, method: 'tools/list' }, env);
  assert.deepEqual(out.result.tools.map((t: any) => t.name), ['create_payment_link', 'payment_status']);
});
