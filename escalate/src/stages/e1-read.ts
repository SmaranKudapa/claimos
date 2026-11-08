/**
 * E1 · Read the decision. A reader pulls facts out of the letter; code checks every quote, lets
 * verified numbers override wording, gets an automatic second read when unsure, and resolves a
 * letter that stays unclear without a person: ask Chase to clarify while there is time, otherwise
 * treat it as a denial and let the economics decide.
 */
import { rungById } from "../config.js";
import { log, stop, type Draft } from "../draft.js";
import { ReaderError } from "../reader/types.js";
import { verifyQuotes } from "../reader/verify-quotes.js";
import type { DecisionReading, Outcome } from "../types.js";
import { addDays, daysBetween, minDate } from "../util.js";

interface Interpreted {
  facts: DecisionReading;
  conflict: boolean;
}

/** Numbers beat labels: a verified new value decides the outcome. */
export function interpret(r: DecisionReading, assessed: number, target: number): Interpreted {
  const facts: DecisionReading = { ...r, reasonCategories: [...r.reasonCategories], evidence: [...r.evidence] };
  let conflict = false;
  const numeric: Outcome[] = ["full_win", "partial_reduction", "denied", "unclear"];
  if (facts.newAssessedValue !== undefined && numeric.includes(facts.outcome)) {
    const nv = facts.newAssessedValue;
    const computed: Outcome = nv <= target ? "full_win" : nv < assessed ? "partial_reduction" : "denied";
    if (facts.outcome !== "unclear" && facts.outcome !== computed) conflict = true;
    facts.outcome = computed;
    facts.confidence = Math.max(facts.confidence, 0.9);
  }
  return { facts, conflict };
}

export async function readDecision(d: Draft): Promise<void> {
  const { ctx, c, d: dec } = d;
  const cfg = ctx.config;
  const rc = cfg.reader;
  const prior = c.readAttempts.find((x) => x.decisionId === dec.decisionId);
  const attemptsSoFar = prior?.attempts ?? 0;
  const firstPendingOn = prior?.firstPendingOn ?? ctx.today;

  if (!ctx.reader) {
    log(d, "E1", "skip", "no reader (tests only)");
    return unclearFallback(d, firstPendingOn, attemptsSoFar);
  }
  const reader = ctx.reader;
  const primary = ctx.models?.primary ?? rc.model;
  const stronger = ctx.models?.escalation ?? rc.escalationModel ?? primary;

  const attempt = async (model: string | null, secondRead: boolean): Promise<Interpreted> => {
    if (d.reading.costUsd >= rc.maxCostPerCaseUsd) throw new ReaderError(`cost cap $${rc.maxCostPerCaseUsd} reached`);
    const out = await reader.read(dec, c, cfg, { model, secondRead });
    d.reading.costUsd += out.costUsd;
    d.reading.readers.push(reader.name);
    d.reading.models.push(out.model);
    d.reading.cached = d.reading.cached || out.cached;
    if (d.reading.costUsd > rc.maxCostPerCaseUsd) throw new ReaderError(`cost $${d.reading.costUsd.toFixed(4)} over cap $${rc.maxCostPerCaseUsd}`);
    const { reading, dropped } = verifyQuotes(out.reading, dec.text);
    d.reading.droppedFields.push(...dropped.map((f) => (secondRead ? `second:${f}` : f)));
    return interpret(reading, c.assessedValue, c.targetValue);
  };
  const unsure = (x: Interpreted) => x.facts.outcome === "unclear" || x.facts.confidence < rc.minReadConfidence || x.conflict;

  let final: Interpreted;
  try {
    final = await attempt(primary, false);
    if (unsure(final)) {
      d.flags.add("F_SECOND_READ");
      d.reading.secondRead = true;
      const second = await attempt(stronger, true);
      if (!unsure(second)) final = second;
      else if (final.facts.outcome === "unclear" && second.facts.outcome !== "unclear" && second.facts.confidence >= rc.minReadConfidence) final = second;
    }
  } catch (e) {
    if (!(e instanceof ReaderError)) throw e;
    const attempts = attemptsSoFar + 1;
    if (attempts < rc.maxReadAttempts) {
      d.readState = { decisionId: dec.decisionId, attempts, firstPendingOn };
      d.requeueOn = addDays(ctx.today, rc.retryAfterDays);
      return stop(d, "E1", "P_READ_RETRY", `reader failed (${e.message}); attempt ${attempts} of ${rc.maxReadAttempts}, retry ${d.requeueOn}`);
    }
    log(d, "E1", "pass", `reader failed ${attempts} times (${e.message}); applying the unclear-letter rules`);
    return unclearFallback(d, firstPendingOn, attempts);
  }

  if (final.conflict) d.flags.add("F_LABEL_NUMBER_CONFLICT");
  d.reading.verified = final.facts;
  if (final.facts.outcome === "unclear" || final.facts.confidence < rc.minReadConfidence) {
    log(d, "E1", "pass", `letter still unclear after ${d.reading.secondRead ? "a second read" : "one read"}`);
    return unclearFallback(d, firstPendingOn, attemptsSoFar, final.facts);
  }
  d.facts = final.facts;
  log(d, "E1", "pass", `read as ${final.facts.outcome}${final.facts.newAssessedValue ? ` (new value ${final.facts.newAssessedValue})` : ""}, confidence ${final.facts.confidence}`);
}

/**
 * A letter that stays unclear: ask Chase to clarify while the clarification window is open and
 * waiting cannot cost the next level's deadline; otherwise treat it as a denial with reason "other".
 */
function unclearFallback(d: Draft, firstPendingOn: string, attempts: number, partial?: DecisionReading): void {
  const { ctx, c, d: dec } = d;
  const cfg = ctx.config;
  const rc = cfg.reader;
  const clarifyEnd = addDays(firstPendingOn, rc.clarifyMaxDays);
  const cur = rungById(cfg, c.currentLevel);
  const next = cur ? cfg.ladder.find((r) => r.order === cur.order + 1) : undefined;
  const latestUseful = next ? addDays(addDays(dec.receivedOn, next.deadline.days), -(next.workDaysNeeded + next.bufferDays)) : clarifyEnd;
  const requeue = minDate(addDays(ctx.today, rc.retryAfterDays), clarifyEnd);
  if (ctx.today < clarifyEnd && requeue <= latestUseful) {
    d.readState = { decisionId: dec.decisionId, attempts, firstPendingOn };
    d.requeueOn = requeue;
    return stop(d, "E1", "P_CLARIFY", `unclear letter; Chase gets a clearer copy or clarification, check again ${requeue} (window ends ${clarifyEnd}, ${daysBetween(ctx.today, clarifyEnd)}d left)`);
  }
  d.flags.add("F_ASSUMED_DENIAL");
  d.facts = {
    outcome: "denied",
    reasonCategories: ["other"],
    confidence: 0,
    evidence: [],
    ...(partial?.decisionDate ? { decisionDate: partial.decisionDate } : {}),
    ...(partial?.statedNextStep ? { statedNextStep: partial.statedNextStep } : {}),
  };
  log(d, "E1", "pass", `unclear past the cutoff (${ctx.today >= clarifyEnd ? `clarify window ended ${clarifyEnd}` : "waiting would cost the next deadline"}); treated as a denial`);
}
