/** One test per sample path (D.8), plus the budget path (18). */
import { describe, expect, it } from "vitest";
import { escalateAll } from "../src/pipeline.js";
import { buildSamples } from "../scripts/samples.js";
import { config, ctx } from "./helpers.js";

const samples = buildSamples();

describe("sample paths", () => {
  for (const s of samples) {
    it(`${s.n}. ${s.title} → ${s.expect.status} (${s.expect.code})`, async () => {
      const [r] = await escalateAll([{ case: s.case, decision: s.decision }], ctx());
      expect(r!.status).toBe(s.expect.status);
      expect(r!.reasonCodes).toContain(s.expect.code);
      for (const f of s.expect.flags ?? []) expect(r!.flags).toContain(f);
    });
  }

  it("5. denied for rejected comps asks Evidence for fresh comps", async () => {
    const s = samples.find((x) => x.n === 5)!;
    const [r] = await escalateAll([{ case: s.case, decision: s.decision }], ctx());
    expect(r!.evidenceRequests.map((e) => e.key)).toEqual(["fresh_comps"]);
    expect(r!.nextLevel).toMatchObject({ id: "appeal", deadline: "2026-12-12", filingFee: 40, hearing: true });
  });

  it("11. a missing signature asks Evidence for the signature and refiles at the same level", async () => {
    const s = samples.find((x) => x.n === 11)!;
    const [r] = await escalateAll([{ case: s.case, decision: s.decision }], ctx());
    expect(r!.evidenceRequests[0]).toMatchObject({ key: "missing_signature", forStep: "evidence" });
    expect(r!.nextLevel).toMatchObject({ id: "review", deadline: "2026-11-16" });
  });

  it("18. over the daily filing-fee budget, the lowest-EV escalations wait a day", async () => {
    const cfg = config();
    cfg.budget.maxFilingFeesPerDayUsd = 40; // room for one appeal fee
    const picks = samples.filter((s) => [3, 5].includes(s.n));
    const rs = await escalateAll(picks.map((s) => ({ case: s.case, decision: s.decision })), ctx({ config: cfg }));
    const by = Object.fromEntries(rs.map((r) => [r.caseId, r]));
    const five = by["case_placeholder_PH-0005"]!; // EV ≈ $147
    const three = by["case_placeholder_PH-0003"]!; // EV ≈ $102
    expect(five.status).toBe("ESCALATE");
    expect(three.status).toBe("PENDING");
    expect(three.reasonCodes).toContain("P_BUDGET");
    expect(three.requeueOn).toBe("2026-11-06");
  });
});
