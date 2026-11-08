/** E0 · Intake — is this letter for this case, at this level, with text to read? */
import { coversJurisdiction, rungById } from "../config.js";
import { log, stop, type Draft } from "../draft.js";

export function intake(d: Draft): void {
  const { c, d: dec, ctx } = d;
  if (!coversJurisdiction(ctx.config, c.jurisdictionId))
    return stop(d, "E0", "I_WRONG_DESK", `case jurisdiction ${c.jurisdictionId} is not covered by desk ${ctx.config.jurisdictionId}`);
  if (dec.caseId !== c.caseId) return stop(d, "E0", "I_CASE_MISMATCH", `letter is for ${dec.caseId}, case is ${c.caseId}`);
  const sameLevel = dec.level === c.currentLevel || (rungById(ctx.config, dec.level)?.id ?? dec.level) === (rungById(ctx.config, c.currentLevel)?.id ?? c.currentLevel);
  if (!sameLevel) return stop(d, "E0", "I_LEVEL_MISMATCH", `letter answers ${dec.level}, case is at ${c.currentLevel}`);
  if (!dec.text.trim()) return stop(d, "E0", "I_NO_DECISION_TEXT", "the letter has no text");
  if (c.authorizationSource === "desk_default") d.flags.add("F_DEFAULT_AUTHORIZATION");
  log(d, "E0", "pass", `letter ${dec.decisionId} received ${dec.receivedOn} by ${dec.channel}`);
}
