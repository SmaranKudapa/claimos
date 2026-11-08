/**
 * Reason codes. The prefix decides the status (precedence I_ > D_ > C_ > V_ > P_); F_ codes are
 * flags. No code or status routes a case to a person.
 */
import type { Status } from "./types.js";

export const CODES = {
  // INCOMPLETE
  I_SCHEMA: "Case or bill does not match the expected shape (or the case is not a win)",
  I_BILL_MISMATCH: "The bill is for a different case",
  // PAID
  D_PAID: "The invoice is paid",
  // CLOSED
  C_NO_PROOF: "No corrected bill arrived within the wait limit; closed without a fee",
  C_NO_REDUCTION_ON_BILL: "The corrected bill shows no reduction; no fee",
  C_NO_SAVINGS: "No tax savings; no fee",
  C_FEE_BELOW_MIN: "The fee would be below the minimum; not invoiced",
  C_WRITTEN_OFF: "The invoice stayed unpaid past the write-off date",
  C_UNHANDLED: "A situation the rules do not cover; closed without charging",
  // INVOICED
  V_INVOICE_ISSUED: "Invoice issued for the agreed share of the first year's savings",
  V_REMINDER: "A payment reminder is due",
  // WAITING
  P_AWAIT_BILL: "Waiting for the corrected tax bill",
  P_AWAIT_PAYMENT: "Invoice sent; waiting for payment",
  // Flags
  F_SAVINGS_FROM_BILL: "Savings are the tax difference shown on the bill",
  F_SAVINGS_ESTIMATED: "The bill shows no tax amounts; savings = value cut × tax rate",
  F_VALUE_DIFFERS: "The bill's value differs from the value the county granted; the bill is used",
  F_FEE_CAPPED: "The fee was capped at the desk maximum",
  F_BILL_UNREADABLE: "The bill could not be read with enough confidence; waiting for a clearer one",
  F_DEFAULT_AUTHORIZATION: "Sign up has not recorded the owner's fee terms; the desk default was used",
} as const;
export type Code = keyof typeof CODES;

const PRECEDENCE: [string, Status][] = [
  ["I_", "INCOMPLETE"],
  ["D_", "PAID"],
  ["C_", "CLOSED"],
  ["V_", "INVOICED"],
  ["P_", "WAITING"],
];

export function statusFor(codes: string[]): Status | null {
  for (const [prefix, status] of PRECEDENCE) if (codes.some((c) => c.startsWith(prefix))) return status;
  return null;
}
