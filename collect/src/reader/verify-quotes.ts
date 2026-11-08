/**
 * Quote check (same rule as escalate/src/reader/verify-quotes.ts): every number read from the bill
 * must quote it. A field whose quote is not in the bill (ignoring case and whitespace) is dropped.
 */
import type { BillReading } from "../types.js";

const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();

export function quoteInText(quote: string, text: string): boolean {
  const q = norm(quote);
  return q.length > 0 && norm(text).includes(q);
}

const FIELDS = ["assessedValue", "originalTax", "correctedTax", "billDate"] as const;

export function verifyBillQuotes(r: BillReading, text: string): { reading: BillReading; dropped: string[] } {
  const ok = new Set(r.evidence.filter((e) => quoteInText(e.quote, text)).map((e) => e.field));
  const out: BillReading = { confidence: r.confidence, evidence: r.evidence.filter((e) => ok.has(e.field)) };
  const dropped: string[] = [];
  for (const f of FIELDS) {
    if (r[f] === undefined) continue;
    if (ok.has(f)) (out as Record<string, unknown>)[f] = r[f];
    else dropped.push(f);
  }
  return { reading: out, dropped };
}
