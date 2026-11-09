import { timingSafeEqual } from 'node:crypto';
import { Naive, NaiveError, type Fetch } from './naive.js';
import { STEPS, type Step } from './engine.js';
import { runStep, type Deps } from './runtime.js';
import { restStore } from './store.js';

export interface Env {
  VETTA_MCP_TOKEN?: string; NAIVE_API_KEY?: string; NAIVE_API_URL?: string;
  DATABASE_REST_URL?: string; DATABASE_SERVICE_KEY?: string;
  NAIVE_FILES_READ_KEY?: string; FLOW_PUBLIC_URL?: string; BOOKING_URL?: string; PRESENTER_NAME?: string; PRESENTER_TITLE?: string; PRESENTER_LICENSE?: string; PRESENTER_EMAIL?: string; FEE_PCT?: string;
}

export function depsFrom(env: Env): Deps {
  let store = null;
  try { store = restStore(env); } catch {}
  const fee = Number(env.FEE_PCT);
  return {
    store,
    config: { publicUrl: env.FLOW_PUBLIC_URL || null, presenterEmail: env.PRESENTER_EMAIL || null, bookingUrl: env.BOOKING_URL || null },
    presenter: { name: env.PRESENTER_NAME || null, title: env.PRESENTER_TITLE || 'Claim OS appeal specialist', license: env.PRESENTER_LICENSE || null },
    feePct: fee > 0 && fee < 1 ? fee : 0.3,
  };
}

export const tools = [
  {
    name: 'flow_step',
    description: `One step of the Claim OS coordinator pass. Steps, in order: ${STEPS.join(', ')}. The engine reads the whole board, applies the glue writes this step needs (links, authorization copies, hand-off assignments, bill requests, invoice-ready notes, claim cards) and answers whether a step agent should run now: run, agent, message, reason, holds, applied writes and cards the board started itself. It never contacts anyone and never moves money.`,
    inputSchema: {
      type: 'object',
      additionalProperties: false,
      required: ['step'],
      properties: {
        step: { type: 'string', enum: [...STEPS] },
        dry_run: { type: 'boolean', description: 'Plan only: report the writes without making them.' },
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

export async function handle(message: any, env: Env, fetch?: Fetch, now?: Date): Promise<unknown | null> {
  const id = message?.id ?? null;
  switch (message?.method) {
    case 'notifications/initialized': return null;
    case 'initialize': {
      const asked = String(message.params?.protocolVersion ?? '');
      return reply(id, { protocolVersion: VERSIONS.includes(asked) ? asked : '2025-03-26', capabilities: { tools: {} }, serverInfo: { name: 'claimos-flow', version: '0.1.0' } });
    }
    case 'ping': return reply(id, {});
    case 'tools/list': return reply(id, { tools });
    case 'tools/call': {
      const name = String(message.params?.name ?? '');
      const args = message.params?.arguments ?? {};
      if (name !== 'flow_step') return reply(id, toolText({ error: 'unknown_tool', message: `No tool named ${name}.` }, true));
      const extra = Object.keys(args).filter((k) => k !== 'step' && k !== 'dry_run');
      if (extra.length || !STEPS.includes(args.step)) return reply(id, toolText({ error: 'invalid_arguments', message: `step must be one of ${STEPS.join(', ')}.` }, true));
      try {
        const base = env.NAIVE_API_URL || 'https://api.vetta.sh';
        const naive = new Naive(env.NAIVE_API_KEY ?? '', base, fetch);
        const deps = depsFrom(env);
        if (env.NAIVE_FILES_READ_KEY) try { deps.files = new Naive(env.NAIVE_FILES_READ_KEY, base, fetch); } catch {}
        return reply(id, toolText(await runStep(naive, args.step as Step, args.dry_run === true, now, deps)));
      } catch (e) {
        if (e instanceof NaiveError) return reply(id, toolText({ error: 'naive_refused', status: e.status, message: e.message, request_id: e.requestId }, true));
        return reply(id, toolText({ error: 'unavailable', message: 'The board could not be read.' }, true));
      }
    }
    default: return { jsonrpc: '2.0', id, error: { code: -32601, message: 'Method not found' } };
  }
}
