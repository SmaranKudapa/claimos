/**
 * A bill reading supplied from outside, e.g. by the Naïve agent that read the bill itself.
 * The program still checks every quote and decides.
 */
import { BillReadingSchema, type BillReading } from "../types.js";
import { ReaderError, type BillReader } from "./types.js";

export class ProvidedBillReader implements BillReader {
  readonly name = "agent";
  readonly reading: BillReading;
  constructor(raw: unknown) {
    const p = BillReadingSchema.safeParse(raw);
    if (!p.success) throw new ReaderError(`bill reading is invalid: ${p.error.issues.slice(0, 2).map((x) => `${x.path.join(".")}: ${x.message}`).join("; ")}`);
    this.reading = p.data;
  }
  async read(): Promise<BillReading> {
    return this.reading;
  }
}

/** Readings supplied per bill, keyed by the bill's docId. A bill with no reading is refused, never guessed. */
export class ReadingsByBill implements BillReader {
  readonly name = "agent";
  private readings = new Map<string, BillReading>();
  constructor(raw: Record<string, unknown>) {
    for (const [docId, r] of Object.entries(raw)) this.readings.set(docId, new ProvidedBillReader(r).reading);
  }
  async read(bill: { docId: string }): Promise<BillReading> {
    const r = this.readings.get(bill.docId);
    if (!r) throw new ReaderError(`no reading was given for bill ${bill.docId}`);
    return r;
  }
}
