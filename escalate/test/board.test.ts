/** Board hookup: Chase's decision-letter comment in, an escalate-result comment out (synthetic data). */
import { describe, expect, it } from "vitest";
import { caseFromQualify, decisionFromComment, parseLetterComment, resultComment, type QualifyHandoffEntry } from "../src/board.js";
import { escalate } from "../src/pipeline.js";
import { ProvidedReader } from "../src/reader/provided.js";
import { ReaderError } from "../src/reader/types.js";
import { ctx, floridaConfig } from "./helpers.js";

const entry: QualifyHandoffEntry = {
  find_case_id: "FL-99-2026-DEMO1",
  parcelId: "DEMO1",
  jurisdictionId: "FL-99",
  address: "1 Sample St, Testville",
  judgedAsOf: "2026-08-25",
  pWin: 0.66,
  route: { id: "vab_petition" },
  assessedValue: 500_000,
  targetValue: 420_000,
  taxRate: 0.015,
  owner: { names: ["SAMPLE OWNER"], type: "individual" },
};
const comment = (body: string, head = "decision-letter · case FL-99-2026-DEMO1 · level vab_petition · received 2026-11-03 · msg_1") => `${head}\n${body}`;

async function run(body: string, reading?: unknown) {
  const cfg = floridaConfig();
  const letter = parseLetterComment(comment(body))!;
  const c = caseFromQualify(entry, letter, cfg);
  return escalate(c, decisionFromComment(letter, null), ctx({ config: cfg, ...(reading ? { reader: new ProvidedReader(reading) } : {}) }));
}

describe("decision-letter comments", () => {
  it("parses the agreed shape and the full letter text", () => {
    const l = parseLetterComment(comment("Line one.\nThe petition is denied."))!;
    expect(l).toEqual({ caseId: "FL-99-2026-DEMO1", level: "vab_petition", receivedOn: "2026-11-03", messageId: "msg_1", text: "Line one.\nThe petition is denied." });
    expect(parseLetterComment(comment("x", "decision-letter · case unknown · level unknown · received 2026-11-03 · m2"))).toMatchObject({ caseId: null, level: null });
    expect(parseLetterComment("decision: denied · value none · 2026-10-30 · m3")).toBeNull();
  });
});

describe("agent mode", () => {
  it("a board denial in Florida is referred out, using the desk's default authorization", async () => {
    const r = await run("Decision date: 2026-10-30\nThe petition is denied.");
    expect(r.status).toBe("CLOSED");
    expect(r.reasonCodes).toContain("C_REFER_OUT");
    expect(r.flags).toContain("F_DEFAULT_AUTHORIZATION");
  });

  it("a full win is collected", async () => {
    const r = await run("Decision date: 2026-10-30\nThe petition is granted in full. The assessed value is reduced to $420,000.");
    expect(r.status).toBe("COLLECT");
  });

  it("the agent's reading is quote-checked: a made-up quote cannot turn a denial into a win", async () => {
    const fake = { outcome: "full_win", newAssessedValue: 420_000, reasonCategories: [], confidence: 0.95, evidence: [{ field: "outcome", quote: "granted in full" }, { field: "newAssessedValue", quote: "reduced to $420,000" }] };
    const r = await run("Decision date: 2026-10-30\nThe petition is denied.", fake);
    expect(r.status).not.toBe("COLLECT");
    expect(r.reading.droppedFields).toEqual(expect.arrayContaining(["outcome", "newAssessedValue"]));
  });

  it("rejects an invalid supplied reading", () => {
    expect(() => new ProvidedReader({ outcome: "won" })).toThrow(ReaderError);
  });

  it("writes one escalate-result comment with the status, next step and owner update", async () => {
    const r = await run("Decision date: 2026-10-30\nThe petition is granted in full. The assessed value is reduced to $420,000.");
    const w = resultComment(r, "crd_1");
    expect(w).toMatchObject({ op: "comment", card_id: "crd_1" });
    const lines = w.body.split("\n");
    expect(lines[0]).toBe("escalate-result · COLLECT · W_FULL_WIN · msg_1");
    expect(w.body).toContain("next: Collect");
    expect(w.body).toMatch(/owner-update \(mail, auto-send\)/);
  });
});
