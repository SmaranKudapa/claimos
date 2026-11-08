/**
 * Human review queue actions.
 *
 *   approve → NEEDS_REVIEW becomes QUALIFIED (only NEEDS_REVIEW can be approved;
 *             a lead that failed a hard rule never reaches the queue)
 *   reject  → REJECTED with H_REJECTED plus the reviewer's reason code
 *   edit    → exclude comps and/or correct fields, then re-run the pipeline without the LLM;
 *             the case stays in review until someone approves it
 */
import { CODES } from "./codes.js";
import type { QualifyContext } from "./draft.js";
import { qualify } from "./pipeline.js";
import type { QualifyResult } from "./types.js";

export type ReviewAction =
  | { type: "approve"; note?: string }
  | { type: "reject"; code: string; note?: string }
  | { type: "edit"; excludeComps?: string[]; patch?: Record<string, unknown>; note?: string };

export class ReviewError extends Error {}

export async function applyReview(
  result: QualifyResult,
  action: ReviewAction,
  by: string,
  opts: { now?: string; ctx?: QualifyContext; candidate?: unknown } = {},
): Promise<QualifyResult> {
  const at = opts.now ?? new Date().toISOString();
  const stamp = (r: QualifyResult, note?: string): QualifyResult => ({
    ...r,
    audit: { ...r.audit, decidedBy: `human:${by}`, decidedAt: at, review: { by, action: action.type, at, ...(note ? { note } : {}) } },
  });

  switch (action.type) {
    case "approve": {
      if (result.status !== "NEEDS_REVIEW")
        throw new ReviewError(`Only NEEDS_REVIEW cases can be approved (this one is ${result.status}).`);
      return stamp({ ...result, status: "QUALIFIED", releaseDate: null, summary: result.summary.replace(/ Review:.*$/, "") + ` Approved by ${by}.` }, action.note);
    }
    case "reject": {
      if (result.status === "REJECTED") throw new ReviewError("Case is already rejected.");
      if (!(action.code in CODES)) throw new ReviewError(`Unknown reason code ${action.code}.`);
      return stamp(
        { ...result, status: "REJECTED", reasonCodes: ["H_REJECTED", action.code], releaseDate: null, route: undefined, summary: `Rejected by ${by}: ${CODES[action.code as keyof typeof CODES]}.` },
        action.note,
      );
    }
    case "edit": {
      if (!opts.ctx || opts.candidate === undefined) throw new ReviewError("Edit needs the original candidate and a context.");
      const patched = deepMerge(opts.candidate, action.patch ?? {});
      const prior = result.valuation?.compsExcluded ?? [];
      const rerun = await qualify(patched, opts.ctx, { excludeComps: [...prior, ...(action.excludeComps ?? [])], skipLlm: true, now: at });
      // Stay in the queue unless the edit itself stops the lead.
      const status = rerun.status === "QUALIFIED" ? "NEEDS_REVIEW" : rerun.status;
      const summary = status === "NEEDS_REVIEW" ? `${rerun.summary.replace(/ Review:.*$/, "")} Edited by ${by}; awaiting approval.` : rerun.summary;
      return stamp({ ...rerun, status, summary }, action.note);
    }
  }
}

function deepMerge(base: unknown, patch: Record<string, unknown>): unknown {
  if (!base || typeof base !== "object" || Array.isArray(base)) return patch;
  const out: Record<string, unknown> = { ...(base as Record<string, unknown>) };
  for (const [k, v] of Object.entries(patch)) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) ? deepMerge(out[k], v as Record<string, unknown>) : v;
  }
  return out;
}
