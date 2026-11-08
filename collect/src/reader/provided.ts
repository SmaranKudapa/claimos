/**
 * A bill reading supplied from outside, e.g. by the Naïve agent that read the bill itself.
 * The program still checks every quote and decides.
 */
import { BillReadingSchema, type BillReading } from "../types.js";
import { ReaderError, type BillReader } from "./types.js";

export class ProvidedBillReader implements BillReader {
  readonly name = "agent";
  private reading: BillReading;
  constructor(raw: unknown) {
    const p = BillReadingSchema.safeParse(raw);
    if (!p.success) throw new ReaderError(`bill reading is invalid: ${p.error.issues.slice(0, 2).map((x) => `${x.path.join(".")}: ${x.message}`).join("; ")}`);
    this.reading = p.data;
  }
  async read(): Promise<BillReading> {
    return this.reading;
  }
}
