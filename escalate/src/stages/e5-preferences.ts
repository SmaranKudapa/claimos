/** E5 · Owner preferences (partial mode only) — the owner decided at sign-up; never ask mid-process. */
import { log, stop, type Draft } from "../draft.js";
import { round } from "../util.js";

export function preferences(d: Draft): void {
  if (d.mode !== "partial") return log(d, "E5", "skip", "denied mode");
  const threshold = d.c.authorization.escalation?.appealPartialIfRemainingAnnualAbove;
  const annual = d.economics!.annual;
  if (threshold === undefined) {
    d.flags.add("F_DEFAULT_PREFERENCE");
    return stop(d, "E5", "W_PARTIAL_ACCEPTED", "owner set no preference for partial wins; accept");
  }
  if (annual <= threshold) return stop(d, "E5", "W_PARTIAL_ACCEPTED", `remaining $${round(annual)}/yr ≤ owner's threshold $${threshold}/yr`);
  log(d, "E5", "pass", `remaining $${round(annual)}/yr > owner's threshold $${threshold}/yr; appeal the rest`);
}
