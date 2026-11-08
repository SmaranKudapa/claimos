/** Sign up's authorization line: parsing, safe fallback, and its effect on decisions (synthetic data). */
import { describe, expect, it } from "vitest";
import { caseFromQualify, decisionFromComment, parseAuthorizationLine, parseLetterComment, type QualifyHandoffEntry } from "../src/board.js";
import { escalate } from "../src/pipeline.js";
import { ctx, config } from "./helpers.js";

describe("parseAuthorizationLine", () => {
  it("reads the agreed line", () => {
    expect(parseAuthorizationLine("authorization: case_id FL-1 · scope vab_petition · fee 30% · partial_above 500 · reopen_risk no · signed 2026-09-01")).toEqual({
      caseId: "FL-1",
      scope: ["vab_petition"],
      feePct: 0.3,
      appealPartialIfRemainingAnnualAbove: 500,
      acceptReopenRisk: false,
      signedOn: "2026-09-01",
    });
  });

  it("accepts any field order, a scope list, $ amounts and 'none'; finds the line inside a longer comment", () => {
    const a = parseAuthorizationLine("Signed by the owner.\nauthorization: fee 25% · reopen_risk yes · scope review,appeal · case_id X-9 · partial_above $1,200/yr");
    expect(a).toMatchObject({ caseId: "X-9", scope: ["review", "appeal"], feePct: 0.25, appealPartialIfRemainingAnnualAbove: 1200, acceptReopenRisk: true });
    expect(parseAuthorizationLine("authorization: case_id X · scope all_levels · fee 30% · partial_above none")).toMatchObject({ scope: ["all_levels"], acceptReopenRisk: false });
    expect(parseAuthorizationLine("authorization: case_id X · scope all_levels · fee 30% · partial_above none")!.appealPartialIfRemainingAnnualAbove).toBeUndefined();
  });

  it("returns null for anything unreadable, so the desk default applies", () => {
    for (const bad of [
      "no authorization here",
      "authorization: scope vab_petition · fee 30%",
      "authorization: case_id X · fee 30%",
      "authorization: case_id X · scope vab_petition · fee thirty",
      "authorization: case_id X · scope vab_petition · fee 130%",
      "authorization: case_id X · scope vab_petition · fee 30% · partial_above lots",
      "authorization: case_id X · scope vab_petition · fee 30% · reopen_risk maybe",
    ])
      expect(parseAuthorizationLine(bad), bad).toBeNull();
  });
});

describe("signed authorization in decisions", () => {
  const entry: QualifyHandoffEntry = {
    find_case_id: "case_placeholder_PH-0501",
    parcelId: "PH-0501",
    jurisdictionId: "placeholder",
    address: "1 Sample St",
    judgedAsOf: "2026-09-01",
    pWin: 0.6,
    route: { id: "review" },
    assessedValue: 500_000,
    targetValue: 420_000,
    taxRate: 0.02,
    owner: { names: ["SAMPLE"], type: "individual" },
  };
  const letter = parseLetterComment(
    "decision-letter · case case_placeholder_PH-0501 · level review · received 2026-10-31 · m1\nDecision date: 2026-10-28\nThe request is granted in part. The assessed value is reduced to $470,000.",
  )!;
  const run = (signed: ReturnType<typeof parseAuthorizationLine>) => escalate(caseFromQualify(entry, letter, config(), { signed }), decisionFromComment(letter, null), ctx());

  it("without one, a partial win is accepted and the default is flagged", async () => {
    const r = await run(null);
    expect(r.status).toBe("COLLECT");
    expect(r.flags).toContain("F_DEFAULT_AUTHORIZATION");
  });

  it("with the owner's 'keep appealing above $500/yr', the rest is appealed", async () => {
    const r = await run(parseAuthorizationLine("authorization: case_id case_placeholder_PH-0501 · scope all_levels · fee 30% · partial_above 500 · reopen_risk no"));
    expect(r.status).toBe("ESCALATE");
    expect(r.reasonCodes).toContain("A_NEXT_LEVEL");
    expect(r.flags).not.toContain("F_DEFAULT_AUTHORIZATION");
  });

  it("an authorization for a different case is ignored", async () => {
    const r = await run(parseAuthorizationLine("authorization: case_id someone-else · scope all_levels · fee 30% · partial_above 500"));
    expect(r.flags).toContain("F_DEFAULT_AUTHORIZATION");
    expect(r.status).toBe("COLLECT");
  });
});
