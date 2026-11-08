/**
 * Quote check: every fact a reader extracts must quote the letter. A fact whose quote is not in
 * the letter (ignoring case and extra whitespace) is dropped. A dropped outcome becomes "unclear".
 */
import type { DecisionReading } from "../types.js";

const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();

export function quoteInLetter(quote: string, letter: string): boolean {
  const q = norm(quote);
  return q.length > 0 && norm(letter).includes(q);
}

export function verifyQuotes(r: DecisionReading, letter: string): { reading: DecisionReading; dropped: string[] } {
  const ok = new Set(r.evidence.filter((e) => quoteInLetter(e.quote, letter)).map((e) => e.field));
  const dropped: string[] = [];
  const keep = (field: string) => {
    if (ok.has(field)) return true;
    dropped.push(field);
    return false;
  };
  const out: DecisionReading = {
    outcome: r.outcome === "unclear" || keep("outcome") ? r.outcome : "unclear",
    reasonCategories: r.reasonCategories.filter((k) => keep(`reasonCategories.${k}`)),
    confidence: r.confidence,
    evidence: r.evidence.filter((e) => ok.has(e.field)),
  };
  if (r.newAssessedValue !== undefined && keep("newAssessedValue")) out.newAssessedValue = r.newAssessedValue;
  if (r.decisionDate !== undefined && keep("decisionDate")) out.decisionDate = r.decisionDate;
  if (r.proceduralReason !== undefined && keep("proceduralReason")) out.proceduralReason = r.proceduralReason;
  if (r.hearingDate !== undefined && keep("hearingDate")) out.hearingDate = r.hearingDate;
  if (r.statedNextStep?.deadline !== undefined && keep("statedNextStep.deadline"))
    out.statedNextStep = { ...(r.statedNextStep.name ? { name: r.statedNextStep.name } : {}), deadline: r.statedNextStep.deadline };
  return { reading: out, dropped };
}
