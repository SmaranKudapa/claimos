/** Board writes per status: result comment, Waiting-on card update, Evidence hand-off (synthetic data). */
import { describe, expect, it } from "vitest";
import { caseFromQualify, cardWrites, decisionFromComment, findCaseBlock, parseLetterComment, type QualifyHandoffEntry } from "../src/board.js";
import { escalate } from "../src/pipeline.js";
import { ctx, floridaConfig } from "./helpers.js";

const caseJson = { schema_version: 2, case_id: "FL-99-2026-DEMO1", status: "candidate", property: { address: "1 SAMPLE ST" } };
const cardBody = `Petition filed 2026-08-20, receipt R-1.\nfollow_up: Sample VAB vab@example.org, every 7 days, last chased never\n\n\`\`\`json\n${JSON.stringify(caseJson)}\n\`\`\``;
const entry: QualifyHandoffEntry = {
  find_case_id: "FL-99-2026-DEMO1", parcelId: "DEMO1", jurisdictionId: "FL-99", address: "1 Sample St, Testville",
  judgedAsOf: "2026-08-25", pWin: 0.66, route: { id: "vab_petition" }, assessedValue: 500_000, targetValue: 420_000, taxRate: 0.015,
  owner: { names: ["SAMPLE OWNER"], type: "individual" },
};

async function writesFor(body: string, cardText: string | undefined = cardBody) {
  const cfg = floridaConfig();
  const letter = parseLetterComment(`decision-letter · case FL-99-2026-DEMO1 · level vab_petition · received 2026-11-03 · msg_9\n${body}`)!;
  const r = await escalate(caseFromQualify(entry, letter, cfg), decisionFromComment(letter, null), ctx({ config: cfg }));
  return { r, ...cardWrites(r, { id: "crd_w", ...(cardText ? { body: cardText } : {}) }) };
}

describe("findCaseBlock", () => {
  it("takes the last valid json block from a card body", () => {
    expect(JSON.parse(findCaseBlock(cardBody)!)).toEqual(caseJson);
    expect(findCaseBlock("no block")).toBeNull();
    expect(findCaseBlock("```json\nnot json\n```")).toBeNull();
  });
});

describe("cardWrites", () => {
  it("COLLECT: comment, the card goes to done with a WON note, and a Collect card carries the handoff", async () => {
    const { r, writes } = await writesFor("Decision date: 2026-10-30\nThe petition is granted in full. The assessed value is reduced to $420,000.");
    expect(r.status).toBe("COLLECT");
    expect(writes.map((w) => w.op)).toEqual(["comment", "update", "create"]);
    expect(writes[1]).toMatchObject({ op: "update", card_id: "crd_w", status: "done", note: expect.stringMatching(/^WON · W_FULL_WIN · /) });
    const col = writes[2] as Extract<(typeof writes)[number], { op: "create" }>;
    expect(col).toMatchObject({ assignee: "collect", status: "todo", key: "escalate-collect-FL-99-2026-DEMO1-msg_9", title: "Collect · 1 Sample St, Testville · FL-99-2026-DEMO1" });
    expect(col.body).toContain("collect-handoff · case FL-99-2026-DEMO1 · old 500000 · won 420000 · decided 2026-10-30 · letter msg_9 · code W_FULL_WIN");
    expect(JSON.parse(findCaseBlock(col.body)!)).toEqual(caseJson);
  });

  it("CLOSED: the card goes to done with a STOPPED note", async () => {
    const { writes } = await writesFor("Decision date: 2026-10-30\nThe petition is denied.");
    expect(writes[1]).toMatchObject({ status: "done", note: expect.stringMatching(/^STOPPED · C_REFER_OUT/) });
  });

  it("ESCALATE: the card stays blocked with an APPEAL note, and an Evidence card carries the case block", async () => {
    const { r, writes } = await writesFor("Decision date: 2026-11-02\nThe petition is dismissed because it was not signed by the petitioner.");
    expect(r.reasonCodes).toContain("A_REFILE_SAME_LEVEL");
    expect(writes.map((w) => w.op)).toEqual(["comment", "update", "create"]);
    expect(writes[1]).toMatchObject({ status: "blocked", note: expect.stringMatching(/^APPEAL · A_REFILE_SAME_LEVEL/) });
    const ev = writes[2] as Extract<(typeof writes)[number], { op: "create" }>;
    expect(ev).toMatchObject({ assignee: "evidence", status: "todo", key: "escalate-evidence-FL-99-2026-DEMO1-msg_9" });
    expect(ev.title).toBe("Evidence · 1 Sample St, Testville · FL-99-2026-DEMO1");
    expect(ev.body).toContain("fix: missing_signature");
    expect(ev.body).toContain("petition_deadline: 2026-11-12");
    expect(JSON.parse(findCaseBlock(ev.body)!)).toEqual(caseJson);
  });

  it("ESCALATE without a case block on the card: no Evidence card, and says why", async () => {
    const { writes, notes } = await writesFor("Decision date: 2026-11-02\nThe petition is dismissed because it was not signed by the petitioner.", "no json here");
    expect(writes.map((w) => w.op)).toEqual(["comment", "update"]);
    expect(notes[0]).toMatch(/Evidence hand-off card not created/);
  });

  it("PENDING: only the comment; the card is left for Chase", async () => {
    const { r, writes } = await writesFor("A hearing has been scheduled for 2026-11-20. No decision has been made yet.");
    expect(r.status).toBe("PENDING");
    expect(writes.map((w) => w.op)).toEqual(["comment"]);
  });
});
