/**
 * Offline reviewers for demos and tests. Neither calls a network.
 *
 * HeuristicReviewer — a rule-of-thumb stand-in for the real model, so the whole pipeline
 *   (including comp exclusion and review routing) can be demoed without an API key.
 * ScriptedReviewer — returns canned replies in order; tests use it to drive every merge rule.
 */
import type { LlmClient, LlmRequest, LlmResponse } from "./client.js";
import type { Packet } from "./prompt.js";

export function packetFromPrompt(user: string): Packet {
  const start = user.indexOf("{");
  const end = user.indexOf("\nSource documents");
  return JSON.parse(user.slice(start, end > 0 ? end : undefined).trim());
}

export class HeuristicReviewer implements LlmClient {
  readonly name = "heuristic-mock";
  async complete(req: LlmRequest): Promise<LlmResponse> {
    const p = packetFromPrompt(req.user);
    const flags = new Set(p.result.flags);
    const docs = [...req.user.matchAll(/<source_document ref="([^"]+)"[^>]*>([\s\S]*?)<\/source_document>/g)].map((m) => ({ ref: m[1]!, text: m[2]! }));
    const checks: { id: string; verdict: "pass" | "concern" | "fail"; evidence: string[]; note: string }[] = [];
    let adj = 0;

    checks.push({ id: "C1", verdict: "pass", evidence: ["subject.assessment.assessedValue"], note: "Fields are consistent." });

    const ivs = p.comps.map((c) => c.impliedValue).sort((a, b) => a - b);
    const med = ivs[Math.floor(ivs.length / 2)] ?? 0;
    const outliers = p.comps.filter((c) => med > 0 && Math.abs(c.impliedValue - med) / med > 0.25).map((c) => c.compId!);
    checks.push(
      outliers.length
        ? { id: "C2", verdict: "concern", evidence: outliers.map((id) => `comp:${id}`), note: `Outlier comp(s) far from the median: ${outliers.join(", ")}.` }
        : { id: "C2", verdict: "pass", evidence: p.comps[0] ? [`comp:${p.comps[0].compId}`] : ["result.valuation.estimate"], note: "Comps look comparable." },
    );

    const reno = docs.find((d) => /renovat|addition|remodel/i.test(d.text));
    if (flags.has("F_VALUE_CHANGE") || reno)
      checks.push({
        id: "C3",
        verdict: "concern",
        evidence: reno ? [`doc:${reno.ref}`] : ["subject.physical.yearBuilt"],
        note: "Possible value change since the last valuation.",
      });
    else checks.push({ id: "C3", verdict: "pass", evidence: ["subject.physical"], note: "No sign of unrecorded changes." });

    const t = p.subject.transfer;
    if (t && t.armsLength && t.price <= p.result.valuation.target) {
      checks.push({ id: "C4", verdict: "fail", evidence: ["subject.transfer.price", "result.valuation.target"], note: "Recent sale price is at or below our target; the claim is weak." });
      adj = -0.3;
    } else if (flags.has("F_RECENT_TRANSFER")) {
      checks.push({ id: "C4", verdict: "concern", evidence: ["subject.transfer.price"], note: "Recent sale is strong evidence of value." });
      adj = -0.1;
    } else checks.push({ id: "C4", verdict: "pass", evidence: ["subject.transfer"], note: "No recent sale undercuts the claim." });

    checks.push(
      flags.has("F_COMPLEX_OWNER")
        ? { id: "C5", verdict: "concern", evidence: ["subject.owner.type"], note: "Signer may need trust or entity documents." }
        : { id: "C5", verdict: "pass", evidence: ["subject.owner.type"], note: "Single individual owner." },
    );
    checks.push({ id: "C6", verdict: "pass", evidence: ["result.valuation.basis"], note: "Chosen basis is supported." });
    checks.push({ id: "C7", verdict: "pass", evidence: ["result.economics.ev"], note: "Nothing embarrassing found." });

    const action = checks.some((c) => c.verdict === "fail") ? "reject" : checks.some((c) => c.verdict === "concern") ? "review" : "proceed";
    const input = {
      checks,
      recommended_action: action,
      comps_to_exclude: outliers,
      p_win_adjustment: adj,
      summary: action === "proceed" ? "Checks pass; comps and data support the claim." : `Flagged: ${checks.filter((c) => c.verdict !== "pass").map((c) => c.id).join(", ")}.`,
    };
    return { toolInput: input, text: "", model: req.model, usage: { inputTokens: Math.ceil(req.user.length / 4), outputTokens: 400 } };
  }
}

export class ScriptedReviewer implements LlmClient {
  readonly name = "scripted";
  readonly requests: LlmRequest[] = [];
  constructor(private replies: (unknown | Error | { text: string })[]) {}
  async complete(req: LlmRequest): Promise<LlmResponse> {
    this.requests.push(req);
    const next = this.replies.shift();
    if (next instanceof Error) throw next;
    if (next && typeof next === "object" && "text" in next && typeof (next as { text: unknown }).text === "string")
      return { text: (next as { text: string }).text, model: req.model, usage: { inputTokens: 1000, outputTokens: 300 } };
    return { toolInput: next, text: "", model: req.model, usage: { inputTokens: 1000, outputTokens: 300 } };
  }
}
