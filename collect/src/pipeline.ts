/**
 * Collect pipeline, one case at a time:
 *   K0 intake → K1 follow up an issued invoice (paid / reminder / write-off / wait) →
 *   K2 corrected-bill proof (wait, close, or verify) → K3 savings and fee → K4 invoice.
 * Every result is final for this run and acted on automatically; nothing waits for a person.
 */
import { statusFor } from "./codes.js";
import { coversJurisdiction } from "./config.js";
import { ownerMessage } from "./owner-message.js";
import { verifyBillQuotes } from "./reader/verify-quotes.js";
import type { BillReader } from "./reader/types.js";
import { CollectCaseSchema, TaxBillSchema, type BillReading, type CollectCase, type CollectConfig, type CollectResult, type InvoiceState, type TaxBill } from "./types.js";
import { addDays, daysBetween, minDate, round, sha256, stableStringify } from "./util.js";

export interface CollectContext {
  config: CollectConfig;
  today: string;
  reader: BillReader;
}

interface Draft {
  ctx: CollectContext;
  c: CollectCase;
  bill: TaxBill | null;
  codes: string[];
  flags: Set<string>;
  log: CollectResult["stageLog"];
  stopped: boolean;
  reading: BillReading | null;
  dropped: string[];
  savings: CollectResult["savings"];
  fee: CollectResult["fee"];
  invoice: InvoiceState | null;
  paymentRequest: CollectResult["paymentRequest"];
  requeueOn: string | null;
}

const log = (d: Draft, stage: string, outcome: "pass" | "stop" | "skip", detail: string): void => {
  d.log.push({ stage, outcome, detail });
};
function stop(d: Draft, stage: string, code: string, detail: string) {
  d.codes.push(code);
  d.stopped = true;
  log(d, stage, "stop", `${code}: ${detail}`);
}

/** K1 · An invoice already exists: paid, reminder due, written off, or keep waiting. */
function followUp(d: Draft): void {
  const inv = d.c.invoice;
  if (!inv) return log(d, "K1", "skip", "no invoice yet");
  const cfg = d.ctx.config.invoice;
  d.invoice = { ...inv, reminders: [...inv.reminders] };
  if (inv.paid) return stop(d, "K1", "D_PAID", `${inv.number} paid ${inv.paid.on} (${inv.paid.ref})`);
  const age = daysBetween(inv.issuedOn, d.ctx.today);
  const writeOff = addDays(inv.issuedOn, cfg.writeOffDays);
  if (age >= cfg.writeOffDays) return stop(d, "K1", "C_WRITTEN_OFF", `${inv.number} unpaid ${age} days (write-off at ${cfg.writeOffDays})`);
  const due = cfg.reminderDays.filter((n) => n <= age).length;
  const nextDay = cfg.reminderDays.find((n) => n > age);
  const nextDate = nextDay !== undefined ? addDays(inv.issuedOn, nextDay) : writeOff;
  if (due > inv.reminders.length) {
    d.invoice.reminders.push(d.ctx.today);
    d.requeueOn = nextDate;
    return stop(d, "K1", "V_REMINDER", `reminder ${due} of ${cfg.reminderDays.length} for ${inv.number}; next check ${nextDate}`);
  }
  d.requeueOn = nextDate;
  stop(d, "K1", "P_AWAIT_PAYMENT", `${inv.number} due ${inv.dueOn}; next check ${nextDate}`);
}

/** Wait for a bill, or stop waiting past the limit (close without a fee). */
function awaitBill(d: Draft, why: string): void {
  const b = d.ctx.config.bill;
  const limit = addDays(d.c.wonOn, b.maxWaitDays);
  if (d.ctx.today > limit) return stop(d, "K2", "C_NO_PROOF", `${why}; wait limit ${limit} passed`);
  d.requeueOn = minDate(addDays(d.ctx.today, b.recheckDays), limit);
  stop(d, "K2", "P_AWAIT_BILL", `${why}; check again ${d.requeueOn} (limit ${limit})`);
}

/** K2 · Corrected-bill proof. */
async function proof(d: Draft): Promise<number> {
  const b = d.ctx.config.bill;
  if (!d.bill) {
    if (!b.required) {
      log(d, "K2", "pass", "bill not required by this desk; using the value the county granted");
      return d.c.wonAssessedValue;
    }
    awaitBill(d, "no corrected bill yet");
    return 0;
  }
  const raw = await d.ctx.reader.read(d.bill);
  const { reading, dropped } = verifyBillQuotes(raw, d.bill.text);
  d.reading = reading;
  d.dropped = dropped;
  const usable = reading.confidence >= b.minReadConfidence && (reading.assessedValue !== undefined || (reading.originalTax !== undefined && reading.correctedTax !== undefined));
  if (!usable) {
    d.flags.add("F_BILL_UNREADABLE");
    awaitBill(d, `bill ${d.bill.docId} not readable with confidence (dropped: ${dropped.join(", ") || "none"})`);
    return 0;
  }
  const value = reading.assessedValue ?? d.c.wonAssessedValue;
  if (reading.assessedValue !== undefined) {
    if (reading.assessedValue >= d.c.oldAssessedValue - b.valueToleranceUsd) {
      stop(d, "K2", "C_NO_REDUCTION_ON_BILL", `bill value ${reading.assessedValue} vs original ${d.c.oldAssessedValue}`);
      return 0;
    }
    if (Math.abs(reading.assessedValue - d.c.wonAssessedValue) > b.valueToleranceUsd) d.flags.add("F_VALUE_DIFFERS");
  }
  log(d, "K2", "pass", `bill ${d.bill.docId}: value ${value}${reading.originalTax !== undefined ? `, tax ${reading.originalTax} → ${reading.correctedTax}` : ""}`);
  return value;
}

/** K3 · Savings and fee. */
function feeStage(d: Draft, billValue: number): void {
  const r = d.reading;
  const f = d.ctx.config.fee;
  let annual: number;
  let oldTax: number | null = null;
  let newTax: number | null = null;
  if (r?.originalTax !== undefined && r.correctedTax !== undefined) {
    oldTax = r.originalTax;
    newTax = r.correctedTax;
    annual = oldTax - newTax;
    d.flags.add("F_SAVINGS_FROM_BILL");
  } else {
    annual = (d.c.oldAssessedValue - billValue) * d.c.taxRate;
    d.flags.add("F_SAVINGS_ESTIMATED");
  }
  annual = round(annual, 2);
  d.savings = { oldTax, newTax, annual, fromBill: oldTax !== null };
  if (annual <= 0) return stop(d, "K3", "C_NO_SAVINGS", `savings ${annual}`);
  const computed = round(d.c.feePct * annual, 2);
  const charged = round(Math.min(computed, f.maxFee), 2);
  d.fee = { pct: d.c.feePct, computed, charged, capped: computed > f.maxFee };
  if (d.fee.capped) d.flags.add("F_FEE_CAPPED");
  if (charged < f.minFee) return stop(d, "K3", "C_FEE_BELOW_MIN", `fee ${charged} < minimum ${f.minFee}`);
  log(d, "K3", "pass", `savings $${annual}/yr · fee ${(d.c.feePct * 100).toFixed(0)}% = $${computed}${d.fee.capped ? ` capped at $${charged}` : ""}`);
}

/** K4 · Invoice and payment request. */
function invoiceStage(d: Draft): void {
  const cfg = d.ctx.config;
  const amount = d.fee!.charged;
  const number = `${cfg.invoice.numberPrefix}-${d.c.caseId}-${sha256(d.bill?.docId ?? d.c.decisionId).slice(0, 6)}`;
  d.invoice = { number, issuedOn: d.ctx.today, dueOn: addDays(d.ctx.today, cfg.invoice.dueDays), amount, reminders: [] };
  d.paymentRequest = {
    amountCents: Math.round(amount * 100),
    currency: cfg.fee.currency,
    description: `Claim OS success fee, property tax appeal: ${d.c.address} (case ${d.c.caseId}), invoice ${number}`,
    reference: number,
  };
  d.requeueOn = addDays(d.ctx.today, cfg.invoice.reminderDays[0]!);
  stop(d, "K4", "V_INVOICE_ISSUED", `${number} for $${amount}, due ${d.invoice.dueOn}`);
}

/** An unpaid invoice without a payment link keeps asking for one (e.g. Stripe was connected later). */
function linkRequest(d: Draft): CollectResult["paymentRequest"] {
  const inv = d.invoice!;
  return {
    amountCents: Math.round(inv.amount * 100),
    currency: d.ctx.config.fee.currency,
    description: `Claim OS success fee, property tax appeal: ${d.c.address} (case ${d.c.caseId}), invoice ${inv.number}`,
    reference: inv.number,
  };
}

function finish(d: Draft, inputHash: string): CollectResult {
  let status = statusFor(d.codes);
  if (!status) {
    d.codes.push("C_UNHANDLED");
    status = "CLOSED";
  }
  const lead = d.codes.find((c) => statusFor([c]) === status)!;
  const money = d.invoice ? ` · $${d.invoice.amount} ${d.invoice.number}` : d.savings ? ` · savings $${d.savings.annual}/yr` : "";
  const when = d.requeueOn ? ` · check again ${d.requeueOn}` : "";
  return {
    caseId: d.c.caseId,
    parcelId: d.c.parcelId,
    jurisdictionId: d.c.jurisdictionId,
    address: d.c.address,
    status,
    reasonCodes: d.codes,
    flags: [...d.flags].sort(),
    summary: `${status} · ${lead}${money}${when}`,
    bill: { docId: d.bill?.docId ?? null, verified: d.reading, droppedFields: d.dropped },
    savings: d.savings,
    fee: d.fee,
    invoice: status === "CLOSED" && lead !== "C_WRITTEN_OFF" ? null : d.invoice,
    paymentRequest: lead === "V_INVOICE_ISSUED" ? d.paymentRequest : (status === "INVOICED" || status === "WAITING") && d.invoice && !d.invoice.paid && !d.invoice.paymentLink ? linkRequest(d) : null,
    requeueOn: status === "WAITING" || status === "INVOICED" ? d.requeueOn : null,
    ownerMessage: ownerMessage(d.c, status, lead, { reading: d.reading, savings: d.savings, fee: d.fee, invoice: d.invoice }),
    stageLog: d.log,
    audit: { configVersion: d.ctx.config.version, inputHash, decidedAt: new Date().toISOString(), decidedBy: "collect-rules" },
  };
}

function schemaResult(ctx: CollectContext, raw: unknown, detail: string): CollectResult {
  const g = (k: string) => (raw && typeof raw === "object" ? String((raw as Record<string, unknown>)[k] ?? "unknown") : "unknown");
  return {
    caseId: g("caseId"), parcelId: g("parcelId"), jurisdictionId: g("jurisdictionId"), address: g("address"),
    status: "INCOMPLETE", reasonCodes: ["I_SCHEMA"], flags: [], summary: `INCOMPLETE · I_SCHEMA · ${detail}`,
    bill: { docId: null, verified: null, droppedFields: [] }, savings: null, fee: null, invoice: null, paymentRequest: null, requeueOn: null, ownerMessage: null,
    stageLog: [{ stage: "K0", outcome: "stop", detail: `I_SCHEMA: ${detail}` }],
    audit: { configVersion: ctx.config.version, inputHash: sha256(stableStringify(raw)), decidedAt: new Date().toISOString(), decidedBy: "collect-rules" },
  };
}

export async function collect(rawCase: unknown, rawBill: unknown | null, ctx: CollectContext): Promise<CollectResult> {
  const c = CollectCaseSchema.safeParse(rawCase);
  const b = rawBill ? TaxBillSchema.safeParse(rawBill) : null;
  if (!c.success || (b && !b.success)) {
    const issues = [...(c.success ? [] : c.error.issues.map((i) => `case.${i.path.join(".")}: ${i.message}`)), ...(b && !b.success ? b.error.issues.map((i) => `bill.${i.path.join(".")}: ${i.message}`) : [])];
    return schemaResult(ctx, rawCase, issues.slice(0, 3).join("; "));
  }
  const d: Draft = {
    ctx, c: c.data, bill: b?.success ? b.data : null, codes: [], flags: new Set(), log: [], stopped: false,
    reading: null, dropped: [], savings: null, fee: null, invoice: null, paymentRequest: null, requeueOn: null,
  };
  const inputHash = sha256(stableStringify({ case: d.c, bill: d.bill }));
  if (d.c.authorizationSource === "desk_default") d.flags.add("F_DEFAULT_AUTHORIZATION");
  if (!coversJurisdiction(ctx.config, d.c.jurisdictionId)) {
    stop(d, "K0", "I_SCHEMA", `jurisdiction ${d.c.jurisdictionId} not covered by desk ${ctx.config.jurisdictionId}`);
    return finish(d, inputHash);
  }
  if (d.bill && d.bill.caseId !== d.c.caseId) {
    stop(d, "K0", "I_BILL_MISMATCH", `bill is for ${d.bill.caseId}`);
    return finish(d, inputHash);
  }
  log(d, "K0", "pass", `${d.c.wonCode} on ${d.c.wonOn}: ${d.c.oldAssessedValue} → ${d.c.wonAssessedValue}`);
  followUp(d);
  if (d.stopped) return finish(d, inputHash);
  const value = await proof(d);
  if (d.stopped) return finish(d, inputHash);
  feeStage(d, value);
  if (d.stopped) return finish(d, inputHash);
  invoiceStage(d);
  return finish(d, inputHash);
}

export async function collectAll(items: { case: unknown; bill?: unknown | null }[], ctx: CollectContext): Promise<CollectResult[]> {
  const out: CollectResult[] = [];
  for (const it of items) out.push(await collect(it.case, it.bill ?? null, ctx));
  return out;
}
