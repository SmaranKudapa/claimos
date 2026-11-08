/**
 * Shared types for the Escalate step ("Appeal again").
 *
 * EscalateCase    — the case as it stands after the county answered (from Chase).
 * CountyDecision  — the county's decision letter (from Chase).
 * EscalateConfig  — the desk's appeal ladder, economics and fallbacks: every jurisdiction rule.
 * DecisionReading — facts a reader pulled out of the letter, each backed by a quote.
 * EscalateResult  — what Escalate decided; executed automatically by the next agent.
 */
import { z } from "zod";

export const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected a YYYY-MM-DD date");

// ─── Inputs ────────────────────────────────────────────────────────────────

export const AuthorizationSchema = z.object({
  signedOn: isoDate,
  feePct: z.number().min(0).max(1),
  /** Ladder rung ids the owner authorized, or ["all_levels"]. */
  scope: z.array(z.string().min(1)).min(1),
  escalation: z
    .object({
      /** Appeal the rest of a partial win only if the remaining savings exceed this ($/yr). */
      appealPartialIfRemainingAnnualAbove: z.number().min(0).optional(),
      /** The owner accepts a level where the value could go up. Default false. */
      acceptReopenRisk: z.boolean().default(false),
    })
    .optional(),
});
export type Authorization = z.infer<typeof AuthorizationSchema>;

export const EscalateCaseSchema = z.object({
  /** The team's case id (Find's case_id, e.g. FL-13-2026-…), shared by every step. */
  caseId: z.string().min(1),
  parcelId: z.string().min(1),
  jurisdictionId: z.string().min(1),
  address: z.string().min(1),
  owner: z.object({
    names: z.array(z.string()),
    type: z.string(),
    /** The channel the owner consented to at sign-up. */
    contactChannel: z.enum(["email", "mail", "sms", "phone", "portal"]),
  }),
  /** The value under appeal at the current level. */
  assessedValue: z.number().positive(),
  /** The value we argue for (Qualify's valuation.target). */
  targetValue: z.number().positive(),
  taxRate: z.number().positive().max(1),
  qualify: z.object({ pWin: z.number().min(0).max(1), confidence: z.number().min(0).max(1).optional(), annualSavings: z.number().optional() }).optional(),
  /** Ladder rung id of the filing this decision answers. First filing = Qualify's route.id. */
  currentLevel: z.string().min(1),
  filings: z.array(z.object({ level: z.string(), filedOn: isoDate, receiptRef: z.string().optional(), claimedValue: z.number() })).default([]),
  authorization: AuthorizationSchema,
  /** desk_default = Sign up has not recorded one yet; the desk config's conservative default was used. */
  authorizationSource: z.enum(["signed", "desk_default"]).default("signed"),
  evidence: z.object({ compCount: z.number().int().min(0), hasPhotos: z.boolean(), hasOwnerStatement: z.boolean() }).optional(),
  priorDecisions: z.array(z.object({ level: z.string(), outcome: z.string(), decidedOn: isoDate })).default([]),
  /** Lets retries and clarification resume across runs. */
  readAttempts: z.array(z.object({ decisionId: z.string(), attempts: z.number().int().min(0), firstPendingOn: isoDate })).default([]),
});
export type EscalateCase = z.infer<typeof EscalateCaseSchema>;

export const CountyDecisionSchema = z.object({
  decisionId: z.string().min(1),
  caseId: z.string().min(1),
  level: z.string().min(1),
  receivedOn: isoDate,
  channel: z.enum(["email", "mail", "portal", "fax"]),
  /** Full letter text (already OCR'd if it was a scan). */
  text: z.string(),
  attachments: z.array(z.object({ ref: z.string(), kind: z.string() })).default([]),
});
export type CountyDecision = z.infer<typeof CountyDecisionSchema>;

// ─── Desk config ───────────────────────────────────────────────────────────

export const RungSchema = z.object({
  id: z.string().min(1),
  /** Other names teammates use for this level (e.g. a File adapter's route id). */
  aliases: z.array(z.string()).default([]),
  order: z.number().int().min(1),
  name: z.string(),
  formId: z.string(),
  deadline: z.object({ type: z.literal("days_after_decision"), days: z.number().int() }),
  filingFee: z.number().min(0),
  workDaysNeeded: z.number().int().min(0),
  bufferDays: z.number().int().min(0),
  fastTrackDays: z.number().int().min(0),
  pWinMultiplier: z.number().positive(),
  hearing: z.boolean(),
  requiresLicensedRep: z.boolean(),
  valueCanIncrease: z.boolean(),
  /** Plain words for the owner update when this level needs a licensed professional. */
  referOutNote: z.string().optional(),
});
export type Rung = z.infer<typeof RungSchema>;

export const EscalateConfigSchema = z
  .object({
    version: z.string().min(1),
    jurisdictionId: z.string().min(1),
    ladder: z.array(RungSchema).min(1),
    economics: z.object({
      feePct: z.number().min(0).max(1),
      persistenceCycles: z.number().int().min(1),
      costs: z.object({ evidenceRefresh: z.number().min(0), hearingPrep: z.number().min(0), llm: z.number().min(0) }),
      defaultPWin: z.number().min(0).max(1),
      pWinCap: z.number().min(0).max(1),
      pWinFloor: z.number().min(0).max(1),
      minExpectedValue: z.number(),
      minRemainingGapPct: z.number().min(0),
      minRemainingAnnualSavings: z.number().min(0),
    }),
    denialReasons: z.record(z.string(), z.object({ pWinMultiplier: z.number().positive(), evidence: z.array(z.string()) })),
    proceduralReasons: z.record(z.string(), z.object({ curable: z.boolean(), refileWithinDays: z.number().int().positive().optional() })),
    reader: z.object({
      model: z.string().nullable().default(null),
      escalationModel: z.string().nullable().default(null),
      promptVersion: z.string(),
      minReadConfidence: z.number().min(0).max(1),
      maxReadAttempts: z.number().int().min(1),
      retryAfterDays: z.number().int().min(1),
      clarifyMaxDays: z.number().int().min(1),
      /** How long to wait before checking again on a decision that is not final yet. */
      notFinalRecheckDays: z.number().int().min(1).default(7),
      maxCostPerCaseUsd: z.number().positive(),
      priceUsdPerMTokIn: z.number().min(0),
      priceUsdPerMTokOut: z.number().min(0),
    }),
    budget: z.object({ maxFilingFeesPerDayUsd: z.number().min(0) }),
    /** Used when Sign up has not recorded the owner's authorization yet. Keep it narrow. */
    defaultAuthorization: z.object({ scope: z.array(z.string().min(1)).min(1), feePct: z.number().min(0).max(1) }).optional(),
  })
  .superRefine((cfg, ctx) => {
    const ids = new Set<string>();
    cfg.ladder.forEach((r, i) => {
      for (const id of [r.id, ...r.aliases]) {
        if (ids.has(id)) ctx.addIssue({ code: "custom", path: ["ladder", i, "id"], message: `duplicate rung id ${id}` });
        ids.add(id);
      }
      if (r.deadline.days <= 0) ctx.addIssue({ code: "custom", path: ["ladder", i, "deadline", "days"], message: "deadline days must be > 0" });
      if (r.fastTrackDays > r.workDaysNeeded) ctx.addIssue({ code: "custom", path: ["ladder", i, "fastTrackDays"], message: "fastTrackDays must be ≤ workDaysNeeded" });
    });
    const orders = cfg.ladder.map((r) => r.order).sort((a, b) => a - b);
    orders.forEach((o, i) => {
      if (o !== i + 1) ctx.addIssue({ code: "custom", path: ["ladder"], message: `rung orders must run 1, 2, 3… without gaps or repeats (got ${orders.join(", ")})` });
    });
    if (cfg.economics.pWinFloor >= cfg.economics.pWinCap)
      ctx.addIssue({ code: "custom", path: ["economics", "pWinFloor"], message: "pWinFloor must be < pWinCap" });
    if (!cfg.denialReasons.other) ctx.addIssue({ code: "custom", path: ["denialReasons", "other"], message: "an 'other' denial reason is required" });
    if (!cfg.proceduralReasons.other) ctx.addIssue({ code: "custom", path: ["proceduralReasons", "other"], message: "an 'other' procedural reason is required" });
  });
export type EscalateConfig = z.infer<typeof EscalateConfigSchema>;

// ─── Reading ───────────────────────────────────────────────────────────────

export const OUTCOMES = ["full_win", "partial_reduction", "denied", "dismissed_procedural", "not_final", "unclear"] as const;
export type Outcome = (typeof OUTCOMES)[number];

export const DecisionReadingSchema = z.object({
  outcome: z.enum(OUTCOMES),
  newAssessedValue: z.number().positive().optional(),
  decisionDate: isoDate.optional(),
  reasonCategories: z.array(z.string()).default([]),
  proceduralReason: z.string().optional(),
  statedNextStep: z.object({ name: z.string().optional(), deadline: isoDate.optional() }).optional(),
  hearingDate: isoDate.optional(),
  confidence: z.number().min(0).max(1),
  /** One quote per extracted fact. Field names: outcome, newAssessedValue, decisionDate,
   *  reasonCategories.<key>, proceduralReason, statedNextStep.deadline, hearingDate. */
  evidence: z.array(z.object({ field: z.string(), quote: z.string() })).default([]),
});
export type DecisionReading = z.infer<typeof DecisionReadingSchema>;

// ─── Result ────────────────────────────────────────────────────────────────

export type Status = "INCOMPLETE" | "PENDING" | "CLOSED" | "COLLECT" | "ESCALATE";
export const STATUSES: readonly Status[] = ["INCOMPLETE", "PENDING", "CLOSED", "COLLECT", "ESCALATE"];

export interface StageLogEntry {
  stage: string;
  outcome: "pass" | "stop" | "skip";
  detail: string;
}

export interface EvidenceRequest {
  key: string;
  why: string;
  forStep: "evidence";
}

export interface OwnerUpdate {
  channel: string;
  subject: string;
  body: string;
  autoSend: true;
}

export interface EscalateResult {
  caseId: string;
  parcelId: string;
  jurisdictionId: string;
  address: string;
  decisionId: string | null;
  status: Status;
  reasonCodes: string[];
  flags: string[];
  summary: string;
  reading: {
    verified: DecisionReading | null;
    droppedFields: string[];
    readers: string[];
    models: string[];
    costUsd: number;
    cached: boolean;
    secondRead: boolean;
  };
  nextLevel: { id: string; name: string; formId: string; deadline: string; daysLeft: number; filingFee: number; hearing: boolean; fastTrack: boolean } | null;
  economics: { gap: number; gapPct: number; annual: number; revenue: number; pWin: number; costs: number; ev: number; maxLoss: number } | null;
  evidenceRequests: EvidenceRequest[];
  requeueOn: string | null;
  /** Hand back to Chase with the next PENDING so retries and clarification resume where they left off. */
  readState: { decisionId: string; attempts: number; firstPendingOn: string } | null;
  /** For COLLECT: what Collect needs to compute the fee (value before the appeal, decision date). */
  collect: { oldValue: number; decidedOn: string } | null;
  ownerUpdate: OwnerUpdate | null;
  stageLog: StageLogEntry[];
  audit: { configVersion: string; inputHash: string; decidedAt: string; decidedBy: "escalate-rules" };
}
