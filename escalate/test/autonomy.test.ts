/** No human in the loop, no dead ends, determinism, and no jurisdiction names in engine code. */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { escalate, escalateAll } from "../src/pipeline.js";
import { STATUSES, type EscalateResult } from "../src/types.js";
import { buildSamples } from "../scripts/samples.js";
import { addDays } from "../src/util.js";
import { ctx, FailingReader } from "./helpers.js";

const samples = buildSamples();

/** Deterministic pseudo-random generator. */
function rng(seed: number) {
  return () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
}

function randomDeliveries(n: number) {
  const r = rng(42);
  const pick = <T>(xs: T[]) => xs[Math.floor(r() * xs.length)]!;
  const bodies = [
    (v: number) => `The request is granted in full. The assessed value is reduced to $${v.toLocaleString("en-US")}.`,
    (v: number) => `The request is granted in part. The assessed value is reduced to $${v.toLocaleString("en-US")}.`,
    () => "The request is denied. The board found that the comparable sales submitted were not comparable to the subject property.",
    () => "The request is denied. The board finds the market evidence supports the assessed value.",
    () => "The request is denied. The board found insufficient evidence to change the value.",
    () => "A hearing has been scheduled for 2026-12-01. No decision has been made yet.",
    () => "Your request is dismissed because the form was not signed by the owner.",
    () => "Your request is dismissed because it was filed after the filing deadline.",
    () => "We have received your correspondence. Further information will follow.",
    () => "",
    (v: number) => `The value was set at $${v.toLocaleString("en-US")} after review.`,
  ];
  return Array.from({ length: n }, (_, i) => {
    const s = pick(samples);
    const assessed = 200_000 + Math.floor(r() * 800_000);
    const target = Math.floor(assessed * (0.6 + r() * 0.35));
    const level = pick(["review", "appeal", "board", "court", "unknown_level"]);
    const decided = addDays("2026-08-01", Math.floor(r() * 100));
    const c = {
      ...s.case,
      caseId: `rand-${i}`,
      assessedValue: assessed,
      targetValue: target,
      currentLevel: level,
      qualify: r() < 0.3 ? undefined : { pWin: r() },
      authorization: { signedOn: "2026-08-01", feePct: 0.3, scope: pick([["all_levels"], ["review"], ["review", "appeal"]]), escalation: r() < 0.5 ? undefined : { appealPartialIfRemainingAnnualAbove: Math.floor(r() * 3000), acceptReopenRisk: r() < 0.5 } },
      readAttempts: r() < 0.3 ? [{ decisionId: `RD-${i}`, attempts: Math.floor(r() * 3), firstPendingOn: addDays("2026-10-20", Math.floor(r() * 20)) }] : [],
    };
    const text = pick(bodies)(Math.floor(target + (assessed - target) * r() * 1.4));
    const d = { decisionId: `RD-${i}`, caseId: r() < 0.95 ? c.caseId : "someone-else", level: r() < 0.95 ? level : "review", receivedOn: addDays(decided, 3), channel: "mail", text: text ? `Decision date: ${decided}\n${text}` : "", attachments: [] };
    return { case: c, decision: d };
  });
}

describe("no human in the loop", () => {
  it("every sample and 300 random cases end in an automatic status", async () => {
    const all = [...samples.map((s) => ({ case: s.case, decision: s.decision })), ...randomDeliveries(300)];
    const rs = await escalateAll(all, ctx());
    expect(rs).toHaveLength(all.length);
    for (const r of rs) {
      expect(STATUSES).toContain(r.status);
      expect(r.reasonCodes.every((c) => /^[IPCWA]_/.test(c))).toBe(true);
      if (r.status === "PENDING") expect(r.requeueOn).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      if (r.status !== "INCOMPLETE") expect(r.ownerUpdate?.autoSend).toBe(true);
    }
  });

  it("the engine code has no review queue, approval step or person-routing code", () => {
    const files = listTs("src");
    for (const f of files) {
      const t = readFileSync(f, "utf8");
      expect(t, f).not.toMatch(/NEEDS_REVIEW|review queue|approvalRequired/i);
      expect(t, f).not.toMatch(/["'`](R|O)_[A-Z]/);
    }
  });
});

describe("no dead ends", () => {
  async function loop(c: Record<string, unknown>, d: Record<string, unknown>, reader = ctx().reader) {
    let today = "2026-11-05";
    let current = { ...c };
    const seen: EscalateResult[] = [];
    for (let i = 0; i < 30; i++) {
      const r = await escalate(current, d, ctx({ today, reader }));
      seen.push(r);
      if (r.status !== "PENDING" || r.reasonCodes.includes("P_HEARING_SCHEDULED")) return seen;
      expect(r.requeueOn! > today).toBe(true);
      today = r.requeueOn!;
      if (r.readState) current = { ...current, readAttempts: [r.readState] };
    }
    return seen;
  }

  it("an unclear letter is clarified, then resolves within clarifyMaxDays", async () => {
    const s = samples.find((x) => x.n === 13)!;
    const seen = await loop(s.case, s.decision);
    const last = seen.at(-1)!;
    expect(last.status).not.toBe("PENDING");
    expect(last.flags).toContain("F_ASSUMED_DENIAL");
    expect(seen.length).toBeLessThanOrEqual(1 + ctx().config.reader.clarifyMaxDays);
  });

  it("a failing reader retries, then resolves within maxReadAttempts plus the clarify window", async () => {
    const s = samples.find((x) => x.n === 5)!;
    const seen = await loop(s.case, s.decision, new FailingReader());
    expect(seen[0]!.reasonCodes).toContain("P_READ_RETRY");
    expect(seen.at(-1)!.status).not.toBe("PENDING");
    expect(seen.length).toBeLessThanOrEqual(ctx().config.reader.maxReadAttempts + ctx().config.reader.clarifyMaxDays + 1);
  });
});

describe("determinism", () => {
  it("same inputs and today give the same output apart from decidedAt", async () => {
    const strip = (rs: EscalateResult[]) => rs.map((r) => ({ ...r, audit: { ...r.audit, decidedAt: "" } }));
    const input = samples.map((s) => ({ case: s.case, decision: s.decision }));
    const a = strip(await escalateAll(input, ctx()));
    const b = strip(await escalateAll(input, ctx()));
    expect(a).toEqual(b);
    expect(a[0]!.audit.inputHash).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe("engine code never names a jurisdiction", () => {
  it("no state names or 'county of' / 'state of' in src/", () => {
    const names = /\b(florida|california|texas|georgia|new york|illinois|cook county|hendry|bay county|miami|broward|volusia)\b|county of|state of/i;
    for (const f of listTs("src")) expect(readFileSync(f, "utf8"), f).not.toMatch(names);
  });
});

function listTs(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? listTs(p) : p.endsWith(".ts") ? [p] : [];
  });
}
