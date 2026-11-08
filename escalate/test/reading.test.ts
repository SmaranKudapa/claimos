/** Quote check, numbers beat labels, second read, deadline conflicts, config validation, owner updates, Florida. */
import { describe, expect, it } from "vitest";
import { parseConfig } from "../src/config.js";
import { escalate, escalateAll } from "../src/pipeline.js";
import { verifyQuotes } from "../src/reader/verify-quotes.js";
import { toAppealBeat, toCaseRecordPatch } from "../src/case.js";
import type { DecisionReading } from "../src/types.js";
import { buildSamples } from "../scripts/samples.js";
import { config, ctx, floridaConfig, ScriptedReader } from "./helpers.js";

const samples = buildSamples();
const sample = (n: number) => samples.find((s) => s.n === n)!;

describe("quote check", () => {
  it("drops a fact whose quote is not in the letter; a dropped outcome becomes unclear", () => {
    const letter = "The request is DENIED.\n The assessed   value is unchanged.";
    const r: DecisionReading = {
      outcome: "denied",
      newAssessedValue: 410_000,
      reasonCategories: ["comps_rejected"],
      confidence: 0.9,
      evidence: [
        { field: "outcome", quote: "the request is denied" },
        { field: "newAssessedValue", quote: "reduced to $410,000" },
        { field: "reasonCategories.comps_rejected", quote: "comparables were rejected" },
      ],
    };
    const { reading, dropped } = verifyQuotes(r, letter);
    expect(reading.outcome).toBe("denied");
    expect(reading.newAssessedValue).toBeUndefined();
    expect(reading.reasonCategories).toEqual([]);
    expect(dropped.sort()).toEqual(["newAssessedValue", "reasonCategories.comps_rejected"]);
    const made = verifyQuotes({ ...r, evidence: [{ field: "outcome", quote: "granted in full" }] }, letter);
    expect(made.reading.outcome).toBe("unclear");
  });
});

describe("numbers beat labels and trigger a second read", () => {
  it("a 'partial' label with a value at the target is a full win, after a second read", async () => {
    const s = sample(3);
    const text = String(s.decision.text).replace("$470,000", "$420,000");
    const first: DecisionReading = {
      outcome: "partial_reduction",
      newAssessedValue: 420_000,
      reasonCategories: [],
      confidence: 0.9,
      evidence: [
        { field: "outcome", quote: "granted in part" },
        { field: "newAssessedValue", quote: "reduced to $420,000" },
      ],
    };
    const second: DecisionReading = { ...first, outcome: "full_win", evidence: [{ field: "outcome", quote: "granted in part" }, { field: "newAssessedValue", quote: "reduced to $420,000" }] };
    const reader = new ScriptedReader({ "first-model": first, "strong-model": second });
    const r = await escalate(s.case, { ...s.decision, text }, ctx({ reader }));
    expect(reader.calls).toEqual(["first-model", "strong-model"]);
    expect(r.flags).toContain("F_SECOND_READ");
    expect(r.status).toBe("COLLECT");
    expect(r.reasonCodes).toContain("W_FULL_WIN");
  });

  it("a value above the assessed value is a denial against the higher value", async () => {
    const s = sample(5);
    const text = "Decision date: 2026-10-28\nAfter review the value was set at $520,000.";
    const r = await escalate(s.case, { ...s.decision, text }, ctx());
    expect(r.flags).toContain("F_VALUE_INCREASED");
    expect(r.economics!.gap).toBe(100_000);
  });
});

describe("deadlines", () => {
  it("when the letter's deadline and the rule differ, the earlier one wins", async () => {
    const s = sample(5);
    const text = String(s.decision.text).replace("by 2026-12-12", "by 2026-12-01");
    const r = await escalate(s.case, { ...s.decision, text }, ctx());
    expect(r.flags).toContain("F_DEADLINE_CONFLICT");
    expect(r.nextLevel!.deadline).toBe("2026-12-01");
  });
});

describe("config validation", () => {
  it("lists every bad path", () => {
    const bad = config() as unknown as Record<string, any>;
    bad.ladder[1].order = 5;
    bad.ladder[1].fastTrackDays = 99;
    bad.ladder[2].id = "review";
    bad.economics.pWinFloor = 0.9;
    let msg = "";
    try {
      parseConfig(bad, "bad.json");
    } catch (e) {
      msg = (e as Error).message;
    }
    expect(msg).toContain("Invalid escalate config bad.json");
    expect(msg).toContain("ladder.1.fastTrackDays");
    expect(msg).toContain("ladder.2.id");
    expect(msg).toContain("economics.pWinFloor");
    expect(msg).toMatch(/orders must run 1, 2, 3/);
  });
});

describe("owner updates", () => {
  it("never contain a dollar figure that is not a verified value", async () => {
    const rs = await escalateAll(samples.map((s) => ({ case: s.case, decision: s.decision })), ctx());
    for (const r of rs) {
      if (!r.ownerUpdate) {
        expect(r.status).toBe("INCOMPLETE");
        continue;
      }
      const s = samples.find((x) => x.case.caseId === r.caseId)!;
      const allowed = new Set([Number(s.case.assessedValue), r.reading.verified?.newAssessedValue].filter((x): x is number => typeof x === "number"));
      for (const m of r.ownerUpdate.body.matchAll(/\$([\d,]+)/g)) expect(allowed.has(Number(m[1]!.replace(/,/g, ""))), `${r.caseId}: ${m[0]}`).toBe(true);
      expect(r.ownerUpdate.channel).toBe("email");
      expect(r.ownerUpdate.body).not.toMatch(/guarantee|will win|promise/i);
    }
  });
});

describe("website export", () => {
  it("builds 'Appeal again' beats and hides money on closed cases", async () => {
    const rs = await escalateAll([sample(5), sample(6)].map((s) => ({ case: s.case, decision: s.decision })), ctx());
    const esc = rs.find((r) => r.status === "ESCALATE")!;
    const closed = rs.find((r) => r.status === "CLOSED")!;
    expect(toAppealBeat(esc)).toMatchObject({ id: "escalate", label: "Appeal again", state: "escalating", value: "Formal appeal by Dec 12, 2026" });
    expect(toCaseRecordPatch(esc)).toMatchObject({ filingFee: 40, deadline: "Dec 12, 2026", appealStatus: "ESCALATE" });
    expect(toCaseRecordPatch(closed)).toMatchObject({ potentialRecovery: null, expectedValue: null, filingFee: null, appealStatus: "CLOSED" });
  });
});

describe("Florida desk", () => {
  const flCase = (over: Record<string, unknown> = {}) => ({ ...sample(5).case, caseId: "FL-13-2026-123", jurisdictionId: "FL-13", currentLevel: "vab_value_appeal", ...over });
  const flDecision = (text: string) => ({ decisionId: "FL-D1", caseId: "FL-13-2026-123", level: "vab_petition", receivedOn: "2026-10-31", channel: "mail", text, attachments: [] });

  it("a board denial is referred out to a licensed professional, with the court note", async () => {
    const r = await escalate(flCase(), flDecision("Decision date: 2026-10-28\nThe petition is denied."), ctx({ config: floridaConfig() }));
    expect(r.status).toBe("CLOSED");
    expect(r.reasonCodes).toContain("C_REFER_OUT");
    expect(r.ownerUpdate!.body).toContain("circuit court within 60 days");
  });

  it("a partial win at the board is accepted, never closed", async () => {
    const r = await escalate(flCase(), flDecision("Decision date: 2026-10-28\nThe petition is granted in part. The assessed value is reduced to $470,000."), ctx({ config: floridaConfig() }));
    expect(r.status).toBe("COLLECT");
    expect(r.flags).toContain("F_ESCALATION_BLOCKED");
  });

  it("rejects a case from a jurisdiction the desk does not cover", async () => {
    const r = await escalate(flCase({ jurisdictionId: "IL-31" }), flDecision("The petition is denied."), ctx({ config: floridaConfig() }));
    expect(r.reasonCodes).toContain("I_WRONG_DESK");
  });
});
