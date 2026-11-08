/**
 * Shared types for the Qualify step.
 *
 * Candidate  — what Find hands us (validated in S0).
 * DeskConfig — the "desk adds" column: every jurisdiction-specific rule and threshold.
 * QualifyResult — what Qualify writes back to the shared Case.
 */
import { z } from "zod";

export const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected a YYYY-MM-DD date");

// ─── Candidate (from Find) ─────────────────────────────────────────────────

export const OWNER_TYPES = ["individual", "joint", "trust", "entity", "estate", "government"] as const;

export const CompSchema = z.object({
  compId: z.string().min(1),
  price: z.number(),
  saleDate: isoDate,
  livingArea: z.number(),
  propertyType: z.string(),
  yearBuilt: z.number().int().optional(),
  /** Distance from the subject, in whatever unit the desk config uses for compRules.maxDistance. */
  distance: z.number(),
  armsLength: z.boolean().default(true),
});
export type Comp = z.infer<typeof CompSchema>;

export const RawDocSchema = z.object({
  ref: z.string().min(1),
  kind: z.string(),
  text: z.string(),
});
export type RawDoc = z.infer<typeof RawDocSchema>;

export const CandidateSchema = z.object({
  parcelId: z.string().min(1),
  jurisdictionId: z.string().min(1),
  situsAddress: z.string().min(1),
  propertyType: z.string().min(1),
  useCode: z.string().optional(),
  owner: z.object({
    names: z.array(z.string()),
    type: z.enum(OWNER_TYPES),
    mailingAddress: z.string().optional(),
    ownerOccupied: z.boolean().optional(),
  }),
  assessment: z.object({
    assessedValue: z.number(),
    valuationDate: isoDate,
    /** Value-based tax rate as a fraction (fixed charges excluded). */
    taxRate: z.number(),
    history: z.array(z.object({ valuationDate: isoDate, assessedValue: z.number() })).optional(),
    exemptions: z
      .array(z.object({ type: z.string(), fullyExempt: z.boolean().default(false) }))
      .default([]),
  }),
  physical: z.object({
    livingArea: z.number(),
    lotArea: z.number().optional(),
    yearBuilt: z.number().int().optional(),
    lastPermitDate: isoDate.optional(),
    permitTypes: z.array(z.string()).default([]),
  }),
  transfer: z.object({ date: isoDate, price: z.number(), armsLength: z.boolean() }).optional(),
  /** Needed only for the uniformity claim basis. */
  neighborhood: z.object({ medianAssessmentRatio: z.number() }).optional(),
  /** Absent = Find never fetched comps (INCOMPLETE). Present but short = not enough comps (REJECTED). */
  comps: z.array(CompSchema).optional(),
  status: z.object({
    appealOnFile: z.boolean(),
    priorAppealOutcome: z.string().optional(),
    existingCaseId: z.string().optional(),
  }),
  provenance: z.object({
    fetchedAt: isoDate,
    sources: z.record(z.string(), z.string()).default({}),
    rawDocs: z.array(RawDocSchema).default([]),
  }),
});
export type Candidate = z.infer<typeof CandidateSchema>;

// ─── Desk config ────────────────────────────────────────────────────────────

export const CLAIM_BASES = ["market_value", "uniformity"] as const;
export const ClaimBasisSchema = z.enum(CLAIM_BASES);
export type ClaimBasis = z.infer<typeof ClaimBasisSchema>;

export const RouteSchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  formId: z.string(),
  opens: isoDate,
  closes: isoDate,
  filingFee: z.number().min(0),
  /** Days we need for sign-up + evidence + filing. */
  workDaysNeeded: z.number().int().min(0),
  bufferDays: z.number().int().min(0),
  filer: z.enum(["owner", "agent", "either"]),
  authorizationRequired: z.boolean(),
  claimBases: z.array(ClaimBasisSchema).min(1),
  /** Relative strength of this route (e.g. a formal hearing vs. an informal review). */
  pWinMultiplier: z.number().positive().default(1),
  /** Overrides jurisdiction.reductionPersistenceCycles for this route. */
  reductionPersistenceCycles: z.number().int().min(1).optional(),
});
export type Route = z.infer<typeof RouteSchema>;

export const DeskConfigSchema = z
  .object({
    version: z.string().min(1),
    jurisdiction: z.object({
      id: z.string().min(1),
      name: z.string(),
      valuationDate: isoDate,
      supportedPropertyTypes: z.array(z.string()).min(1),
      /** Maps source property-type codes to the engine vocabulary, e.g. { "R1": "SFR" }. */
      propertyTypeAliases: z.record(z.string(), z.string()).default({}),
      allowedClaimBases: z.array(ClaimBasisSchema).min(1),
      reductionPersistenceCycles: z.number().int().min(1),
      discountRate: z.number().min(0).default(0),
      /** Permit types that count as a value-change event. */
      majorPermitTypes: z.array(z.string()).default([]),
    }),
    routes: z.array(RouteSchema).min(1),
    /** When the next cycle's first route opens (used when nothing in `routes` opens later). */
    nextCycleOpens: isoDate.optional(),
    compRules: z.object({
      maxDistance: z.number().positive(),
      sizeTolerance: z.number().positive(),
      ageTolerance: z.number().positive().optional(),
      saleWindowBeforeDays: z.number().int().min(0),
      saleWindowAfterDays: z.number().int().min(0),
      minComps: z.number().int().min(1),
      maxComps: z.number().int().min(1),
      armsLengthOnly: z.boolean(),
      sameTypeOnly: z.boolean(),
    }),
    thresholds: z.object({
      minGapPct: z.number().min(0),
      minAnnualSavings: z.number().min(0),
      minExpectedValue: z.number(),
      minConfidence: z.number().min(0).max(1),
      /** Annual savings at or above this count as high value. */
      highValueReviewThreshold: z.number().min(0),
      /** While a desk is new, send every high-value lead to a human. */
      reviewHighValue: z.boolean(),
      transferLookbackDays: z.number().int().min(0),
      maxSourceAgeDays: z.number().int().min(0),
    }),
    economics: z.object({
      feePct: z.number().min(0).max(1),
      feeBasis: z.enum(["first_cycle", "total"]),
      preCosts: z.record(z.string(), z.number().min(0)),
      postCosts: z.record(z.string(), z.number().min(0)),
      pSignupPrior: z.number().min(0).max(1),
      complexOwnerSignupFactor: z.number().min(0).max(1).default(1),
      pWin: z.object({
        midpointGapPct: z.number(),
        scale: z.number().positive(),
        cap: z.number().min(0).max(1),
        confidenceFloor: z.number().min(0).max(1).default(0.4),
        flagPenalty: z.number().min(0).max(1),
        penalizedFlags: z.array(z.string()).default([]),
      }),
    }),
    timing: z.object({
      requalifyLeadDays: z.number().int().min(0),
      urgencyMaxBoost: z.number().min(1),
    }),
    suppression: z.object({
      cooldownDays: z.number().int().min(0),
      rejectionCacheDays: z.number().int().min(0),
    }),
    llm: z.object({
      enabled: z.boolean(),
      /** Null → read QUALIFY_MODEL from the environment. */
      model: z.string().nullable().default(null),
      escalationModel: z.string().nullable().default(null),
      promptVersion: z.string(),
      window: z.enum(["immediate", "priority", "loose"]).default("immediate"),
      maxTokens: z.number().int().positive(),
      maxCostPerLeadUsd: z.number().positive(),
      priceUsdPerMTokIn: z.number().min(0),
      priceUsdPerMTokOut: z.number().min(0),
      minEvToReview: z.number(),
      deskRulesText: z.string(),
    }),
    capacity: z.object({
      dailyReleaseLimit: z.number().int().min(0),
    }),
  })
  .superRefine((cfg, ctx) => {
    const ids = new Set<string>();
    cfg.routes.forEach((r, i) => {
      if (ids.has(r.id)) ctx.addIssue({ code: "custom", path: ["routes", i, "id"], message: `duplicate route id ${r.id}` });
      ids.add(r.id);
      if (r.closes < r.opens) ctx.addIssue({ code: "custom", path: ["routes", i, "closes"], message: "closes before it opens" });
      for (const b of r.claimBases) {
        if (!cfg.jurisdiction.allowedClaimBases.includes(b))
          ctx.addIssue({ code: "custom", path: ["routes", i, "claimBases"], message: `basis ${b} not allowed by jurisdiction` });
      }
    });
    if (cfg.compRules.maxComps < cfg.compRules.minComps)
      ctx.addIssue({ code: "custom", path: ["compRules", "maxComps"], message: "maxComps < minComps" });
  });
export type DeskConfig = z.infer<typeof DeskConfigSchema>;

// ─── Suppression list ──────────────────────────────────────────────────────

export const SuppressionSchema = z.object({
  dncParcels: z.array(z.string()).default([]),
  /** Normalized (upper-case, single-spaced) owner names. */
  dncOwners: z.array(z.string()).default([]),
  clientParcels: z.array(z.string()).default([]),
  representedParcels: z.array(z.string()).default([]),
  declined: z.array(z.object({ parcelId: z.string(), date: isoDate })).default([]),
});
export type Suppression = z.infer<typeof SuppressionSchema>;

// ─── Result ─────────────────────────────────────────────────────────────────

export type Status = "QUALIFIED" | "NEEDS_REVIEW" | "NEXT_CYCLE" | "INCOMPLETE" | "REJECTED";
export const STATUS_ORDER: Record<Status, number> = {
  QUALIFIED: 0,
  NEEDS_REVIEW: 1,
  NEXT_CYCLE: 2,
  INCOMPLETE: 3,
  REJECTED: 4,
};

export type StageId = "S0" | "S1" | "S2" | "S3" | "S4" | "S5" | "S6" | "S7";

export interface StageLogEntry {
  stage: StageId;
  outcome: "pass" | "stop" | "skip";
  detail?: string;
}

export interface ScoredComp {
  compId: string;
  similarity: number;
  impliedValue: number;
}

export interface BasisOption {
  basis: ClaimBasis;
  target: number;
  gap: number;
  gapPct: number;
}

export interface Valuation {
  estimate: number;
  low: number;
  high: number;
  confidence: number;
  compsUsed: ScoredComp[];
  compsExcluded: string[];
  /** Every allowed basis with a positive gap, best first. */
  bases: BasisOption[];
  /** The basis actually chosen (set in S5). */
  basis: ClaimBasis;
  target: number;
  gap: number;
  gapPct: number;
}

export interface Economics {
  annualSavings: number;
  totalSavings: number;
  fee: number;
  pWin: number;
  pSignup: number;
  preCosts: number;
  postCosts: number;
  ev: number;
  maxLoss: number;
}

export interface RoutePick {
  id: string;
  name: string;
  formId: string;
  deadline: string;
  daysLeft: number;
  urgency: number;
}

export type Verdict = "pass" | "concern" | "fail";

export interface LlmCheckResult {
  id: string;
  verdict: Verdict;
  evidence: string[];
  note: string;
  /** False when the verdict had no valid evidence reference and was ignored. */
  counted: boolean;
}

export interface LlmReview {
  ran: boolean;
  skippedReason?: string;
  model?: string;
  promptVersion?: string;
  checks: LlmCheckResult[];
  recommendedAction?: "proceed" | "review" | "reject";
  pWinAdjustment?: number;
  compsExcluded?: string[];
  summary?: string;
  costUsd?: number;
  cached?: boolean;
  escalated?: boolean;
  error?: string;
}

export type DecidedBy = "rules" | "llm" | `human:${string}`;

export interface QualifyResult {
  caseId: string;
  parcelId: string;
  jurisdictionId: string;
  address: string;
  status: Status;
  reasonCodes: string[];
  flags: string[];
  summary: string;
  stageLog: StageLogEntry[];
  valuation?: Valuation;
  economics?: Economics;
  route?: RoutePick;
  priority: number;
  releaseDate: string | null;
  requalifyOn: string | null;
  llm?: LlmReview;
  audit: {
    configVersion: string;
    inputHash: string;
    decidedAt: string;
    decidedBy: DecidedBy;
    review?: { by: string; action: string; note?: string; at: string };
  };
}
