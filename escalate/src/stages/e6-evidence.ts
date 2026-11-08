/** E6 · Evidence plan — what the Evidence step should add before the next filing. (Budget: pipeline.) */
import { log, type Draft } from "../draft.js";
import { reasonKeys } from "./e4-economics.js";

const WHY: Record<string, string> = {
  fresh_comps: "The county rejected the comparable sales, so newer and closer sales are needed.",
  owner_photos: "Photos from the owner can show the property's real condition.",
  condition_report: "A condition report backs up claims about the property's state.",
  repair_estimates: "Repair estimates show what the condition problems would cost to fix.",
  missing_form: "The county said a required form was missing; it must be completed and attached.",
  missing_signature: "The county said the filing was not signed; it needs the owner's or agent's signature.",
  missing_authorization: "The county said the authorization was missing; the signed authorization must be attached.",
};

export function evidenceWhy(key: string): string {
  return WHY[key] ?? `The county's decision points to a missing item (${key.replace(/_/g, " ")}); it must be supplied before refiling.`;
}

export function evidencePlan(d: Draft): void {
  const keys = [...new Set(reasonKeys(d).flatMap((k) => d.ctx.config.denialReasons[k]!.evidence))];
  d.evidenceRequests = keys.map((key) => ({ key, why: evidenceWhy(key), forStep: "evidence" }));
  log(d, "E6", "pass", keys.length ? `evidence to add: ${keys.join(", ")}` : "no new evidence named");
}
