import type { BillReading, TaxBill } from "../types.js";

/** Reads numbers off a tax bill. It never decides anything. */
export interface BillReader {
  readonly name: string;
  read(bill: TaxBill): Promise<BillReading>;
}
export class ReaderError extends Error {}
