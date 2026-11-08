/**
 * Synthetic won cases and corrected bills, one per Collect path. Every name, parcel and bill is
 * made up. `reading` is what the Collect agent states it read off the bill, quote by quote. `expect` is
 * what the placeholder config decides on 2026-12-15 with that reading.
 */
export const SAMPLE_TODAY = "2026-12-15";

type Json = Record<string, unknown>;
export interface Sample {
  n: number;
  title: string;
  case: Json;
  bill: Json | null;
  reading: Json | null;
  expect: { status: string; code: string; flags?: string[]; fee?: number };
}

const pad = (n: number) => String(n).padStart(4, "0");
const id = (n: number) => `case_placeholder_PH-${pad(1000 + n)}`;

function makeCase(n: number, over: Json = {}): Json {
  return {
    caseId: id(n),
    parcelId: `PH-${pad(1000 + n)}`,
    jurisdictionId: "placeholder",
    address: `${200 + n} Placeholder Lane, Sampletown`,
    owner: { names: [`Sample Owner ${n}`], type: "individual", contactChannel: "email" },
    oldAssessedValue: 500_000,
    wonAssessedValue: 420_000,
    taxRate: 0.02,
    feePct: 0.3,
    authorizationSource: "signed",
    wonOn: "2026-10-28",
    wonCode: "W_FULL_WIN",
    decisionId: `D-${pad(1000 + n)}`,
    ...over,
  };
}

function bill(n: number, lines: string[], over: Json = {}): Json {
  return {
    docId: `BILL-${pad(1000 + n)}`,
    caseId: id(n),
    receivedOn: "2026-12-05",
    text: ["Placeholder County Tax Collector", "Corrected Tax Bill (synthetic sample)", `Parcel: PH-${pad(1000 + n)}`, ...lines].join("\n"),
    ...over,
  };
}

const fact = (field: string, value: number | string, quote: string) => ({ field, value, quote });
function reading(confidence: number, facts: { field: string; value: number | string; quote: string }[]): Json {
  return { ...Object.fromEntries(facts.map((f) => [f.field, f.value])), confidence, evidence: facts.map(({ field, quote }) => ({ field, quote })) };
}
const value = (v: number) => fact("assessedValue", v, `Corrected assessed value: $${v.toLocaleString("en-US")}`);
const billDate = fact("billDate", "2026-12-01", "Bill date: 2026-12-01");
const taxes = (before: number, after: number) => [
  fact("originalTax", before, `Original tax amount: $${before.toLocaleString("en-US", { minimumFractionDigits: 2 })}`),
  fact("correctedTax", after, `Corrected tax amount: $${after.toLocaleString("en-US", { minimumFractionDigits: 2 })}`),
];
const READINGS: Record<number, Json> = {
  3: reading(0.95, [billDate, value(420_000), ...taxes(10_000, 8_400)]),
  4: reading(0.95, [billDate, value(420_000)]),
  5: reading(0.95, [value(440_000)]),
  6: reading(0.95, [value(500_000)]),
  7: reading(0.95, [value(497_500)]),
  8: reading(0.95, [value(3_000_000)]),
  9: reading(0.2, []),
  10: reading(0.95, [billDate, value(420_000), ...taxes(10_000, 8_400)]),
  16: reading(0.95, [value(470_000), ...taxes(10_000, 9_400)]),
};

const fullBill = ["Bill date: 2026-12-01", "Corrected assessed value: $420,000", "Original tax amount: $10,000.00", "Corrected tax amount: $8,400.00"];
const invoice = (issuedOn: string, over: Json = {}): Json => ({ number: "PH-INV-1", issuedOn, dueOn: "2027-01-01", amount: 480, reminders: [], ...over });

export function buildSamples(): Sample[] {
  const s: Sample[] = [];
  const add = (n: number, title: string, c: Json, b: Json | null, expect: Sample["expect"]) => s.push({ n, title, case: c, bill: b, reading: b ? READINGS[n] ?? null : null, expect });
  add(1, "Won, no corrected bill yet", makeCase(1), null, { status: "WAITING", code: "P_AWAIT_BILL" });
  add(2, "Won long ago, no bill within the wait limit", makeCase(2, { wonOn: "2026-07-01" }), null, { status: "CLOSED", code: "C_NO_PROOF" });
  add(3, "Corrected bill shows the tax amounts", makeCase(3), bill(3, fullBill), { status: "INVOICED", code: "V_INVOICE_ISSUED", flags: ["F_SAVINGS_FROM_BILL"], fee: 480 });
  add(4, "Corrected bill shows only the value", makeCase(4), bill(4, ["Bill date: 2026-12-01", "Corrected assessed value: $420,000"]), { status: "INVOICED", code: "V_INVOICE_ISSUED", flags: ["F_SAVINGS_ESTIMATED"], fee: 480 });
  add(5, "Bill value differs from the decision", makeCase(5), bill(5, ["Corrected assessed value: $440,000"]), { status: "INVOICED", code: "V_INVOICE_ISSUED", flags: ["F_VALUE_DIFFERS"], fee: 360 });
  add(6, "Bill shows no reduction", makeCase(6), bill(6, ["Corrected assessed value: $500,000"]), { status: "CLOSED", code: "C_NO_REDUCTION_ON_BILL" });
  add(7, "Fee below the minimum", makeCase(7, { wonAssessedValue: 497_500 }), bill(7, ["Corrected assessed value: $497,500"]), { status: "CLOSED", code: "C_FEE_BELOW_MIN" });
  add(8, "Fee capped at the maximum", makeCase(8, { oldAssessedValue: 5_000_000, wonAssessedValue: 3_000_000 }), bill(8, ["Corrected assessed value: $3,000,000"]), { status: "INVOICED", code: "V_INVOICE_ISSUED", flags: ["F_FEE_CAPPED"], fee: 5000 });
  add(9, "Unreadable bill", makeCase(9), bill(9, ["We have updated your account. Details will follow."]), { status: "WAITING", code: "P_AWAIT_BILL", flags: ["F_BILL_UNREADABLE"] });
  add(10, "Bill for a different case", makeCase(10), bill(10, fullBill, { caseId: id(99) }), { status: "INCOMPLETE", code: "I_BILL_MISMATCH" });
  add(11, "Invoice sent, before the first reminder", makeCase(11, { invoice: invoice("2026-12-10") }), null, { status: "WAITING", code: "P_AWAIT_PAYMENT" });
  add(12, "Invoice unpaid, reminder due", makeCase(12, { invoice: invoice("2026-11-25") }), null, { status: "INVOICED", code: "V_REMINDER" });
  add(13, "Invoice unpaid past the write-off date", makeCase(13, { invoice: invoice("2026-10-01") }), null, { status: "CLOSED", code: "C_WRITTEN_OFF" });
  add(14, "Invoice paid", makeCase(14, { invoice: invoice("2026-11-25", { paid: { on: "2026-12-02", ref: "pi_sample_14" } }) }), null, { status: "PAID", code: "D_PAID" });
  add(15, "Not a won case", makeCase(15, { wonCode: "C_REFER_OUT" }), null, { status: "INCOMPLETE", code: "I_SCHEMA" });
  add(16, "Partial win with a corrected bill", makeCase(16, { wonCode: "W_PARTIAL_ACCEPTED", wonAssessedValue: 470_000 }), bill(16, ["Corrected assessed value: $470,000", "Original tax amount: $10,000.00", "Corrected tax amount: $9,400.00"]), { status: "INVOICED", code: "V_INVOICE_ISSUED", fee: 180 });
  return s;
}
