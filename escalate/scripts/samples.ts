/**
 * Synthetic sample cases and decision letters, one per Escalate path. Every name, parcel, letter
 * and authority here is made up. `expect` is what the placeholder config must decide on
 * 2026-11-05 with the offline reader; the tests check it.
 */
export const SAMPLE_TODAY = "2026-11-05";

type Json = Record<string, unknown>;
export interface Sample {
  n: number;
  title: string;
  case: Json;
  decision: Json;
  expect: { status: string; code: string; flags?: string[] };
}

const pad = (n: number) => String(n).padStart(4, "0");

function makeCase(n: number, over: Json = {}): Json {
  return {
    caseId: `case_placeholder_PH-${pad(n)}`,
    parcelId: `PH-${pad(n)}`,
    jurisdictionId: "placeholder",
    address: `${100 + n} Placeholder Lane, Sampletown`,
    owner: { names: [`Sample Owner ${n}`], type: "individual", contactChannel: "email" },
    assessedValue: 500_000,
    targetValue: 420_000,
    taxRate: 0.02,
    qualify: { pWin: 0.6, confidence: 0.7, annualSavings: 1600 },
    currentLevel: "review",
    filings: [{ level: "review", filedOn: "2026-09-15", claimedValue: 420_000 }],
    authorization: { signedOn: "2026-09-01", feePct: 0.3, scope: ["all_levels"], escalation: { appealPartialIfRemainingAnnualAbove: 500, acceptReopenRisk: false } },
    priorDecisions: [],
    readAttempts: [],
    ...over,
  };
}

function letter(n: number, body: string, decisionDate?: string, board = "Placeholder County Assessment Board"): string {
  return [board, "Notice of Decision", `Parcel: PH-${pad(n)}`, decisionDate ? `Decision date: ${decisionDate}` : "", "", body, "", "This notice is synthetic sample data."].filter((l, i) => l !== "" || i === 4).join("\n");
}

function makeDecision(n: number, text: string, receivedOn: string, over: Json = {}): Json {
  return { decisionId: `D-${pad(n)}`, caseId: `case_placeholder_PH-${pad(n)}`, level: "review", receivedOn, channel: "mail", text, attachments: [], ...over };
}

export function buildSamples(): Sample[] {
  const s: Sample[] = [];
  const add = (n: number, title: string, c: Json, d: Json, expect: Sample["expect"]) => s.push({ n, title, case: c, decision: d, expect });

  add(1, "Full win", makeCase(1), makeDecision(1, letter(1, "After review, the request is granted in full. The assessed value is reduced to $420,000.", "2026-10-28"), "2026-10-31"), { status: "COLLECT", code: "W_FULL_WIN" });
  add(2, "Partial, no owner preference", makeCase(2, { authorization: { signedOn: "2026-09-01", feePct: 0.3, scope: ["all_levels"] } }), makeDecision(2, letter(2, "The request is granted in part. The assessed value is reduced to $470,000.", "2026-10-28"), "2026-10-31"), { status: "COLLECT", code: "W_PARTIAL_ACCEPTED", flags: ["F_DEFAULT_PREFERENCE"] });
  add(3, "Partial, remainder above threshold", makeCase(3), makeDecision(3, letter(3, "The request is granted in part. The assessed value is reduced to $470,000.", "2026-10-28"), "2026-10-31"), { status: "ESCALATE", code: "A_NEXT_LEVEL" });
  add(4, "Partial, remainder below threshold", makeCase(4, { authorization: { signedOn: "2026-09-01", feePct: 0.3, scope: ["all_levels"], escalation: { appealPartialIfRemainingAnnualAbove: 2000 } } }), makeDecision(4, letter(4, "The request is granted in part. The assessed value is reduced to $470,000.", "2026-10-28"), "2026-10-31"), { status: "COLLECT", code: "W_PARTIAL_ACCEPTED" });
  add(5, "Denied, comps rejected, good EV", makeCase(5), makeDecision(5, letter(5, "The request is denied. The board found that the comparable sales submitted were not comparable to the subject property. The assessed value of $500,000 is sustained. You may appeal to the Formal Appeal level by 2026-12-12.", "2026-10-28"), "2026-10-31"), { status: "ESCALATE", code: "A_NEXT_LEVEL" });
  add(6, "Denied, value supported, low EV", makeCase(6, { assessedValue: 300_000, targetValue: 285_000 }), makeDecision(6, letter(6, "The request is denied. The board finds the market evidence supports the assessed value.", "2026-10-28"), "2026-10-31"), { status: "CLOSED", code: "C_LOW_EV" });
  add(7, "Denied at the last level ClaimOS can file", makeCase(7, { currentLevel: "board", filings: [{ level: "board", filedOn: "2026-09-20", claimedValue: 420_000 }] }), makeDecision(7, letter(7, "The appeal is denied. The board found insufficient evidence to change the value.", "2026-10-28", "Placeholder Appeals Board"), "2026-10-31", { level: "board" }), { status: "CLOSED", code: "C_REFER_OUT" });
  add(8, "Denied, deadline passed", makeCase(8), makeDecision(8, letter(8, "The request is denied.", "2026-09-01"), "2026-09-04"), { status: "CLOSED", code: "C_DEADLINE_PASSED", flags: ["F_MISSED_DEADLINE"] });
  add(9, "Denied, tight deadline within fast track", makeCase(9), makeDecision(9, letter(9, "The request is denied. The board found insufficient evidence to change the value.", "2026-09-27"), "2026-10-01"), { status: "ESCALATE", code: "A_FAST_TRACK", flags: ["F_FAST_TRACK"] });
  add(10, "Hearing scheduled", makeCase(10), makeDecision(10, letter(10, "A hearing has been scheduled for 2026-11-20. No decision has been made on your request yet."), "2026-11-02"), { status: "PENDING", code: "P_HEARING_SCHEDULED" });
  add(11, "Dismissed, missing signature", makeCase(11), makeDecision(11, letter(11, "Your request is dismissed because the form was not signed by the owner or an authorized agent.", "2026-11-01"), "2026-11-03"), { status: "ESCALATE", code: "A_REFILE_SAME_LEVEL" });
  add(12, "Dismissed, filed late", makeCase(12), makeDecision(12, letter(12, "Your request is dismissed because it was filed after the filing deadline.", "2026-11-01"), "2026-11-03"), { status: "CLOSED", code: "C_PROCEDURAL_BAR" });
  add(13, "Vague letter, plenty of time", makeCase(13), makeDecision(13, letter(13, "We have received your correspondence regarding this parcel. Further information will follow under separate cover."), "2026-11-04"), { status: "PENDING", code: "P_CLARIFY", flags: ["F_SECOND_READ"] });
  add(14, "Vague letter, clarification window used up", makeCase(14, { readAttempts: [{ decisionId: "D-0014", attempts: 1, firstPendingOn: "2026-10-25" }] }), makeDecision(14, letter(14, "We have received your correspondence regarding this parcel. Further information will follow under separate cover."), "2026-10-24"), { status: "ESCALATE", code: "A_NEXT_LEVEL", flags: ["F_ASSUMED_DENIAL", "F_DATE_FROM_RECEIPT"] });
  add(15, "Authorization does not cover the next level", makeCase(15, { authorization: { signedOn: "2026-09-01", feePct: 0.3, scope: ["review"] } }), makeDecision(15, letter(15, "The request is denied. The board found insufficient evidence to change the value.", "2026-10-28"), "2026-10-31"), { status: "CLOSED", code: "C_NOT_AUTHORIZED" });
  add(16, "Next level can raise the value, owner did not accept", makeCase(16, { currentLevel: "appeal", filings: [{ level: "appeal", filedOn: "2026-10-01", claimedValue: 420_000 }] }), makeDecision(16, letter(16, "The appeal is denied. The board found insufficient evidence to change the value.", "2026-10-28", "Placeholder Appeals Panel"), "2026-10-31", { level: "appeal" }), { status: "CLOSED", code: "C_REOPEN_RISK" });
  add(17, "Letter for a different case", makeCase(17), { ...makeDecision(17, letter(99, "The request is granted in full. The assessed value is reduced to $420,000.", "2026-10-28"), "2026-10-31"), caseId: "case_placeholder_PH-0099" }, { status: "INCOMPLETE", code: "I_CASE_MISMATCH" });
  return s;
}
