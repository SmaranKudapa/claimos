/**
 * Owner updates, one template per outcome. Every number comes from a verified field: the case's
 * assessed value, a new value whose quote was found in the letter, or a computed deadline date.
 * Nothing here promises a result. Escalate never sends these; the next agent does, automatically.
 */
import type { Draft } from "./draft.js";
import type { OwnerUpdate, Status } from "./types.js";
import { money } from "./util.js";

const PROCEDURAL_WORDS: Record<string, string> = {
  missing_form: "a required form was missing",
  missing_signature: "the filing was not signed",
  missing_authorization: "the signed authorization was missing",
  late_filing: "it was filed after the deadline",
};

export function ownerUpdate(d: Draft, status: Status, code: string): OwnerUpdate | null {
  if (status === "INCOMPLETE") return null;
  const { c } = d;
  const f = d.facts;
  const nv = f?.newAssessedValue;
  const was = money(c.assessedValue);
  const county = (() => {
    if (!f) return "";
    if (f.outcome === "full_win") return nv ? `The county granted your appeal and lowered your assessed value from ${was} to ${money(nv)}.` : "The county granted your appeal in full.";
    if (f.outcome === "partial_reduction" && nv) return `The county lowered your assessed value from ${was} to ${money(nv)}, less than the reduction we asked for.`;
    if (f.outcome === "denied") {
      if (d.flags.has("F_ASSUMED_DENIAL")) return "The county's letter did not clearly state a decision, and it could not be clarified in time, so we are treating it as a denial.";
      if (nv && nv > c.assessedValue) return `The county did not lower your value; its letter sets it at ${money(nv)}.`;
      return `The county denied your appeal and kept your assessed value at ${was}.`;
    }
    if (f.outcome === "dismissed_procedural") return `The county dismissed the filing because ${PROCEDURAL_WORDS[f.proceduralReason ?? ""] ?? "of a procedural problem"}.`;
    return "";
  })();
  const next = d.next;
  const evidence = d.evidenceRequests.map((r) => r.key.replace(/_/g, " ")).join(", ");
  const reopen = d.flags.has("F_REOPEN_RISK") ? " At this level the value can also go up; you accepted that risk when you signed up." : "";
  const lines: Record<string, [string, string]> = {
    W_FULL_WIN: ["Your appeal was granted", `${county} Next, we confirm the change on your tax bill and then invoice our fee as agreed when you signed up.`],
    W_PARTIAL_ACCEPTED: [
      "Your assessed value was lowered",
      `${county} ${d.flags.has("F_DEFAULT_PREFERENCE") ? "You did not ask us to keep appealing partial wins, so we are accepting this result." : d.flags.has("F_ESCALATION_BLOCKED") ? "Appealing the rest is not possible or not worthwhile here, so we are accepting this result." : "The remaining amount is below the level you set for appealing further, so we are accepting this result."} Next, we confirm the change on your tax bill and invoice our fee as agreed.`,
    ],
    A_NEXT_LEVEL: ["We are appealing at the next level", `${county} We are appealing at the next level (${next?.rung.name}); the filing deadline is ${next?.deadline}.${evidence ? ` First we will add: ${evidence}.` : ""}${reopen}`],
    A_FAST_TRACK: ["We are appealing at the next level (tight deadline)", `${county} We are appealing at the next level (${next?.rung.name}) on a fast track; the filing deadline is ${next?.deadline}.${evidence ? ` First we will add: ${evidence}.` : ""}${reopen}`],
    A_REFILE_SAME_LEVEL: ["We are fixing the filing and refiling", `${county} We are fixing it and refiling by ${next?.deadline}.`],
    C_LADDER_END: ["Your appeal has ended", `${county} There is no further appeal level, so this appeal is closed.`],
    C_REFER_OUT: [
      "Your appeal can continue with a licensed professional",
      `${county} The next step needs a licensed professional, so ClaimOS cannot take it further. You can continue with one if you wish.${d.ctx.config.ladder.find((r) => r.requiresLicensedRep && r.referOutNote)?.referOutNote ? ` ${d.ctx.config.ladder.find((r) => r.requiresLicensedRep && r.referOutNote)!.referOutNote}` : ""}`,
    ],
    C_NOT_AUTHORIZED: ["Your appeal has stopped", `${county} Your authorization does not cover the next appeal level, so we have stopped here.`],
    C_DEADLINE_PASSED: ["Your appeal has ended", `${county} The deadline for the next level has passed, so this appeal is closed.`],
    C_DEADLINE_TOO_CLOSE: ["Your appeal has ended", `${county} There is not enough time left to prepare the next level properly, so this appeal is closed.`],
    C_REOPEN_RISK: ["Your appeal has ended", `${county} At the next level the value could go up, and you did not choose to accept that risk, so we have stopped here.`],
    C_SMALL_GAP: ["Your appeal has ended", `${county} The remaining amount is too small to appeal again, so this appeal is closed.`],
    C_LOW_PWIN: ["Your appeal has ended", `${county} The chance of winning at the next level is too low, so this appeal is closed.`],
    C_LOW_EV: ["Your appeal has ended", `${county} Appealing again is not likely to be worth the cost, so this appeal is closed.`],
    C_PROCEDURAL_BAR: ["Your appeal has ended", `${county} This cannot be fixed, so this appeal is closed.`],
    C_BUDGET: ["Your appeal has ended", `${county} We could not schedule the next filing in time, so this appeal is closed.`],
    C_UNHANDLED: ["Your appeal has ended", `${county} This situation is outside what we can handle automatically, so this appeal is closed.`],
    P_HEARING_SCHEDULED: ["Your hearing is scheduled", `The county scheduled a hearing for ${f?.hearingDate}. We will check the result the day after.`],
    P_NOT_FINAL: ["No decision yet", `The county has not decided yet. We will check again on ${d.requeueOn}.`],
    P_CLARIFY: ["We are confirming the county's decision", "We received a letter from the county that does not clearly state the decision. We are asking for a clearer copy or a clarification."],
    P_READ_RETRY: ["We received the county's letter", "We received a letter from the county about your appeal and are processing it."],
    P_BUDGET: ["We are preparing your next appeal", `${county} We are preparing the next-level appeal and plan to file it shortly; the filing deadline is ${next?.deadline}.`],
  };
  const [subject, body] = lines[code] ?? ["Update on your appeal", county || "There is an update on your property tax appeal."];
  return { channel: c.owner.contactChannel, subject, body: `${body.trim()} No action is needed from you.`, autoSend: true };
}
