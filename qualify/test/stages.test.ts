import { describe, expect, it } from "vitest";
import { qualify, qualifyAll } from "../src/pipeline.js";
import { SuppressionSchema } from "../src/types.js";
import { NOW, TODAY, candidate, comps, config, ctx } from "./helpers.js";

const run = (raw: unknown, c = ctx()) => qualify(raw, c, { now: NOW });

describe("baseline", () => {
  it("a clean lead qualifies with a route, economics, and a summary", async () => {
    const r = await run(candidate());
    expect(r.status).toBe("QUALIFIED");
    expect(r.route?.id).toBe("review");
    expect(r.economics!.ev).toBeGreaterThan(25);
    expect(r.valuation!.target).toBeGreaterThanOrEqual(r.valuation!.estimate); // conservative
    expect(r.summary).toMatch(/file via/);
    expect(r.stageLog.map((s) => s.stage)).toEqual(["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"]);
  });
});

describe("S0 intake", () => {
  it("missing required field → INCOMPLETE · I_MISSING naming the field", async () => {
    const c = candidate();
    delete (c.assessment as Record<string, unknown>).taxRate;
    const r = await run(c);
    expect(r.status).toBe("INCOMPLETE");
    expect(r.reasonCodes).toEqual(["I_MISSING"]);
    expect(r.summary).toMatch(/assessment\.taxRate/);
  });
  it("wrong type → I_SCHEMA", async () => {
    const r = await run(candidate({ assessment: { assessedValue: "lots" } }));
    expect(r.reasonCodes).toEqual(["I_SCHEMA"]);
  });
  it("insane values → I_INVALID", async () => {
    const r = await run(candidate({ assessment: { assessedValue: -5 } }));
    expect(r.reasonCodes).toEqual(["I_INVALID"]);
  });
  it("assessment for another valuation date → I_STALE", async () => {
    const r = await run(candidate({ assessment: { valuationDate: "2025-01-01" } }));
    expect(r.reasonCodes).toEqual(["I_STALE"]);
  });
  it("old fetch → I_STALE", async () => {
    const r = await run(candidate({ provenance: { fetchedAt: "2026-06-01", sources: {}, rawDocs: [] } }));
    expect(r.reasonCodes).toEqual(["I_STALE"]);
  });
  it("normalizes property-type aliases", async () => {
    const r = await run(candidate({ propertyType: "single family" }));
    expect(r.status).toBe("QUALIFIED");
  });
  it("dedupe keeps the newest record", async () => {
    const older = candidate({ assessment: { assessedValue: 2_000_000 }, provenance: { fetchedAt: "2026-10-01", sources: {}, rawDocs: [] } });
    const newer = candidate();
    const sum = await qualifyAll([older, newer], ctx(), { now: NOW });
    expect(sum.merged).toBe(1);
    expect(sum.results).toHaveLength(1);
    expect(sum.results[0]!.economics!.annualSavings).toBeLessThan(5000);
  });
});

describe("S1 suppression", () => {
  const sup = (o: object) => ctx({ suppression: SuppressionSchema.parse(o) });
  it("DNC by parcel and by owner name", async () => {
    expect((await run(candidate(), sup({ dncParcels: ["T-1"] }))).reasonCodes).toEqual(["S_DNC"]);
    expect((await run(candidate(), sup({ dncOwners: ["PAT EXAMPLE"] }))).reasonCodes).toEqual(["S_DNC"]);
  });
  it("existing case, represented, cooldown, government", async () => {
    expect((await run(candidate({ status: { appealOnFile: false, existingCaseId: "c1" } }))).reasonCodes).toEqual(["S_EXISTING_CASE"]);
    expect((await run(candidate(), sup({ representedParcels: ["T-1"] }))).reasonCodes).toEqual(["S_REPRESENTED"]);
    expect((await run(candidate(), sup({ declined: [{ parcelId: "T-1", date: "2026-10-01" }] }))).reasonCodes).toEqual(["S_COOLDOWN"]);
    expect((await run(candidate(), sup({ declined: [{ parcelId: "T-1", date: "2025-01-01" }] }))).status).toBe("QUALIFIED");
    expect((await run(candidate({ owner: { type: "government" } }))).reasonCodes).toEqual(["S_EXEMPT_OWNER"]);
  });
  it("rejection cache reuses a recent rejection with identical inputs", async () => {
    const c = ctx();
    const first = await run(candidate({ assessment: { assessedValue: 900_000 } }), c);
    expect(first.status).toBe("REJECTED");
    c.priorResults.set(first.caseId, first);
    const second = await run(candidate({ assessment: { assessedValue: 900_000 } }), c);
    expect(second.reasonCodes[0]).toBe("S_CACHED");
    // Changed inputs → recomputed
    const third = await run(candidate({ assessment: { assessedValue: 1_050_000 } }), c);
    expect(third.status).toBe("QUALIFIED");
  });
});

describe("S2 eligibility", () => {
  it("hard failures", async () => {
    expect((await run(candidate({ jurisdictionId: "elsewhere" }))).reasonCodes).toEqual(["E_NO_DESK"]);
    expect((await run(candidate({ propertyType: "COMMERCIAL" }))).reasonCodes).toEqual(["E_TYPE"]);
    expect((await run(candidate({ status: { appealOnFile: true } }))).reasonCodes).toEqual(["E_ALREADY_FILED"]);
    expect((await run(candidate({ assessment: { exemptions: [{ type: "X", fullyExempt: true }] } }))).reasonCodes).toEqual(["E_EXEMPT"]);
  });
  it("no owner / no mailing address → INCOMPLETE · I_OWNER", async () => {
    const r = await run(candidate({ owner: { names: [], type: "individual", mailingAddress: "x" } }));
    expect(r.status).toBe("INCOMPLETE");
    expect(r.reasonCodes).toEqual(["I_OWNER"]);
  });
  it("flags never reject; they send the lead to review", async () => {
    const trust = await run(candidate({ owner: { names: ["A Trust"], type: "trust", mailingAddress: "x" }, assessment: { assessedValue: 1_150_000 } }));
    expect(trust.status).toBe("NEEDS_REVIEW");
    expect(trust.flags).toContain("F_COMPLEX_OWNER");

    const sold = await run(candidate({ transfer: { date: "2025-06-01", price: 1_000_000, armsLength: true }, assessment: { assessedValue: 1_150_000 } }));
    expect(sold.flags).toContain("F_RECENT_TRANSFER");
    expect(sold.status).toBe("NEEDS_REVIEW");

    const permit = await run(candidate({ physical: { livingArea: 1400, lotArea: 4200, yearBuilt: 1965, lastPermitDate: "2025-05-01", permitTypes: ["ADDITION"] }, assessment: { assessedValue: 1_150_000 } }));
    expect(permit.flags).toContain("F_VALUE_CHANGE");
  });
  it("flags lower p(win)", async () => {
    const clean = await run(candidate({ assessment: { assessedValue: 1_150_000 } }));
    const sold = await run(candidate({ transfer: { date: "2025-06-01", price: 1_000_000, armsLength: true }, assessment: { assessedValue: 1_150_000 } }));
    expect(sold.economics!.pWin).toBeLessThan(clean.economics!.pWin);
  });
});

describe("S3 valuation", () => {
  it("comps never fetched → INCOMPLETE · I_NO_COMPS", async () => {
    const c = candidate();
    delete c.comps;
    expect((await run(c)).reasonCodes).toEqual(["I_NO_COMPS"]);
  });
  it("comps filtered by distance, date, size, type, arm's-length", async () => {
    const bad = comps(650, 1400, 5).map((k, i) =>
      [{ ...k, distance: 5 }, { ...k, saleDate: "2024-01-01" }, { ...k, livingArea: 4000 }, { ...k, propertyType: "CONDO" }, { ...k, armsLength: false }][i],
    );
    const r = await run(candidate({ comps: bad }));
    expect(r.reasonCodes).toEqual(["V_INSUFFICIENT_COMPS"]);
  });
  it("below market → V_NO_GAP; small gap → V_GAP_SMALL", async () => {
    expect((await run(candidate({ assessment: { assessedValue: 600_000 } }))).reasonCodes).toEqual(["V_NO_GAP"]);
    expect((await run(candidate({ assessment: { assessedValue: 950_000 } }))).reasonCodes).toEqual(["V_GAP_SMALL"]);
  });
  it("low confidence rejects small leads but only flags high-value ones", async () => {
    const noisy = (a: number) => {
      const ks = comps(650, 1400, 3).map((k, i) => ({ ...k, price: Math.round(k.price * [0.7, 1.0, 1.35][i]!) }));
      return candidate({ comps: ks, assessment: { assessedValue: a }, physical: { livingArea: 1400 } });
    };
    expect((await run(noisy(1_250_000))).reasonCodes).toEqual(["V_LOW_CONFIDENCE"]);
    const big = await run(noisy(2_600_000));
    expect(big.flags).toContain("F_LOW_CONFIDENCE");
    expect(big.status).toBe("NEEDS_REVIEW");
  });
});

describe("S4 economics", () => {
  it("EV = p(signup) × (p(win) × fee − post) − pre", async () => {
    const r = await run(candidate());
    const e = r.economics!;
    expect(e.ev).toBeCloseTo(e.pSignup * (e.pWin * e.fee - e.postCosts) - e.preCosts, 0);
    expect(e.maxLoss).toBeCloseTo(e.preCosts + e.postCosts, 2);
  });
  it("small savings → C_SAVINGS_LOW", async () => {
    const r = await run(candidate({ assessment: { taxRate: 0.002 } }));
    expect(r.reasonCodes).toEqual(["C_SAVINGS_LOW"]);
  });
  it("EV below minimum → C_EV_LOW", async () => {
    const c = ctx({ config: config((x) => (x.thresholds.minExpectedValue = 10_000)) });
    expect((await run(candidate(), c)).reasonCodes).toEqual(["C_EV_LOW"]);
  });
});

describe("S5 timing", () => {
  it("no open route → NEXT_CYCLE with a re-qualify date", async () => {
    const c = ctx({ today: "2027-01-10" });
    const r = await qualify(candidate({ provenance: { fetchedAt: "2027-01-05", sources: {}, rawDocs: [] } }), c, { now: NOW });
    expect(r.status).toBe("NEXT_CYCLE");
    expect(r.reasonCodes).toEqual(["T_NO_ROUTE"]);
    expect(r.requalifyOn).toBe("2027-03-18");
  });
  it("too little time left → NEXT_CYCLE", async () => {
    const c = ctx({ today: "2026-12-12" });
    const r = await qualify(candidate({ provenance: { fetchedAt: "2026-12-01", sources: {}, rawDocs: [] } }), c, { now: NOW });
    expect(r.status).toBe("NEXT_CYCLE");
    expect(r.summary).toMatch(/need 7/);
  });
  it("urgency rises as the deadline nears", async () => {
    const early = await run(candidate());
    const late = await qualify(candidate({ provenance: { fetchedAt: "2026-12-01", sources: {}, rawDocs: [] } }), ctx({ today: "2026-12-07" }), { now: NOW });
    expect(late.route!.urgency).toBeGreaterThan(early.route!.urgency);
  });
  it("strong claim only fileable on a closed route waits instead of filing a weak one now", async () => {
    const r = await run(candidate({ assessment: { assessedValue: 960_000 }, neighborhood: { medianAssessmentRatio: 0.8 } }));
    expect(r.status).toBe("NEXT_CYCLE");
    expect(r.valuation!.bases[0]!.basis).toBe("uniformity");
  });
  it("no (route, basis) pair clears both the gap and EV minimums → C_EV_LOW at S5", async () => {
    // The best-EV pair (market_value via review) passes S4 but its gap is under the minimum;
    // the big-gap basis (uniformity) is only accepted by a route whose fee sinks its EV.
    const c = ctx({
      config: config((x) => {
        x.thresholds.minGapPct = 0.2;
        x.routes[1]!.filingFee = 100_000;
      }),
    });
    const r = await run(candidate({ neighborhood: { medianAssessmentRatio: 0.8 } }), c);
    expect(r.status).toBe("REJECTED");
    expect(r.reasonCodes).toEqual(["C_EV_LOW"]);
    expect(r.stageLog.find((s) => s.outcome === "stop")!.stage).toBe("S5");
    expect(r.stageLog.find((s) => s.stage === "S4")!.outcome).toBe("pass");
  });
});

describe("S7 decision & ranking", () => {
  it("high value while desk is new → NEEDS_REVIEW · F_HIGH_VALUE", async () => {
    const r = await run(candidate({ assessment: { assessedValue: 3_000_000 }, physical: { livingArea: 3500 }, comps: comps(650, 3500) }));
    expect(r.flags).toContain("F_HIGH_VALUE");
    expect(r.status).toBe("NEEDS_REVIEW");
  });
  it("releases only dailyReleaseLimit QUALIFIED leads, highest priority first", async () => {
    const c = ctx({ config: config((x) => (x.capacity.dailyReleaseLimit = 2)) });
    const leads = [1_050_000, 1_100_000, 1_150_000].map((a, i) => candidate({ parcelId: `T-${i}`, assessment: { assessedValue: a } }));
    const sum = await qualifyAll(leads, c, { now: NOW });
    const q = sum.results.filter((r) => r.status === "QUALIFIED");
    expect(q).toHaveLength(3);
    expect(q.map((r) => !!r.releaseDate)).toEqual([true, true, false]);
    expect(q[0]!.priority).toBeGreaterThanOrEqual(q[1]!.priority);
    expect(q[0]!.releaseDate).toBe(TODAY);
  });
  it("is deterministic", async () => {
    const a = await run(candidate());
    const b = await run(candidate());
    expect(b).toEqual(a);
  });
});
