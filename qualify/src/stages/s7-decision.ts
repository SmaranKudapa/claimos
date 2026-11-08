/**
 * S7 · Decision & ranking — final status, priority, and a one-line summary.
 *
 * Decision table (first match wins):
 *   1. any I_ code                    → INCOMPLETE
 *   2. any S_/E_/V_/C_ code           → REJECTED
 *   3. T_ code (no feasible route)    → NEXT_CYCLE
 *   4. any F_ flag, any forced review,
 *      or high value while desk is new → NEEDS_REVIEW
 *   5. everything else                → QUALIFIED
 */
import { log, type Draft } from "../draft.js";
import { statusForCode } from "../codes.js";
import type { Status } from "../types.js";
import { money, pct, round } from "../util.js";

const LLM_FLAGS = new Set(["F_LLM_CONCERN", "F_LLM_FAIL", "F_LLM_COMPS_FAVORABLE"]);

export function decide(d: Draft): Status {
  const order: Status[] = ["INCOMPLETE", "REJECTED", "NEXT_CYCLE"];
  for (const s of order) if (d.codes.some((c) => statusForCode(c) === s)) return s;

  const highValue = !!d.economics && d.economics.annualSavings >= d.cfg.thresholds.highValueReviewThreshold;
  if (highValue && d.cfg.thresholds.reviewHighValue) d.flags.add("F_HIGH_VALUE");

  if (d.flags.size > 0 || d.forceReview.length > 0) {
    const ruleCauses = [...d.flags].filter((f) => !LLM_FLAGS.has(f));
    const llmOnly = ruleCauses.length === 0 && d.forceReview.every((r) => r.startsWith("LLM"));
    d.decidedBy = llmOnly ? "llm" : "rules";
    log(d, "S7", "pass", `NEEDS_REVIEW: ${[...d.flags, ...d.forceReview].join(", ")}`);
    return "NEEDS_REVIEW";
  }
  log(d, "S7", "pass", "QUALIFIED");
  return "QUALIFIED";
}

/** priority = EV × urgency × confidence factor (0.5–1.0). */
export function priority(d: Draft): number {
  if (!d.economics || !d.route || !d.valuation) return 0;
  return round(d.economics.ev * d.route.urgency * (0.5 + 0.5 * d.valuation.confidence), 2);
}

export function summarize(d: Draft, status: Status): string {
  const v = d.valuation;
  const e = d.economics;
  const lastStop = [...d.stageLog].reverse().find((s) => s.outcome === "stop");
  switch (status) {
    case "INCOMPLETE":
      return `Needs more data: ${lastStop?.detail ?? d.codes.join(", ")}.`;
    case "REJECTED":
      return `Not pursuing: ${lastStop?.detail ?? d.codes.join(", ")}.`;
    case "NEXT_CYCLE":
      return `Good claim, no window open: ${lastStop?.detail ?? ""}.`;
    default: {
      const base = v && e
        ? `Assessed ${money(d.cand.assessment.assessedValue)} vs cautious ${money(v.target)} (${pct(v.gapPct)} over, ${v.basis.replace("_", " ")}); ~${money(e.annualSavings)}/yr savings, EV ${money(e.ev)}`
        : "";
      const route = d.route ? `; file via ${d.route.name} by ${d.route.deadline}` : "";
      const review = status === "NEEDS_REVIEW" ? ` Review: ${[...d.flags, ...d.forceReview].join(", ")}.` : "";
      return `${base}${route}.${review}`;
    }
  }
}
