/**
 * S6 · LLM review — did the rules miss anything a careful analyst would catch?
 *
 * The one-way rule: the LLM can only keep a lead's status or move it toward more caution.
 * It never runs on stopped leads, never removes a flag, and never rejects a lead on its own
 * (anything that would stop the lead becomes NEEDS_REVIEW for a human to confirm).
 */
import { log, type Draft, type QualifyContext } from "../draft.js";
import type { LlmCheckResult, LlmReview } from "../types.js";
import { clamp, round, sha256, stableStringify } from "../util.js";
import type { LlmRequest } from "../llm/client.js";
import {
  LlmOutputSchema,
  TOOL_NAME,
  TOOL_SCHEMA,
  buildPacket,
  extractJson,
  isValidRef,
  systemPrompt,
  userPrompt,
  type LlmOutput,
} from "../llm/prompt.js";

export const P_WIN_ADJ_MIN = -0.3;
export const P_WIN_ADJ_MAX = 0.05;

interface CachedReview {
  output: LlmOutput;
  model: string;
  costUsd: number;
  escalated: boolean;
}

export async function llmReview(d: Draft, ctx: QualifyContext, rerunS3toS5: (d: Draft) => void): Promise<void> {
  const cfg = d.cfg.llm;
  const econ = d.economics!;
  const highValue = econ.annualSavings >= d.cfg.thresholds.highValueReviewThreshold;

  // ── When it runs ──────────────────────────────────────────────────────────
  if (!cfg.enabled) return skip(d, "disabled in desk config");
  if (!ctx.llm) return skip(d, "no LLM client (run without --no-llm to enable)");
  const model = ctx.models?.primary ?? cfg.model;
  if (!model) return unavailable(d, "no model configured (set QUALIFY_MODEL or llm.model)");
  if (d.flags.size === 0 && !highValue && econ.ev < cfg.minEvToReview)
    return skip(d, `EV ${econ.ev} below ${cfg.minEvToReview} and no flags`);

  const packet = buildPacket(d);
  const docRefs = new Set(d.cand.provenance.rawDocs.map((r) => r.ref));
  const system = systemPrompt();
  const cacheKey = sha256([model, cfg.promptVersion, stableStringify(packet), stableStringify(d.cand.provenance.rawDocs)].join("|"));

  // ── Call (cached) ─────────────────────────────────────────────────────────
  let review: CachedReview;
  const cached = ctx.llmCache?.get(cacheKey) as CachedReview | undefined;
  if (cached) {
    review = cached;
  } else {
    const estCost = estimateCost(d, system + userPrompt(d, packet), cfg.maxTokens);
    if (estCost > cfg.maxCostPerLeadUsd)
      return unavailable(d, `estimated cost $${estCost.toFixed(4)} exceeds cap $${cfg.maxCostPerLeadUsd}`);

    let cost = 0;
    const run = async (m: string): Promise<LlmOutput> => {
      let lastErr = "";
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const req: LlmRequest = {
            model: m,
            system,
            user: userPrompt(d, packet, attempt > 0 ? lastErr : undefined),
            tool: { name: TOOL_NAME, description: "Submit the completed C1–C7 review.", input_schema: TOOL_SCHEMA },
            maxTokens: cfg.maxTokens,
            window: cfg.window,
          };
          const res = await ctx.llm!.complete(req);
          cost += (res.usage.inputTokens * cfg.priceUsdPerMTokIn + res.usage.outputTokens * cfg.priceUsdPerMTokOut) / 1e6;
          const raw = res.toolInput ?? extractJson(res.text);
          const parsed = LlmOutputSchema.safeParse(raw);
          if (parsed.success) return parsed.data;
          lastErr = parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ");
        } catch (e) {
          lastErr = e instanceof Error ? e.message : String(e);
        }
      }
      throw new Error(lastErr || "invalid reply");
    };

    try {
      let output = await run(model);
      let usedModel = model;
      let escalated = false;
      const esc = ctx.models?.escalation ?? cfg.escalationModel;
      const worried = output.recommended_action !== "proceed" || output.checks.some((c) => c.verdict !== "pass");
      if (esc && esc !== model && highValue && worried) {
        output = await run(esc);
        usedModel = esc;
        escalated = true;
      }
      review = { output, model: usedModel, costUsd: round(cost, 5), escalated };
      ctx.llmCache?.set(cacheKey, review);
    } catch (e) {
      return unavailable(d, `LLM reply invalid after retry: ${e instanceof Error ? e.message : e}`, round(cost, 5));
    }
  }

  // ── Merge with the rules ──────────────────────────────────────────────────
  const out = review.output;
  const checks: LlmCheckResult[] = out.checks.map((c) => ({
    id: c.id,
    verdict: c.verdict,
    evidence: c.evidence,
    note: c.note,
    counted: c.evidence.some((ref) => isValidRef(ref, packet, docRefs)),
  }));
  const usedIds = new Set(d.valuation!.compsUsed.map((s) => s.compId));
  const exclude = [...new Set(out.comps_to_exclude)].filter((id) => usedIds.has(id));
  const adj = clamp(out.p_win_adjustment, P_WIN_ADJ_MIN, P_WIN_ADJ_MAX);

  d.llm = {
    ran: true,
    model: review.model,
    promptVersion: cfg.promptVersion,
    checks,
    recommendedAction: out.recommended_action,
    pWinAdjustment: adj,
    compsExcluded: exclude,
    summary: out.summary,
    costUsd: review.costUsd,
    cached: !!cached,
    escalated: review.escalated,
  };

  const notes: string[] = [];

  // Comp exclusions and p(win) adjustment: re-run S3–S5 once, deterministically, on a copy.
  if (exclude.length || adj !== 0) {
    const trial = structuredClone(d);
    exclude.forEach((id) => trial.excludedComps.add(id));
    trial.pWinAdjustment = adj;
    trial.stageLog = [];
    rerunS3toS5(trial);
    if (trial.stopped) {
      d.flags.add("F_LLM_FAIL");
      notes.push(`LLM changes would stop this lead (${trial.codes.at(-1)}); human to confirm`);
    } else if (trial.economics!.ev > d.economics!.ev + 1e-6) {
      if (exclude.length) {
        d.flags.add("F_LLM_COMPS_FAVORABLE");
        notes.push(`excluding ${exclude.join(", ")} would raise EV ${d.economics!.ev} → ${trial.economics!.ev}; kept original numbers`);
      } else {
        // A small positive adjustment is allowed by design; adopt it (status is unchanged).
        adopt(d, trial);
        notes.push(`p(win) adjusted ${adj >= 0 ? "+" : ""}${adj}`);
      }
    } else {
      adopt(d, trial);
      exclude.forEach((id) => d.excludedComps.add(id));
      if (exclude.length) notes.push(`excluded comps ${exclude.join(", ")}`);
      if (adj !== 0) notes.push(`p(win) adjusted ${adj}`);
    }
  }

  const counted = checks.filter((c) => c.counted);
  if (counted.some((c) => c.verdict === "concern")) d.flags.add("F_LLM_CONCERN");
  if (counted.some((c) => c.verdict === "fail") || out.recommended_action === "reject") d.flags.add("F_LLM_FAIL");
  if (out.recommended_action === "review") d.forceReview.push("LLM recommended review");
  const ignored = checks.filter((c) => !c.counted && c.verdict !== "pass").length;
  if (ignored) notes.push(`${ignored} uncited verdict(s) ignored`);

  log(d, "S6", "pass", [`${out.recommended_action}${review.escalated ? " (escalated)" : ""}${cached ? " (cached)" : ""}`, ...notes].join(" · "));
}

function adopt(d: Draft, trial: Draft) {
  d.valuation = trial.valuation;
  d.economics = trial.economics;
  d.route = trial.route;
  d.pWinAdjustment = trial.pWinAdjustment;
}

function skip(d: Draft, reason: string) {
  d.llm = { ran: false, skippedReason: reason, checks: [] } satisfies LlmReview;
  log(d, "S6", "skip", reason);
}

function unavailable(d: Draft, reason: string, costUsd?: number) {
  d.llm = { ran: false, error: reason, checks: [], ...(costUsd !== undefined ? { costUsd } : {}) };
  d.flags.add("F_LLM_UNAVAILABLE");
  log(d, "S6", "skip", reason);
}

function estimateCost(d: Draft, prompt: string, maxTokens: number) {
  const c = d.cfg.llm;
  return ((prompt.length / 4) * c.priceUsdPerMTokIn + maxTokens * c.priceUsdPerMTokOut) / 1e6;
}
