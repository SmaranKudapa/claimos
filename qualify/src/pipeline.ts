/**
 * The Qualify pipeline: S0 → S7, cheapest first. Each stage can stop a lead.
 */
import { caseIdFor, type Draft, type QualifyContext } from "./draft.js";
import { intake, dedupe } from "./stages/s0-intake.js";
import { suppression } from "./stages/s1-suppression.js";
import { eligibility } from "./stages/s2-eligibility.js";
import { valuation } from "./stages/s3-valuation.js";
import { economics } from "./stages/s4-economics.js";
import { timing } from "./stages/s5-timing.js";
import { llmReview } from "./stages/s6-llm.js";
import { decide, priority, summarize } from "./stages/s7-decision.js";
import { STATUS_ORDER, type QualifyResult, type StageLogEntry } from "./types.js";
import { sha256, stableStringify } from "./util.js";

export interface QualifyOptions {
  /** Reviewer edits: comps to leave out. */
  excludeComps?: string[];
  /** Skip S6 (used when a human has already taken over the case). */
  skipLlm?: boolean;
  /** Timestamp for audit.decidedAt (tests pin this). */
  now?: string;
}

export function inputHashFor(normalized: unknown, configVersion: string): string {
  return sha256(configVersion + "|" + stableStringify(normalized));
}

/** Re-run the deterministic middle of the pipeline on a draft (used by S6 and reviewer edits). */
export function runS3toS5(d: Draft): void {
  for (const stage of [valuation, economics, timing]) {
    if (d.stopped) return;
    stage(d);
  }
}

export async function qualify(raw: unknown, ctx: QualifyContext, opts: QualifyOptions = {}): Promise<QualifyResult> {
  const { config: cfg, today } = ctx;
  const now = opts.now ?? new Date().toISOString();

  // S0 · Intake
  const s0 = intake(raw, cfg, today);
  if (!s0.ok) {
    const stageLog: StageLogEntry[] = [{ stage: "S0", outcome: "stop", detail: s0.detail }];
    return {
      caseId: caseIdFor(s0.jurisdictionId, s0.parcelId),
      parcelId: s0.parcelId,
      jurisdictionId: s0.jurisdictionId,
      address: s0.address,
      status: "INCOMPLETE",
      reasonCodes: s0.codes,
      flags: [],
      summary: `Needs more data: ${s0.detail}.`,
      stageLog,
      priority: 0,
      releaseDate: null,
      requalifyOn: null,
      audit: { configVersion: cfg.version, inputHash: inputHashFor(raw, cfg.version), decidedAt: now, decidedBy: "rules" },
    };
  }

  const d: Draft = {
    cand: s0.cand,
    cfg,
    today,
    caseId: caseIdFor(s0.cand.jurisdictionId, s0.cand.parcelId),
    inputHash: inputHashFor(s0.cand, cfg.version),
    flags: new Set(),
    codes: [],
    stageLog: [{ stage: "S0", outcome: "pass", ...(s0.notes.length ? { detail: s0.notes.join("; ") } : {}) }],
    requalifyOn: null,
    excludedComps: new Set(opts.excludeComps ?? []),
    forceReview: [],
    decidedBy: "rules",
    pWinAdjustment: 0,
  };

  // S1–S5 · free/cheap, deterministic
  for (const stage of [() => suppression(d, ctx), () => eligibility(d), () => valuation(d), () => economics(d), () => timing(d)]) {
    if (d.stopped) break;
    stage();
  }

  // S6 · LLM review (only on survivors)
  if (!d.stopped) {
    if (opts.skipLlm) {
      d.llm = { ran: false, skippedReason: "skipped (human review in progress)", checks: [] };
      d.stageLog.push({ stage: "S6", outcome: "skip", detail: "human review in progress" });
    } else {
      await llmReview(d, ctx, runS3toS5);
    }
  }

  // S7 · Decision
  const status = decide(d);
  const result: QualifyResult = {
    caseId: d.caseId,
    parcelId: d.cand.parcelId,
    jurisdictionId: d.cand.jurisdictionId,
    address: d.cand.situsAddress,
    status,
    reasonCodes: d.codes,
    flags: [...d.flags],
    summary: summarize(d, status),
    stageLog: d.stageLog,
    ...(d.valuation ? { valuation: d.valuation } : {}),
    ...(d.economics ? { economics: d.economics } : {}),
    ...(d.route && (status === "QUALIFIED" || status === "NEEDS_REVIEW") ? { route: d.route } : {}),
    priority: status === "QUALIFIED" || status === "NEEDS_REVIEW" ? priority(d) : status === "NEXT_CYCLE" ? d.economics?.ev ?? 0 : 0,
    releaseDate: null,
    requalifyOn: d.requalifyOn,
    ...(d.llm ? { llm: d.llm } : {}),
    audit: { configVersion: cfg.version, inputHash: d.inputHash, decidedAt: now, decidedBy: d.decidedBy },
  };
  return result;
}

export interface RunSummary {
  results: QualifyResult[];
  merged: number;
  counts: Record<string, number>;
  llmCostUsd: number;
}

/**
 * Qualify a batch: dedupe, run each lead, rank, and release the top N QUALIFIED leads
 * to Sign up today (capacity-aware). The rest wait and are re-ranked next run.
 */
export async function qualifyAll(raws: unknown[], ctx: QualifyContext, opts: { concurrency?: number; now?: string } = {}): Promise<RunSummary> {
  const { records, merged } = dedupe(raws);
  const results: QualifyResult[] = new Array(records.length);
  const limit = Math.max(1, opts.concurrency ?? 4);
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.min(limit, records.length) }, async () => {
      while (next < records.length) {
        const i = next++;
        results[i] = await qualify(records[i], ctx, { now: opts.now });
      }
    }),
  );

  results.sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || b.priority - a.priority || a.caseId.localeCompare(b.caseId));
  let released = 0;
  for (const r of results) {
    if (r.status !== "QUALIFIED") continue;
    if (released < ctx.config.capacity.dailyReleaseLimit) {
      r.releaseDate = ctx.today;
      released++;
    }
  }

  const counts: Record<string, number> = {};
  for (const r of results) counts[r.status] = (counts[r.status] ?? 0) + 1;
  const llmCostUsd = results.reduce((s, r) => s + (r.llm?.cached ? 0 : r.llm?.costUsd ?? 0), 0);
  return { results, merged, counts, llmCostUsd };
}
