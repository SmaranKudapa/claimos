export type Fetch = (input: string, init?: RequestInit) => Promise<Response>;

export interface StripeConfig { key: string; fetch?: Fetch; base?: string; }

export interface LinkRequest { reference: string; amountCents: number; currency: string; description: string; caseId: string; }

export interface LinkReceipt {
  object: 'payment_link_receipt';
  reference: string;
  case_id: string;
  payment_link_id: string;
  url: string;
  price_id: string;
  amount_cents: number;
  currency: string;
  livemode: boolean;
  reused: boolean;
  stripe_request_ids: string[];
}

export interface PaymentReceipt {
  object: 'payment_status_receipt';
  reference: string;
  payment_link_id: string;
  paid: boolean;
  paid_on: string | null;
  payment_ref: string | null;
  checkout_session_id: string | null;
  amount_paid_cents: number | null;
  currency: string | null;
  livemode: boolean;
  stripe_request_ids: string[];
}

export class StripeError extends Error {
  constructor(message: string, readonly status: number, readonly code: string | null, readonly requestId: string | null) { super(message); }
}

export class InputError extends Error {}

const REFERENCE = /^COS-[A-Za-z0-9][A-Za-z0-9-]{2,90}$/;
const CASE_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{2,90}$/;
const LINK_ID = /^plink_[A-Za-z0-9]{6,64}$/;

export function linkRequest(raw: unknown): LinkRequest {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new InputError('Arguments must be an object.');
  const a = raw as Record<string, unknown>;
  const allowed = new Set(['reference', 'amount_cents', 'currency', 'description', 'case_id']);
  const extra = Object.keys(a).filter((k) => !allowed.has(k));
  if (extra.length) throw new InputError(`Unknown arguments: ${extra.join(', ')}.`);
  const reference = String(a.reference ?? '');
  if (!REFERENCE.test(reference)) throw new InputError('reference must be the Collect invoice number, e.g. COS-FL-13-2026-30507035000-aea523.');
  const caseId = String(a.case_id ?? '');
  if (!CASE_ID.test(caseId)) throw new InputError('case_id must be the original Find case ID.');
  const amountCents = a.amount_cents;
  if (typeof amountCents !== 'number' || !Number.isInteger(amountCents) || amountCents < 50 || amountCents > 5_000_000) throw new InputError('amount_cents must be a whole number of cents from 50 to 5000000.');
  const currency = String(a.currency ?? '').toLowerCase();
  if (currency !== 'usd') throw new InputError('currency must be usd.');
  const description = String(a.description ?? '').trim();
  if (description.length < 5 || description.length > 500) throw new InputError('description must be 5 to 500 characters.');
  return { reference, amountCents, currency, description, caseId };
}

export function statusRequest(raw: unknown): { reference: string; paymentLinkId: string } {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new InputError('Arguments must be an object.');
  const a = raw as Record<string, unknown>;
  const extra = Object.keys(a).filter((k) => k !== 'reference' && k !== 'payment_link_id');
  if (extra.length) throw new InputError(`Unknown arguments: ${extra.join(', ')}.`);
  const reference = String(a.reference ?? '');
  if (!REFERENCE.test(reference)) throw new InputError('reference must be the Collect invoice number.');
  const paymentLinkId = String(a.payment_link_id ?? '');
  if (!LINK_ID.test(paymentLinkId)) throw new InputError('payment_link_id must be a Stripe payment link id (plink_...).');
  return { reference, paymentLinkId };
}

type Json = Record<string, any>;

class Client {
  readonly ids: string[] = [];
  private readonly fetch: Fetch;
  private readonly base: string;
  constructor(private readonly config: StripeConfig) {
    if (!/^(sk|rk)_(test|live)_[A-Za-z0-9]+$/.test(config.key)) throw new StripeError('STRIPE_SECRET_KEY is not set to a Stripe secret or restricted key.', 500, 'not_configured', null);
    this.fetch = config.fetch ?? ((input, init) => globalThis.fetch(input, init));
    this.base = config.base ?? 'https://api.stripe.com';
  }
  async call(method: 'GET' | 'POST', path: string, params: Record<string, string | number> = {}, idempotencyKey?: string): Promise<Json> {
    const body = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
    const url = method === 'GET' && body.size ? `${this.base}${path}?${body}` : `${this.base}${path}`;
    const headers: Record<string, string> = { authorization: `Bearer ${this.config.key}`, 'stripe-version': '2024-06-20' };
    if (method === 'POST') headers['content-type'] = 'application/x-www-form-urlencoded';
    if (idempotencyKey) headers['idempotency-key'] = idempotencyKey;
    const response = await this.fetch(url, { method, headers, ...(method === 'POST' ? { body: body.toString() } : {}) });
    const requestId = response.headers.get('request-id');
    if (requestId) this.ids.push(requestId);
    const data = (await response.json().catch(() => ({}))) as Json;
    if (!response.ok) {
      const e = (data.error ?? {}) as Json;
      throw new StripeError(String(e.message ?? `Stripe answered ${response.status}.`), response.status, e.code ? String(e.code) : e.type ? String(e.type) : null, requestId);
    }
    return data;
  }
}

async function findLink(client: Client, reference: string): Promise<Json | null> {
  let after: string | undefined;
  for (let page = 0; page < 5; page++) {
    const params: Record<string, string | number> = { limit: 100 };
    if (after) params.starting_after = after;
    const list = await client.call('GET', '/v1/payment_links', params);
    const data = (list.data ?? []) as Json[];
    const hit = data.find((l) => l.metadata?.reference === reference);
    if (hit) return hit;
    if (!list.has_more || !data.length) return null;
    after = String(data[data.length - 1]!.id);
  }
  return null;
}

export async function createPaymentLink(config: StripeConfig, req: LinkRequest): Promise<LinkReceipt> {
  const client = new Client(config);
  const existing = await findLink(client, req.reference);
  if (existing) {
    const amount = Number(existing.metadata?.amount_cents);
    if (amount !== req.amountCents) throw new StripeError(`A payment link for ${req.reference} already exists for ${amount} cents, not ${req.amountCents}. Leave it for a person.`, 409, 'reference_amount_mismatch', null);
    return { object: 'payment_link_receipt', reference: req.reference, case_id: req.caseId, payment_link_id: String(existing.id), url: String(existing.url), price_id: String(existing.metadata?.price_id ?? ''), amount_cents: amount, currency: req.currency, livemode: Boolean(existing.livemode), reused: true, stripe_request_ids: client.ids };
  }
  const key = `claimos-pay:${req.reference}:${req.amountCents}`;
  const price = await client.call('POST', '/v1/prices', {
    currency: req.currency,
    unit_amount: req.amountCents,
    'product_data[name]': `Claim OS invoice ${req.reference}`,
    'metadata[reference]': req.reference,
    'metadata[case_id]': req.caseId,
  }, `${key}:price`);
  const link = await client.call('POST', '/v1/payment_links', {
    'line_items[0][price]': String(price.id),
    'line_items[0][quantity]': 1,
    'restrictions[completed_sessions][limit]': 1,
    'payment_intent_data[description]': req.description,
    'payment_intent_data[metadata][reference]': req.reference,
    'payment_intent_data[metadata][case_id]': req.caseId,
    'metadata[reference]': req.reference,
    'metadata[case_id]': req.caseId,
    'metadata[amount_cents]': req.amountCents,
    'metadata[price_id]': String(price.id),
  }, `${key}:link`);
  return { object: 'payment_link_receipt', reference: req.reference, case_id: req.caseId, payment_link_id: String(link.id), url: String(link.url), price_id: String(price.id), amount_cents: req.amountCents, currency: req.currency, livemode: Boolean(link.livemode), reused: false, stripe_request_ids: client.ids };
}

export async function paymentStatus(config: StripeConfig, req: { reference: string; paymentLinkId: string }): Promise<PaymentReceipt> {
  const client = new Client(config);
  const link = await client.call('GET', `/v1/payment_links/${req.paymentLinkId}`);
  if (link.metadata?.reference !== req.reference) throw new StripeError(`Payment link ${req.paymentLinkId} does not belong to ${req.reference}.`, 409, 'reference_mismatch', null);
  const sessions = await client.call('GET', '/v1/checkout/sessions', { payment_link: req.paymentLinkId, status: 'complete', limit: 10 });
  const paid = ((sessions.data ?? []) as Json[]).find((s) => s.payment_status === 'paid');
  return {
    object: 'payment_status_receipt',
    reference: req.reference,
    payment_link_id: req.paymentLinkId,
    paid: Boolean(paid),
    paid_on: paid ? new Date(Number(paid.created) * 1000).toISOString().slice(0, 10) : null,
    payment_ref: paid ? String(paid.payment_intent ?? paid.id) : null,
    checkout_session_id: paid ? String(paid.id) : null,
    amount_paid_cents: paid ? Number(paid.amount_total) : null,
    currency: paid ? String(paid.currency) : null,
    livemode: Boolean(link.livemode),
    stripe_request_ids: client.ids,
  };
}
