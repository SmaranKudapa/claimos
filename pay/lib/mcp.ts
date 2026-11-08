import { timingSafeEqual } from 'node:crypto';
import { createPaymentLink, InputError, linkRequest, paymentStatus, statusRequest, StripeError, type Fetch } from './stripe.js';

export interface Env { VETTA_MCP_TOKEN?: string; STRIPE_SECRET_KEY?: string; }

export const tools = [
  {
    name: 'create_payment_link',
    description: 'Create one Stripe payment link for a Collect invoice, on the Claim OS Stripe account. Idempotent on reference: asking again for the same invoice returns the same link. Only for an invoice the Collect program printed in paymentRequest. Returns the Stripe receipt (payment_link_id, url, price_id, livemode, Stripe request ids).',
    inputSchema: {
      type: 'object',
      additionalProperties: false,
      required: ['reference', 'amount_cents', 'currency', 'description', 'case_id'],
      properties: {
        reference: { type: 'string', description: 'The Collect invoice number (paymentRequest.reference), e.g. COS-FL-13-2026-30507035000-aea523.' },
        amount_cents: { type: 'integer', minimum: 50, maximum: 5000000, description: 'paymentRequest.amountCents, exactly.' },
        currency: { type: 'string', enum: ['usd'] },
        description: { type: 'string', minLength: 5, maxLength: 500, description: 'paymentRequest.description, exactly.' },
        case_id: { type: 'string', description: 'The original Find case ID on the Collect card.' },
      },
    },
  },
  {
    name: 'payment_status',
    description: 'Check whether a Collect payment link was paid. Reads completed Stripe Checkout sessions for that link. Returns paid, paid_on (YYYY-MM-DD), payment_ref (the Stripe PaymentIntent id), the checkout session id, the amount paid and the Stripe request ids. Never changes anything.',
    inputSchema: {
      type: 'object',
      additionalProperties: false,
      required: ['reference', 'payment_link_id'],
      properties: {
        reference: { type: 'string', description: 'The Collect invoice number.' },
        payment_link_id: { type: 'string', description: 'The plink_ id from the card\'s payment-link comment.' },
      },
    },
  },
];

const VERSIONS = ['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25'];

export function authorized(header: string | null, env: Env): boolean {
  const expected = Buffer.from(env.VETTA_MCP_TOKEN ?? '');
  const supplied = Buffer.from((header ?? '').replace(/^Bearer /, ''));
  return expected.length > 0 && expected.length === supplied.length && timingSafeEqual(expected, supplied);
}

function reply(id: unknown, result: unknown) { return { jsonrpc: '2.0', id, result }; }
function toolText(value: unknown, isError = false) { return { ...(isError ? { isError: true } : {}), content: [{ type: 'text', text: JSON.stringify(value) }] }; }

export async function handle(message: any, env: Env, fetch?: Fetch): Promise<unknown | null> {
  const id = message?.id ?? null;
  switch (message?.method) {
    case 'notifications/initialized': return null;
    case 'initialize': {
      const asked = String(message.params?.protocolVersion ?? '');
      return reply(id, { protocolVersion: VERSIONS.includes(asked) ? asked : '2025-03-26', capabilities: { tools: {} }, serverInfo: { name: 'claimos-pay', version: '0.1.0' } });
    }
    case 'ping': return reply(id, {});
    case 'tools/list': return reply(id, { tools });
    case 'tools/call': {
      const name = String(message.params?.name ?? '');
      const args = message.params?.arguments ?? {};
      const config = { key: env.STRIPE_SECRET_KEY ?? '', ...(fetch ? { fetch } : {}) };
      try {
        if (name === 'create_payment_link') return reply(id, toolText(await createPaymentLink(config, linkRequest(args))));
        if (name === 'payment_status') return reply(id, toolText(await paymentStatus(config, statusRequest(args))));
        return reply(id, toolText({ error: 'unknown_tool', message: `No tool named ${name}.` }, true));
      } catch (e) {
        if (e instanceof InputError) return reply(id, toolText({ error: 'invalid_arguments', message: e.message }, true));
        if (e instanceof StripeError) return reply(id, toolText({ error: 'stripe_refused', status: e.status, code: e.code, message: e.message, stripe_request_id: e.requestId }, true));
        return reply(id, toolText({ error: 'unavailable', message: 'Stripe could not be reached.' }, true));
      }
    }
    default: return { jsonrpc: '2.0', id, error: { code: -32601, message: 'Method not found' } };
  }
}
