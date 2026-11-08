/**
 * Escalate pipeline: E0 intake → E1 read → E2 route → E3 next level → E4 economics →
 * E5 owner preferences → E6 evidence plan (+ daily budget across the batch) → E7 decision.
 * Every result is final for this run and executed by the next agent; nothing waits for a person.
 */
import { stop, type Draft, type EscalateContext } from "./draft.js";
import { CountyDecisionSchema, EscalateCaseSchema, type CountyDecision, type EscalateCase, type EscalateResult } from "./types.js";
import { intake } from "./stages/e0-intake.js";
import { readDecision } from "./stages/e1-read.js";
import { route } from "./stages/e2-route.js";
import { nextLevel } from "./stages/e3-next-level.js";
import { economics } from "./stages/e4-economics.js";
import { preferences } from "./stages/e5-preferences.js";
import { evidencePlan } from "./stages/e6-evidence.js";
import { decide } from "./stages/e7-decision.js";
import { addDays, sha256, stableStringify } from "./util.js";

export interface Delivery {
  /** The case as Chase delivers it. */
  case: unknown;
  /** The county's decision letter. */
  decision: unknown;
}

function newDraft(ctx: EscalateContext, c: EscalateCase, d: CountyDecision): Draft {
  return {
    ctx,
    c,
    d,
    codes: [],
    flags: new Set(),
    log: [],
    stopped: false,
    inputHash: sha256(stableStringify({ case: c, decision: d })),
    reading: { verified: null, droppedFields: [], readers: [], models: [], costUsd: 0, cached: false, secondRead: false },
    facts: null,
    mode: null,
    currentValue: c.assessedValue,
    next: null,
    economics: null,
    evidenceRequests: [],
    requeueOn: null,
    readState: null,
  };
}

/** Stages E0–E6 for one case (budget is applied across the batch afterwards). */
async function runStages(dr: Draft): Promise<void> {
  intake(dr);
  if (dr.stopped) return;
  await readDecision(dr);
  if (dr.stopped) return;
  for (const stage of [route, nextLevel, economics, preferences, evidencePlan]) {
    stage(dr);
    if (dr.stopped) return;
  }
}

function invalidResult(ctx: EscalateContext, raw: Delivery, detail: string): EscalateResult {
  const get = (o: unknown, k: string) => (o && typeof o === "object" ? String((o as Record<string, unknown>)[k] ?? "unknown") : "unknown");
  return {
    caseId: get(raw.case, "caseId"),
    parcelId: get(raw.case, "parcelId"),
    jurisdictionId: get(raw.case, "jurisdictionId"),
    address: get(raw.case, "address"),
    decisionId: get(raw.decision, "decisionId"),
    status: "INCOMPLETE",
    reasonCodes: ["I_SCHEMA"],
    flags: [],
    summary: `INCOMPLETE · I_SCHEMA · ${detail}`,
    reading: { verified: null, droppedFields: [], readers: [], models: [], costUsd: 0, cached: false, secondRead: false },
    nextLevel: null,
    economics: null,
    evidenceRequests: [],
    requeueOn: null,
    readState: null,
    ownerUpdate: null,
    stageLog: [{ stage: "E0", outcome: "stop", detail: `I_SCHEMA: ${detail}` }],
    audit: { configVersion: ctx.config.version, inputHash: sha256(stableStringify(raw)), decidedAt: new Date().toISOString(), decidedBy: "escalate-rules" },
  };
}

function finish(dr: Draft): EscalateResult {
  const { status, summary, ownerUpdate } = decide(dr);
  const n = dr.next;
  return {
    caseId: dr.c.caseId,
    parcelId: dr.c.parcelId,
    jurisdictionId: dr.c.jurisdictionId,
    address: dr.c.address,
    decisionId: dr.d.decisionId,
    status,
    reasonCodes: dr.codes,
    flags: [...dr.flags].sort(),
    summary,
    reading: { ...dr.reading, verified: dr.facts ?? dr.reading.verified },
    nextLevel:
      n && (status === "ESCALATE" || status === "PENDING")
        ? { id: n.rung.id, name: n.rung.name, formId: n.rung.formId, deadline: n.deadline, daysLeft: n.daysLeft, filingFee: n.rung.filingFee, hearing: n.rung.hearing, fastTrack: n.fastTrack }
        : null,
    economics: dr.economics,
    evidenceRequests: status === "ESCALATE" || status === "PENDING" ? dr.evidenceRequests : [],
    requeueOn: status === "PENDING" ? dr.requeueOn : null,
    readState: status === "PENDING" ? dr.readState : null,
    ownerUpdate,
    stageLog: dr.log,
    audit: { configVersion: dr.ctx.config.version, inputHash: dr.inputHash, decidedAt: new Date().toISOString(), decidedBy: "escalate-rules" },
  };
}

/**
 * Process a batch of deliveries. Decisions are deduped by decisionId (last one wins). Escalations
 * are funded in descending EV order within the day's filing-fee budget.
 */
export async function escalateAll(deliveries: Delivery[], ctx: EscalateContext): Promise<EscalateResult[]> {
  const byDecision = new Map<string, Delivery>();
  const invalid: EscalateResult[] = [];
  for (const dl of deliveries) {
    const id = (dl.decision as { decisionId?: unknown })?.decisionId;
    if (typeof id === "string" && id) byDecision.set(id, dl);
    else invalid.push(invalidResult(ctx, dl, "decision has no decisionId"));
  }

  const drafts: Draft[] = [];
  for (const dl of byDecision.values()) {
    const c = EscalateCaseSchema.safeParse(dl.case);
    const d = CountyDecisionSchema.safeParse(dl.decision);
    if (!c.success || !d.success) {
      const issues = [...(c.success ? [] : c.error.issues.map((i) => `case.${i.path.join(".")}: ${i.message}`)), ...(d.success ? [] : d.error.issues.map((i) => `decision.${i.path.join(".")}: ${i.message}`))];
      invalid.push(invalidResult(ctx, dl, issues.slice(0, 3).join("; ")));
      continue;
    }
    const dr = newDraft(ctx, c.data, d.data);
    await runStages(dr);
    drafts.push(dr);
  }

  // E6 · daily filing-fee budget: best expected value first.
  const max = ctx.config.budget.maxFilingFeesPerDayUsd;
  let spent = 0;
  const escalating = drafts.filter((dr) => !dr.stopped && dr.next).sort((a, b) => (b.economics?.ev ?? 0) - (a.economics?.ev ?? 0) || a.c.caseId.localeCompare(b.c.caseId));
  for (const dr of escalating) {
    const fee = dr.next!.rung.filingFee;
    if (spent + fee <= max) {
      spent += fee;
      continue;
    }
    if (dr.next!.daysLeft - 1 >= dr.next!.rung.fastTrackDays) {
      dr.requeueOn = addDays(ctx.today, 1);
      stop(dr, "E6", "P_BUDGET", `today's filing fees would reach $${spent + fee} > $${max}; escalate ${dr.requeueOn}`);
    } else stop(dr, "E6", "C_BUDGET", `today's filing fees would reach $${spent + fee} > $${max} and waiting a day misses the deadline`);
  }

  return [...drafts.map(finish), ...invalid];
}

/** One case and one letter. */
export async function escalate(c: unknown, decision: unknown, ctx: EscalateContext): Promise<EscalateResult> {
  const [r] = await escalateAll([{ case: c, decision }], ctx);
  return r!;
}
