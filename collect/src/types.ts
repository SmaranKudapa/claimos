/**
 * Shared types for the Collect step.
 *
 * CollectCase   — a case Escalate marked won, plus any invoice already issued for it.
 * TaxBill       — the county's corrected tax bill (or roll notice) text, when it has arrived.
 * BillReading   — numbers read from the bill, each backed by a quote from it.
 * CollectConfig — fee bounds, due dates, reminder schedule and waits: every desk rule.
 * CollectResult — what Collect decided; executed automatically by the next agent.
 */
import { z } from "zod";

export const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected a YYYY-MM-DD date");

export const InvoiceStateSchema = z.object({
  number: z.string().min(1),
  issuedOn: isoDate,
  dueOn: isoDate,
  amount: z.number().positive(),
  /** Dates reminders were issued. */
  reminders: z.array(isoDate).default([]),
  paymentLink: z.object({ url: z.string(), id: z.string().optional() }).optional(),
  paid: z.object({ on: isoDate, ref: z.string().min(1) }).optional(),
});
export type InvoiceState = z.infer<typeof InvoiceStateSchema>;

export const CollectCaseSchema = z.object({
  /** The team's case id (Find's case_id). */
  caseId: z.string().min(1),
  parcelId: z.string().min(1),
  jurisdictionId: z.string().min(1),
  address: z.string().min(1),
  owner: z.object({ names: z.array(z.string()), type: z.string(), contactChannel: z.enum(["email", "mail", "sms", "phone", "portal"]) }),
  /** Value before the appeal (the county's original value). */
  oldAssessedValue: z.number().positive(),
  /** The reduced value the county granted, quote-verified by Escalate. */
  wonAssessedValue: z.number().positive(),
  /** Effective tax rate (fraction): used only when the bill does not show the tax amounts. */
  taxRate: z.number().positive().max(1),
  feePct: z.number().min(0).max(1),
  /** desk_default = Sign up has not recorded the owner's authorization yet. */
  authorizationSource: z.enum(["signed", "desk_default"]).default("desk_default"),
  /** When the county decided (from Escalate). */
  wonOn: isoDate,
  /** Escalate's reason code (W_FULL_WIN or W_PARTIAL_ACCEPTED) and the letter id. */
  wonCode: z.string().regex(/^W_/),
  decisionId: z.string().min(1),
  invoice: InvoiceStateSchema.optional(),
});
export type CollectCase = z.infer<typeof CollectCaseSchema>;

export const TaxBillSchema = z.object({
  docId: z.string().min(1),
  caseId: z.string().min(1),
  receivedOn: isoDate,
  text: z.string(),
});
export type TaxBill = z.infer<typeof TaxBillSchema>;

export const BillReadingSchema = z.object({
  /** The assessed (taxable basis) value the corrected bill states. */
  assessedValue: z.number().positive().optional(),
  /** The tax amount before the correction, if the bill shows it. */
  originalTax: z.number().min(0).optional(),
  /** The corrected tax amount, if the bill shows it. */
  correctedTax: z.number().min(0).optional(),
  billDate: isoDate.optional(),
  confidence: z.number().min(0).max(1),
  /** One quote per fact. Fields: assessedValue, originalTax, correctedTax, billDate. */
  evidence: z.array(z.object({ field: z.string(), quote: z.string() })).default([]),
});
export type BillReading = z.infer<typeof BillReadingSchema>;

export const CollectConfigSchema = z
  .object({
    version: z.string().min(1),
    jurisdictionId: z.string().min(1),
    fee: z.object({
      /** Fee basis: the first year's tax savings. */
      basis: z.literal("first_year_savings"),
      /** Used when Sign up has not recorded the owner's fee terms. */
      defaultPct: z.number().min(0).max(1),
      minFee: z.number().min(0),
      maxFee: z.number().positive(),
      currency: z.string().length(3),
    }),
    invoice: z.object({
      dueDays: z.number().int().min(1),
      /** Reminders this many days after the invoice date. */
      reminderDays: z.array(z.number().int().min(1)).min(1),
      /** Written off this many days after the invoice date if still unpaid. */
      writeOffDays: z.number().int().min(1),
      numberPrefix: z.string().min(1),
    }),
    bill: z.object({
      /** Wait for the corrected bill before invoicing (the portal promises this). */
      required: z.boolean(),
      recheckDays: z.number().int().min(1),
      /** Stop waiting this many days after the decision: close without a fee. */
      maxWaitDays: z.number().int().min(1),
      /** Tolerance when comparing the bill's value with the value the county granted. */
      valueToleranceUsd: z.number().min(0),
      minReadConfidence: z.number().min(0).max(1),
    }),
  })
  .superRefine((cfg, ctx) => {
    if (cfg.fee.minFee > cfg.fee.maxFee) ctx.addIssue({ code: "custom", path: ["fee", "minFee"], message: "minFee must be ≤ maxFee" });
    const days = cfg.invoice.reminderDays;
    if (days.some((d, i) => i > 0 && d <= days[i - 1]!)) ctx.addIssue({ code: "custom", path: ["invoice", "reminderDays"], message: "reminder days must increase" });
    if (cfg.invoice.writeOffDays <= days[days.length - 1]!) ctx.addIssue({ code: "custom", path: ["invoice", "writeOffDays"], message: "writeOffDays must be after the last reminder" });
    if (cfg.invoice.dueDays > cfg.invoice.writeOffDays) ctx.addIssue({ code: "custom", path: ["invoice", "dueDays"], message: "dueDays must be ≤ writeOffDays" });
  });
export type CollectConfig = z.infer<typeof CollectConfigSchema>;

export type Status = "INCOMPLETE" | "WAITING" | "INVOICED" | "PAID" | "CLOSED";
export const STATUSES: readonly Status[] = ["INCOMPLETE", "WAITING", "INVOICED", "PAID", "CLOSED"];

export interface PaymentRequest {
  /** Amount in the smallest currency unit (cents). */
  amountCents: number;
  currency: string;
  description: string;
  /** The invoice number, so the payment can be matched back. */
  reference: string;
}

export interface OwnerMessage {
  channel: string;
  subject: string;
  body: string;
  autoSend: true;
}

export interface CollectResult {
  caseId: string;
  parcelId: string;
  jurisdictionId: string;
  address: string;
  status: Status;
  reasonCodes: string[];
  flags: string[];
  summary: string;
  bill: { docId: string | null; verified: BillReading | null; droppedFields: string[] };
  savings: { oldTax: number | null; newTax: number | null; annual: number; fromBill: boolean } | null;
  fee: { pct: number; computed: number; charged: number; capped: boolean } | null;
  invoice: InvoiceState | null;
  paymentRequest: PaymentRequest | null;
  requeueOn: string | null;
  ownerMessage: OwnerMessage | null;
  stageLog: { stage: string; outcome: "pass" | "stop" | "skip"; detail: string }[];
  audit: { configVersion: string; inputHash: string; decidedAt: string; decidedBy: "collect-rules" };
}
