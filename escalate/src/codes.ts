/**
 * Reason codes. The prefix decides the status (precedence I_ > P_ > C_ > W_ > A_); F_ codes are
 * flags and never change it. There is no prefix or status that routes a case to a person.
 */
import type { Status } from "./types.js";

export const CODES = {
  // INCOMPLETE → Chase re-fetches
  I_SCHEMA: "Case or decision does not match the expected shape",
  I_CASE_MISMATCH: "The letter is for a different case",
  I_LEVEL_MISMATCH: "The letter answers a different appeal level than the case is at",
  I_NO_DECISION_TEXT: "The decision letter has no text",
  I_WRONG_DESK: "The case belongs to a jurisdiction this desk config does not cover",
  // PENDING → Chase, at requeueOn
  P_NOT_FINAL: "The county has not decided yet; check again later",
  P_HEARING_SCHEDULED: "A hearing is scheduled; check again the day after",
  P_CLARIFY: "The letter is unclear; Chase gets a clearer copy or asks the county",
  P_READ_RETRY: "Reading the letter failed; retry later",
  P_BUDGET: "Today's filing-fee budget is used up; escalate tomorrow",
  // CLOSED
  C_LADDER_END: "No further appeal level exists",
  C_REFER_OUT: "The next level needs a licensed representative; the owner can continue with one",
  C_NOT_AUTHORIZED: "The owner's authorization does not cover the next level",
  C_DEADLINE_PASSED: "The deadline for the next level has passed",
  C_DEADLINE_TOO_CLOSE: "Too little time left to prepare the next level",
  C_REOPEN_RISK: "The next level could raise the value and the owner did not accept that risk",
  C_SMALL_GAP: "The remaining gap is too small to appeal again",
  C_LOW_PWIN: "The chance of winning at the next level is too low",
  C_LOW_EV: "Appealing again is not worth the cost",
  C_PROCEDURAL_BAR: "Dismissed on a technicality that cannot be fixed",
  C_BUDGET: "Filing-fee budget exceeded and no time to wait",
  C_UNHANDLED: "A situation the rules do not cover; closed conservatively",
  // COLLECT
  W_FULL_WIN: "The county granted the full reduction",
  W_PARTIAL_ACCEPTED: "A partial reduction was granted and is accepted",
  // ESCALATE → Evidence → File
  A_NEXT_LEVEL: "Appeal at the next level",
  A_FAST_TRACK: "Appeal at the next level on a fast track (tight deadline)",
  A_REFILE_SAME_LEVEL: "Fix the technicality and refile at the same level",
  // Flags
  F_VALUE_INCREASED: "The county raised the value",
  F_SECOND_READ: "A stronger model read the letter a second time",
  F_ASSUMED_DENIAL: "The letter stayed unclear past the cutoff and was treated as a denial",
  F_DATE_FROM_RECEIPT: "No decision date in the letter; the received date was used",
  F_DEADLINE_CONFLICT: "The letter's deadline and the computed deadline differ; the earlier one is used",
  F_MISSED_DEADLINE: "A deadline was missed (metric)",
  F_FAST_TRACK: "The deadline is tight; fast-track preparation",
  F_REOPEN_RISK: "The next level could raise the value; the owner accepted that risk",
  F_DEFAULT_PWIN: "No Qualify win probability on file; the desk default was used",
  F_DEFAULT_PREFERENCE: "The owner set no preference for partial wins; the partial win is accepted",
  F_ESCALATION_BLOCKED: "Appealing the rest of a partial win was not possible; the partial win is accepted",
  F_LABEL_NUMBER_CONFLICT: "The letter's wording and its numbers disagreed; the numbers decide",
} as const;
export type Code = keyof typeof CODES;

const PRECEDENCE: [string, Status][] = [
  ["I_", "INCOMPLETE"],
  ["P_", "PENDING"],
  ["C_", "CLOSED"],
  ["W_", "COLLECT"],
  ["A_", "ESCALATE"],
];

/** Status from reason codes. No decisive code means a situation the rules missed: callers add C_UNHANDLED. */
export function statusFor(codes: string[]): Status | null {
  for (const [prefix, status] of PRECEDENCE) if (codes.some((c) => c.startsWith(prefix))) return status;
  return null;
}
