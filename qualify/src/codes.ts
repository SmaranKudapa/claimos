/**
 * Reason codes and flags. The prefix decides the status (see S7):
 *   I_ → INCOMPLETE · S_/E_/V_/C_ → REJECTED · T_ → NEXT_CYCLE · F_ → NEEDS_REVIEW
 */
export const CODES = {
  // Incomplete data → back to Find
  I_SCHEMA: "Record doesn't match the candidate schema",
  I_MISSING: "Required fields are missing",
  I_INVALID: "Values fail sanity checks",
  I_STALE: "Data is out of date or for a different valuation date",
  I_OWNER: "Owner can't be identified (no name or mailing address)",
  I_NO_COMPS: "Comparable sales were never fetched",

  // Suppressed
  S_DNC: "On the do-not-contact list",
  S_EXISTING_CASE: "Already a client or an open case exists",
  S_COOLDOWN: "Owner declined recently",
  S_CACHED: "Rejected recently with identical inputs",
  S_REPRESENTED: "Owner is represented by another agent",
  S_EXEMPT_OWNER: "Government or tax-exempt owner",

  // Ineligible
  E_NO_DESK: "No active desk config for this jurisdiction",
  E_TYPE: "Property type not handled by this desk",
  E_ALREADY_FILED: "An appeal is already on file this cycle",
  E_EXEMPT: "Fully exempt from value-based tax",

  // Valuation
  V_INSUFFICIENT_COMPS: "Too few usable comparable sales",
  V_NO_GAP: "Assessed value is at or below the conservative market estimate",
  V_GAP_SMALL: "Overassessment is below the minimum gap",
  V_LOW_CONFIDENCE: "Value estimate is too uncertain",

  // Economics
  C_SAVINGS_LOW: "Annual savings below the minimum",
  C_EV_LOW: "Expected value below the minimum",

  // Timing
  T_NO_ROUTE: "No filing route open with enough time left",

  // Review flags
  F_COMPLEX_OWNER: "Trust, entity, estate, or multiple owners",
  F_RECENT_TRANSFER: "Arm's-length sale near the valuation date",
  F_VALUE_CHANGE: "New construction or major permit since the last valuation",
  F_LOW_CONFIDENCE: "Low-confidence estimate on a high-value lead",
  F_HIGH_VALUE: "High-value lead while the desk is new",
  F_LLM_CONCERN: "LLM review raised a concern",
  F_LLM_FAIL: "LLM review failed a check or recommended rejection",
  F_LLM_COMPS_FAVORABLE: "LLM comp exclusions would raise the claim; human must confirm",
  F_LLM_UNAVAILABLE: "LLM review could not run",

  // Human review
  H_REJECTED: "Rejected by a reviewer",
} as const;

export type Code = keyof typeof CODES;

export function statusForCode(code: string): "INCOMPLETE" | "REJECTED" | "NEXT_CYCLE" | null {
  if (code.startsWith("I_")) return "INCOMPLETE";
  if (/^(S|E|V|C|H)_/.test(code)) return "REJECTED";
  if (code.startsWith("T_")) return "NEXT_CYCLE";
  return null;
}
