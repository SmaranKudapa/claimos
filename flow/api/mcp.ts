import { authorized, handle } from '../lib/mcp.js';

export async function POST(request: Request) {
  if (!authorized(request.headers.get('authorization'), process.env)) return Response.json({ error: 'MCP authentication is required.' }, { status: 401 });
  let message: unknown;
  try { message = await request.json(); } catch { return Response.json({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } }, { status: 400 }); }
  const out = await handle(message, process.env);
  return out === null ? new Response(null, { status: 202 }) : Response.json(out);
}

export async function GET() { return new Response(null, { status: 405, headers: { allow: 'POST' } }); }
