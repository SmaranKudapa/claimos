import { describe, expect, it } from "vitest";
import { qualify } from "../src/pipeline.js";
import { applyReview, ReviewError } from "../src/review.js";
import { NOW, candidate, comps, ctx } from "./helpers.js";

const flagged = () => candidate({ owner: { names: ["A Trust"], type: "trust", mailingAddress: "x" }, assessment: { assessedValue: 1_150_000 } });

describe("human review", () => {
  it("approve turns NEEDS_REVIEW into QUALIFIED and records who", async () => {
    const r = await qualify(flagged(), ctx(), { now: NOW });
    expect(r.status).toBe("NEEDS_REVIEW");
    const a = await applyReview(r, { type: "approve", note: "trustee confirmed" }, "sam", { now: NOW });
    expect(a.status).toBe("QUALIFIED");
    expect(a.audit.decidedBy).toBe("human:sam");
    expect(a.audit.review).toMatchObject({ by: "sam", action: "approve", note: "trustee confirmed" });
  });
  it("cannot approve anything that isn't in the review queue", async () => {
    const r = await qualify(candidate({ assessment: { assessedValue: 600_000 } }), ctx(), { now: NOW });
    await expect(applyReview(r, { type: "approve" }, "sam")).rejects.toBeInstanceOf(ReviewError);
  });
  it("reject needs a known reason code", async () => {
    const r = await qualify(flagged(), ctx(), { now: NOW });
    await expect(applyReview(r, { type: "reject", code: "NOPE" }, "sam")).rejects.toBeInstanceOf(ReviewError);
    const x = await applyReview(r, { type: "reject", code: "F_COMPLEX_OWNER" }, "sam", { now: NOW });
    expect(x.status).toBe("REJECTED");
    expect(x.reasonCodes).toEqual(["H_REJECTED", "F_COMPLEX_OWNER"]);
  });
  it("edit re-runs without the LLM and stays in the queue", async () => {
    const ks = [...comps(650, 1400, 5), { ...comps(650, 1400, 1)[0]!, compId: "BAD", price: 400_000 }];
    const raw = candidate({ comps: ks, owner: { names: ["A Trust"], type: "trust", mailingAddress: "x" }, assessment: { assessedValue: 1_150_000 } });
    const c = ctx();
    const r = await qualify(raw, c, { now: NOW });
    const e = await applyReview(r, { type: "edit", excludeComps: ["BAD"] }, "sam", { ctx: c, candidate: raw, now: NOW });
    expect(e.valuation!.compsExcluded).toContain("BAD");
    expect(e.status).toBe("NEEDS_REVIEW");
    expect(e.llm?.skippedReason).toMatch(/human review/);
  });
});
