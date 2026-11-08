import { describe, expect, it } from "vitest";
import { qualify } from "../src/pipeline.js";
import { toCaseRecord, toQualifyBeat, formatDeadline } from "../src/case.js";
import { naiveCredentialsFromEnv } from "../src/llm/naive.js";
import { candidate, config, ctx, NOW } from "./helpers.js";

describe("Claim OS UI adapters", () => {
  it("maps a QUALIFIED result onto the prototype caseRecord fields", async () => {
    const cand = candidate();
    const r = await qualify(cand, ctx(), { now: NOW });
    expect(r.status).toBe("QUALIFIED");
    const c = toCaseRecord(r, { candidate: cand, config: config() });
    expect(c).toMatchObject({
      id: r.caseId,
      desk: "Property Tax",
      claimant: "Pat Example",
      apn: "T-1",
      assessedValue: 1_050_000,
      proposedValue: r.valuation!.target,
      potentialRecovery: r.economics!.annualSavings,
      probability: r.economics!.pWin,
      expectedValue: r.economics!.ev,
      estimatedFee: r.economics!.fee,
      filingFee: 0,
      deadline: "Dec 18, 2026",
      status: "QUALIFIED",
    });
    expect(c.caseCost).toBeCloseTo(r.economics!.maxLoss, 2); // review route has no filing fee
    expect(c.qualify).toBe(r);
    const beat = toQualifyBeat(r);
    expect(beat).toMatchObject({ id: "qualify", label: "Qualify", state: "qualified", actor: "Eligibility Agent" });
    expect(beat.kicker).toMatch(/% estimated win probability$/);
  });

  it("never shows money for leads that won't be pursued, and works without the candidate", async () => {
    const r = await qualify(candidate({ assessment: { assessedValue: 600_000 } }), ctx(), { now: NOW });
    expect(r.status).toBe("REJECTED");
    const c = toCaseRecord(r);
    expect(c.claimant).toBeNull();
    expect([c.proposedValue, c.potentialRecovery, c.expectedValue, c.deadline]).toEqual([null, null, null, null]);
    expect(toQualifyBeat(r)).toMatchObject({ state: "rejected", kicker: "V_NO_GAP", value: "No spend" });
  });

  it("formats deadlines like the prototype", () => {
    expect(formatDeadline("2026-12-15")).toBe("Dec 15, 2026");
  });
});

describe("Naïve credentials", () => {
  it("accept NAIVE_* first and fall back to the repo's VETTA_* names", () => {
    expect(naiveCredentialsFromEnv({ VETTA_API_KEY: "v", VETTA_API_BASE_URL: "https://x" })).toEqual({ apiKey: "v", baseUrl: "https://x" });
    expect(naiveCredentialsFromEnv({ NAIVE_API_KEY: "n", VETTA_API_KEY: "v" })).toEqual({ apiKey: "n" });
    expect(naiveCredentialsFromEnv({})).toEqual({ apiKey: "" });
  });
});
