import { PDFDocument, StandardFonts, rgb, type PDFFont, type PDFPage } from 'pdf-lib';
import { presenterLine, type Deck, type Slide } from './briefing.js';

const W = 960, H = 540, M = 56;
const INK = rgb(0.08, 0.13, 0.24), MUTED = rgb(0.36, 0.42, 0.5), ACCENT = rgb(0.12, 0.44, 0.92), LINE = rgb(0.85, 0.88, 0.92), HL = rgb(0.85, 0.28, 0.06);

const SWAP: Record<string, string> = { '→': '->', '←': '<-', '≈': '~', '≥': '>=', '≤': '<=', ' ': ' ', ' ': ' ' };

export function safe(font: PDFFont, s: string) {
  let out = '';
  for (const ch of s.replace(/[→←≈≥≤  ]/g, (c) => SWAP[c]!)) {
    try { font.encodeText(ch); out += ch; } catch { out += '?'; }
  }
  return out;
}

function wrap(font: PDFFont, text: string, size: number, width: number): string[] {
  const words = safe(font, text).split(/\s+/);
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (font.widthOfTextAtSize(next, size) > width && cur) { lines.push(cur); cur = w; } else cur = next;
  }
  if (cur) lines.push(cur);
  return lines;
}

function fit(font: PDFFont, text: string, size: number, width: number) {
  let t = safe(font, text);
  while (t.length > 1 && font.widthOfTextAtSize(t, size) > width) t = t.slice(0, -2) + '…';
  return t;
}

function drawSlide(page: PDFPage, s: Slide, n: number, total: number, f: { reg: PDFFont; bold: PDFFont }) {
  let y = H - M;
  page.drawText(safe(f.bold, s.kicker), { x: M, y: y - 12, size: 12, font: f.bold, color: ACCENT });
  y -= 30;
  for (const l of wrap(f.bold, s.title, 26, W - 2 * M).slice(0, 3)) { y -= 30; page.drawText(l, { x: M, y, size: 26, font: f.bold, color: INK }); }
  y -= 12;
  if (s.lead) for (const l of wrap(f.reg, s.lead, 15, W - 2 * M).slice(0, 3)) { y -= 20; page.drawText(l, { x: M, y, size: 15, font: f.reg, color: MUTED }); }
  y -= 10;
  if (s.table) {
    const cols = s.table.head.length;
    const colW = (W - 2 * M) / cols;
    const row = (cells: string[], font: PDFFont, color = INK) => {
      y -= 22;
      cells.forEach((c, k) => page.drawText(fit(font, c, 12, colW - 10), { x: M + k * colW, y, size: 12, font, color }));
      page.drawLine({ start: { x: M, y: y - 6 }, end: { x: W - M, y: y - 6 }, thickness: 0.5, color: LINE });
    };
    row(s.table.head, f.bold, MUTED);
    for (const r of s.table.rows.slice(0, 8)) row(r, f.reg);
    y -= 8;
  }
  if (s.bars) {
    const max = Math.max(...s.bars.items.map((b) => b.value));
    const labelW = 230, valueW = 120, trackW = W - 2 * M - labelW - valueW - 20;
    for (const b of s.bars.items.slice(0, 6)) {
      y -= 30;
      const font = b.highlight ? f.bold : f.reg;
      page.drawText(fit(font, b.label, 12, labelW - 10), { x: M, y: y + 4, size: 12, font, color: INK });
      page.drawRectangle({ x: M + labelW, y, width: trackW, height: 16, color: LINE });
      page.drawRectangle({ x: M + labelW, y, width: Math.max(3, (b.value / max) * trackW), height: 16, color: b.highlight ? HL : MUTED });
      page.drawText(safe(font, `$${Math.round(b.value)} ${s.bars.unit}`), { x: M + labelW + trackW + 10, y: y + 4, size: 12, font, color: INK });
    }
    y -= 10;
  }
  for (const b of s.bullets) {
    const lines = wrap(f.reg, b, 14, W - 2 * M - 18);
    if (y - lines.length * 19 < M + 10) break;
    y -= 19;
    page.drawCircle({ x: M + 4, y: y + 4, size: 2.5, color: ACCENT });
    lines.forEach((l, k) => { if (k) y -= 19; page.drawText(l, { x: M + 18, y, size: 14, font: f.reg, color: INK }); });
    y -= 6;
  }
  page.drawText(`${n} / ${total}`, { x: W - M - 30, y: 24, size: 10, font: f.reg, color: MUTED });
  page.drawText('Claim OS is a private company and is not affiliated with any government agency.', { x: M, y: 24, size: 9, font: f.reg, color: MUTED });
}

export async function renderPdf(d: Deck): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  doc.setTitle(`${d.address} - Claim OS briefing`);
  doc.setAuthor('Claim OS');
  doc.setSubject(`Property value review prepared by ${presenterLine(d.presenter)}`);
  doc.setCreationDate(new Date(`${d.builtOn}T12:00:00Z`));
  doc.setModificationDate(new Date(`${d.builtOn}T12:00:00Z`));
  const f = { reg: await doc.embedFont(StandardFonts.Helvetica), bold: await doc.embedFont(StandardFonts.HelveticaBold) };
  d.slides.forEach((s, k) => drawSlide(doc.addPage([W, H]), s, k + 1, d.slides.length, f));
  return doc.save();
}
