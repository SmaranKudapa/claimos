/**
 * S1 · Suppression — are we allowed to, and should we, pursue this owner?
 * Runs before any paid lookup.
 */
import { stop, log, type Draft, type QualifyContext } from "../draft.js";
import { daysBetween } from "../util.js";

export function suppression(d: Draft, ctx: QualifyContext): void {
  const { cand: c, cfg } = d;
  const s = ctx.suppression;

  // Rejection cache first: identical inputs, rejected recently → reuse the prior answer.
  const prior = ctx.priorResults.get(d.caseId);
  if (
    prior &&
    prior.status === "REJECTED" &&
    prior.audit.inputHash === d.inputHash &&
    prior.audit.configVersion === cfg.version &&
    daysBetween(prior.audit.decidedAt.slice(0, 10), d.today) <= cfg.suppression.rejectionCacheDays
  ) {
    return stop(d, "S1", ["S_CACHED", ...prior.reasonCodes.filter((x) => x !== "S_CACHED")], `same inputs rejected on ${prior.audit.decidedAt.slice(0, 10)}`);
  }

  if (s.dncParcels.includes(c.parcelId) || c.owner.names.some((n) => s.dncOwners.includes(n)))
    return stop(d, "S1", "S_DNC", "parcel or owner is on the do-not-contact list");

  if (c.status.existingCaseId || s.clientParcels.includes(c.parcelId))
    return stop(d, "S1", "S_EXISTING_CASE", c.status.existingCaseId ? `open case ${c.status.existingCaseId}` : "already a client");

  const declined = s.declined
    .filter((x) => x.parcelId === c.parcelId)
    .find((x) => daysBetween(x.date, d.today) <= cfg.suppression.cooldownDays);
  if (declined) return stop(d, "S1", "S_COOLDOWN", `declined on ${declined.date}`);

  if (s.representedParcels.includes(c.parcelId)) return stop(d, "S1", "S_REPRESENTED", "represented by another agent");

  if (c.owner.type === "government") return stop(d, "S1", "S_EXEMPT_OWNER", "government owner");

  log(d, "S1", "pass");
}
