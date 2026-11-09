import { renderHtml } from '../lib/briefing.js';
import { renderPdf } from '../lib/pdf.js';
import { restStore } from '../lib/store.js';

export async function GET(request: Request) {
  const url = new URL(request.url);
  const token = url.searchParams.get('t') ?? '';
  const headers = { 'cache-control': 'private, no-store', 'x-robots-tag': 'noindex' };
  let row;
  try { row = await restStore(process.env).byToken(token); } catch { return new Response('Briefing unavailable.', { status: 503, headers }); }
  if (!row) return new Response('Not found.', { status: 404, headers });
  const name = `${row.deck.address.replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '')}-Claim-OS-briefing.pdf`;
  if (url.searchParams.get('f') === 'pdf') return new Response(Buffer.from(await renderPdf(row.deck)), { headers: { ...headers, 'content-type': 'application/pdf', 'content-disposition': `inline; filename="${name}"` } });
  return new Response(renderHtml(row.deck, { present: url.searchParams.has('present'), pdfUrl: `/b/${row.token}.pdf` }), { headers: { ...headers, 'content-type': 'text/html; charset=utf-8' } });
}
