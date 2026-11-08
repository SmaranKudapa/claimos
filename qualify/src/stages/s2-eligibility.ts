/**
 * S2 · Hard eligibility — can this claim legally be filed by us this cycle?
 * Hard failures stop the lead. Flags never reject; they lower p(win) and force review.
 */
import { stop, log, type Draft } from "../draft.js";
import { daysBetween } from "../util.js";

export function eligibility(d: Draft): void {
  const { cand: c, cfg } = d;
  const j = cfg.jurisdiction;

  if (c.jurisdictionId !== j.id) return stop(d, "S2", "E_NO_DESK", `no desk for ${c.jurisdictionId}`);
  if (!j.supportedPropertyTypes.map((t) => t.toUpperCase()).includes(c.propertyType))
    return stop(d, "S2", "E_TYPE", `${c.propertyType} is outside this desk`);
  if (c.status.appealOnFile) return stop(d, "S2", "E_ALREADY_FILED", "appeal already on file this cycle");
  if (c.assessment.exemptions.some((e) => e.fullyExempt)) return stop(d, "S2", "E_EXEMPT", "fully exempt");
  if (c.owner.names.length === 0 || !c.owner.mailingAddress)
    return stop(d, "S2", "I_OWNER", c.owner.names.length === 0 ? "no owner name" : "no mailing address");

  const notes: string[] = [];

  if (["trust", "entity", "estate"].includes(c.owner.type) || c.owner.names.length > 1) {
    d.flags.add("F_COMPLEX_OWNER");
    notes.push(`owner is ${c.owner.names.length > 1 ? `${c.owner.names.length} people` : c.owner.type}`);
  }

  if (c.transfer?.armsLength && Math.abs(daysBetween(c.transfer.date, j.valuationDate)) <= cfg.thresholds.transferLookbackDays) {
    d.flags.add("F_RECENT_TRANSFER");
    notes.push(`sold ${c.transfer.date}`);
  }

  const valuationYear = Number(j.valuationDate.slice(0, 4));
  const priorValuation = c.assessment.history
    ?.map((h) => h.valuationDate)
    .filter((x) => x < j.valuationDate)
    .sort()
    .at(-1);
  const sinceDate = priorValuation ?? `${valuationYear - 1}${j.valuationDate.slice(4)}`;
  const majorPermit =
    !!c.physical.lastPermitDate &&
    c.physical.lastPermitDate > sinceDate &&
    (j.majorPermitTypes.length === 0 ||
      c.physical.permitTypes.some((p) => j.majorPermitTypes.map((x) => x.toUpperCase()).includes(p.toUpperCase())));
  const newBuild = c.physical.yearBuilt !== undefined && c.physical.yearBuilt >= valuationYear - 1;
  if (majorPermit || newBuild) {
    d.flags.add("F_VALUE_CHANGE");
    notes.push(newBuild ? `built ${c.physical.yearBuilt}` : `permit ${c.physical.lastPermitDate}`);
  }

  log(d, "S2", "pass", notes.length ? `flags: ${notes.join("; ")}` : undefined);
}
