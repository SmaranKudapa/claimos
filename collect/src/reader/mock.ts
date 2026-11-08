/** Offline bill reader: pattern rules, good enough for the sample bills. Every number quotes its match. */
import type { BillReading, TaxBill } from "../types.js";
import type { BillReader } from "./types.js";

const MONEY = String.raw`\$\s?([\d,]+(?:\.\d{2})?)`;
const num = (s: string) => Number(s.replace(/,/g, ""));

export class MockBillReader implements BillReader {
  readonly name = "mock";
  async read(bill: TaxBill): Promise<BillReading> {
    const t = bill.text;
    const r: BillReading = { confidence: 0.3, evidence: [] };
    const take = (field: string, re: RegExp) => {
      const m = t.match(re);
      if (m) r.evidence.push({ field, quote: m[0] });
      return m;
    };
    const av = take("assessedValue", new RegExp(String.raw`(?:corrected |revised )?(?:assessed|taxable|just) value[:\s]+${MONEY}`, "i"));
    if (av) r.assessedValue = num(av[1]!);
    const ot = take("originalTax", new RegExp(String.raw`(?:original|previous) (?:tax|amount)[^$\n]*${MONEY}`, "i"));
    if (ot) r.originalTax = num(ot[1]!);
    const ct = take("correctedTax", new RegExp(String.raw`(?:corrected|revised|new) (?:tax|amount)[^$\n]*${MONEY}`, "i"));
    if (ct) r.correctedTax = num(ct[1]!);
    const bd = take("billDate", /(?:bill|notice) date[:\s]+(\d{4}-\d{2}-\d{2})/i);
    if (bd) r.billDate = bd[1]!;
    if (av || (ot && ct)) r.confidence = 0.9;
    return r;
  }
}
