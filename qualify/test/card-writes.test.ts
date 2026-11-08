/** Board writes the Qualify agent sends (synthetic data). */
import { describe, expect, it } from "vitest";
import { cardWrites } from "../src/adapters/card-writes.js";

const handoff = {
  replay: true,
  cases: [
    { find_case_id: "XX-1", status: "QUALIFIED", summary: "Assessed $400,000 vs cautious $330,000", flags: [], reasonCodes: [], annualSavings: 1366.4, fee: 409.9, pWin: 0.72, route: { form: "DR-486", deadline: "2026-09-09" }, requalifyOn: null, releaseDate: "2026-08-25" },
    { find_case_id: "XX-2", status: "QUALIFIED", summary: "s2", flags: [], reasonCodes: [], annualSavings: 900, fee: 270, pWin: 0.6, route: { form: "DR-486", deadline: "2026-09-09" }, requalifyOn: null, releaseDate: null },
    { find_case_id: "XX-3", status: "NEEDS_REVIEW", summary: "s3", flags: ["F_RECENT_TRANSFER"], reasonCodes: [], annualSavings: null, fee: null, pWin: null, route: null, requalifyOn: null, releaseDate: null },
    { find_case_id: "XX-4", status: "REJECTED", summary: "s4", flags: [], reasonCodes: ["V_LOW_CONFIDENCE"], annualSavings: null, fee: null, pWin: null, route: null, requalifyOn: null, releaseDate: null },
  ],
};

describe("cardWrites", () => {
  it("builds one complete update per card, with a comment fallback for done cards", () => {
    const [q] = cardWrites(handoff, ["crd_a=XX-1"]);
    expect(q).toMatchObject({ card_id: "crd_a", case_id: "XX-1", write: { op: "update", card_id: "crd_a", status: "done" }, if_done: { op: "comment", card_id: "crd_a" } });
    const note = (q!.write as { note: string }).note;
    expect(note).toBe("QUALIFIED (replay) · savings $1,366/yr · fee $410 · P(win) 0.72 · DR-486 due 2026-09-09 · released 2026-08-25 · Assessed $400,000 vs cautious $330,000");
    expect((q!.if_done as { body: string }).body).toBe(note);
    expect(note).not.toContain("```");
  });

  it("marks queued, review and rejected cases with the right status word", () => {
    const [queued, review, rejected] = cardWrites(handoff, ["crd_b=XX-2", "crd_c=XX-3", "crd_d=XX-4"]);
    expect((queued!.write as { note: string }).note).toContain(" · queued · ");
    expect(review!.write).toMatchObject({ status: "blocked", note: "NEEDS_REVIEW (replay) · F_RECENT_TRANSFER · s3" });
    expect(rejected!.write).toMatchObject({ status: "done", note: "REJECTED (replay) · V_LOW_CONFIDENCE · s4" });
  });

  it("labels replay per case and holds no-desk cases instead of rejecting them", () => {
    const h = {
      cases: [
        { ...handoff.cases[1]!, find_case_id: "LIVE", replayed: false },
        { ...handoff.cases[1]!, find_case_id: "OLD", replayed: true },
        { ...handoff.cases[3]!, find_case_id: "IL", status: "REJECTED", reasonCodes: ["E_NO_DESK"], jurisdictionId: "IL-31" },
      ],
    };
    const [live, old, il] = cardWrites(h, ["c1=LIVE", "c2=OLD", "c3=IL"]);
    expect((live!.write as { note: string }).note).toMatch(/^QUALIFIED · /);
    expect((old!.write as { note: string }).note).toMatch(/^QUALIFIED \(replay\) · /);
    expect(il!.write).toMatchObject({ status: "blocked", note: expect.stringMatching(/^NO_DESK · no Qualify desk settings for IL yet/) });
  });

  it("refuses unknown cases and malformed pairs instead of guessing", () => {
    const [unknown, bad] = cardWrites(handoff, ["crd_e=NOPE", "crd_f"]);
    expect(unknown).toMatchObject({ card_id: "crd_e", error: expect.stringContaining("leave this card untouched") });
    expect(unknown!.write).toBeUndefined();
    expect(bad).toMatchObject({ card_id: "crd_f", error: expect.any(String) });
  });
});
