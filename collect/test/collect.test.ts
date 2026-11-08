/** Collect: sample paths, autonomy, honest numbers, fee bounds, quote checks, board hookup (synthetic data). */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { applyPayment, caseFromCard, cardWrites, feeFromAuthorization, latestInvoiceState, parseBillComment, parseHandoff } from "../src/board.js";
import { loadConfig, parseConfig } from "../src/config.js";
import { collect, collectAll } from "../src/pipeline.js";
import { MockBillReader } from "../src/reader/mock.js";
import { ProvidedBillReader } from "../src/reader/provided.js";
import { STATUSES, type CollectResult } from "../src/types.js";
import { addDays } from "../src/util.js";
import { buildSamples, SAMPLE_TODAY } from "../scripts/samples.js";

const cfg = () => loadConfig("config/collect.placeholder.json");
const ctx = (over: Record<string, unknown> = {}) => ({ config: cfg(), today: SAMPLE_TODAY, reader: new MockBillReader(), ...over });
const samples = buildSamples();
const run = (n: number, over: Record<string, unknown> = {}) => {
  const s = samples.find((x) => x.n === n)!;
  return collect(s.case, s.bill, ctx(over));
};

describe("sample paths", () => {
  for (const s of samples)
    it(`${s.n}. ${s.title} → ${s.expect.status} (${s.expect.code})`, async () => {
      const r = await collect(s.case, s.bill, ctx());
      expect(r.status).toBe(s.expect.status);
      expect(r.reasonCodes).toContain(s.expect.code);
      for (const f of s.expect.flags ?? []) expect(r.flags).toContain(f);
      if (s.expect.fee !== undefined) expect(r.invoice?.amount).toBe(s.expect.fee);
    });

  it("an issued invoice carries an exact payment request", async () => {
    const r = await run(3);
    expect(r.paymentRequest).toEqual({ amountCents: 48000, currency: "usd", reference: r.invoice!.number, description: expect.stringContaining(r.invoice!.number) });
    expect(r.invoice).toMatchObject({ issuedOn: SAMPLE_TODAY, dueOn: addDays(SAMPLE_TODAY, 30), reminders: [] });
  });
});

function rng(seed: number) {
  return () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
}

describe("autonomy and money safety", () => {
  it("every sample and 200 random cases end in an automatic status; fees stay within bounds and need a bill", async () => {
    const r = rng(7);
    const items = [...samples.map((s) => ({ case: s.case, bill: s.bill }))];
    for (let i = 0; i < 200; i++) {
      const base = samples[Math.floor(r() * samples.length)]!;
      const old = 100_000 + Math.floor(r() * 3_000_000);
      const won = Math.floor(old * (0.5 + r() * 0.5));
      const c = { ...base.case, caseId: `rand-${i}`, oldAssessedValue: old, wonAssessedValue: won, feePct: r() * 0.4, taxRate: 0.005 + r() * 0.03, wonOn: addDays("2026-06-01", Math.floor(r() * 180)) };
      const shown = r() < 0.5 ? won : Math.floor(won + (old - won) * r() * 1.2);
      const bill = r() < 0.3 ? null : { docId: `B-${i}`, caseId: r() < 0.95 ? c.caseId : "other", receivedOn: "2026-12-01", text: r() < 0.15 ? "Account updated." : `Corrected assessed value: $${shown.toLocaleString("en-US")}` };
      items.push({ case: r() < 0.2 ? { ...c, invoice: { number: `I-${i}`, issuedOn: addDays(SAMPLE_TODAY, -Math.floor(r() * 90)), dueOn: SAMPLE_TODAY, amount: 100, reminders: [] } } : c, bill } as never);
    }
    const rs = await collectAll(items, ctx());
    for (const x of rs) {
      expect(STATUSES).toContain(x.status);
      expect(x.reasonCodes.every((c) => /^[IDCVP]_/.test(c))).toBe(true);
      if (x.status === "WAITING") expect(x.requeueOn).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      if (x.reasonCodes.includes("V_INVOICE_ISSUED")) {
        expect(x.invoice!.amount).toBeLessThanOrEqual(cfg().fee.maxFee);
        expect(x.invoice!.amount).toBeGreaterThanOrEqual(cfg().fee.minFee);
        expect(x.bill.docId).not.toBeNull();
      }
    }
  });

  it("engine code has no review queue, approval step, or jurisdiction names", () => {
    const list = (d: string): string[] => readdirSync(d).flatMap((n) => (statSync(join(d, n)).isDirectory() ? list(join(d, n)) : n.endsWith(".ts") ? [join(d, n)] : []));
    for (const f of list("src")) {
      const t = readFileSync(f, "utf8");
      expect(t, f).not.toMatch(/NEEDS_REVIEW|review queue|approvalRequired/i);
      expect(t, f).not.toMatch(/\b(florida|california|texas|hendry|bay county|miami|broward)\b|county of|state of/i);
    }
  });

  it("owner messages only contain dollar figures from verified fields", async () => {
    const rs = await collectAll(samples.map((s) => ({ case: s.case, bill: s.bill })), ctx());
    for (const x of rs) {
      if (!x.ownerMessage) continue;
      const s = samples.find((y) => y.case.caseId === x.caseId)!;
      const ok = new Set([s.case.oldAssessedValue, s.case.wonAssessedValue, x.bill.verified?.assessedValue, x.bill.verified?.originalTax, x.bill.verified?.correctedTax, x.savings?.annual, x.invoice?.amount].filter((v): v is number => typeof v === "number"));
      for (const m of x.ownerMessage.body.matchAll(/\$([\d,]+(?:\.\d+)?)/g)) expect(ok.has(Number(m[1]!.replace(/,/g, ""))), `${x.caseId}: ${m[0]}`).toBe(true);
    }
  });

  it("is deterministic apart from decidedAt", async () => {
    const strip = (rs: CollectResult[]) => rs.map((r) => ({ ...r, audit: { ...r.audit, decidedAt: "" } }));
    const items = samples.map((s) => ({ case: s.case, bill: s.bill }));
    expect(strip(await collectAll(items, ctx()))).toEqual(strip(await collectAll(items, ctx())));
  });
});

describe("bill readings are quote-checked", () => {
  it("made-up tax amounts cannot inflate the fee", async () => {
    const s = samples.find((x) => x.n === 4)!; // bill shows only the value
    const fake = { assessedValue: 420_000, originalTax: 50_000, correctedTax: 1_000, confidence: 0.95, evidence: [{ field: "assessedValue", quote: "Corrected assessed value: $420,000" }, { field: "originalTax", quote: "Original tax amount: $50,000" }, { field: "correctedTax", quote: "Corrected tax amount: $1,000" }] };
    const r = await collect(s.case, s.bill, ctx({ reader: new ProvidedBillReader(fake) }));
    expect(r.bill.droppedFields).toEqual(["originalTax", "correctedTax"]);
    expect(r.invoice!.amount).toBe(480);
    expect(r.flags).toContain("F_SAVINGS_ESTIMATED");
  });
});

describe("config validation", () => {
  it("lists bad paths", () => {
    const bad = JSON.parse(readFileSync("config/collect.placeholder.json", "utf8"));
    bad.fee.minFee = 9999;
    bad.invoice.reminderDays = [30, 14];
    expect(() => parseConfig(bad, "bad")).toThrow(/fee\.minFee[\s\S]*invoice\.reminderDays/);
  });
});

describe("board hookup", () => {
  const body = "From Escalate: W_FULL_WIN\ncollect-handoff · case FL-99-2026-X · old 500000 · won 420000 · decided 2026-10-30 · letter msg_1 · code W_FULL_WIN\n";
  const q = { find_case_id: "FL-99-2026-X", parcelId: "X", jurisdictionId: "placeholder", address: "1 Sample St", taxRate: 0.02, owner: { names: ["S"], type: "individual" } };

  it("parses the handoff, bill comment and authorization fee", () => {
    expect(parseHandoff(body)).toEqual({ caseId: "FL-99-2026-X", oldValue: 500000, wonValue: 420000, wonOn: "2026-10-30", decisionId: "msg_1", wonCode: "W_FULL_WIN" });
    expect(parseHandoff("nothing")).toBeNull();
    expect(parseBillComment("tax-bill · case FL-99-2026-X · received 2026-12-05 · doc_1\nCorrected assessed value: $420,000")).toMatchObject({ caseId: "FL-99-2026-X", docId: "doc_1", text: "Corrected assessed value: $420,000" });
    expect(feeFromAuthorization("authorization: case_id FL-99-2026-X · scope vab_petition · fee 25%", "FL-99-2026-X")).toBe(0.25);
    expect(feeFromAuthorization("authorization: case_id OTHER · fee 25%", "FL-99-2026-X")).toBeNull();
  });

  it("invoices, then records payment through the invoice state, ending PAID", async () => {
    const h = parseHandoff(body)!;
    const bill = { ...parseBillComment("tax-bill · case FL-99-2026-X · received 2026-12-05 · doc_1\nCorrected assessed value: $420,000")! };
    const first = await collect(caseFromCard(h, q, cfg()), bill, ctx());
    expect(first.status).toBe("INVOICED");
    expect(first.flags).toContain("F_DEFAULT_AUTHORIZATION");
    const w = cardWrites(first, "crd_c");
    expect(w[0]!.op).toBe("comment");
    expect(w[1]).toMatchObject({ op: "update", status: "blocked", note: expect.stringMatching(/^INVOICED · \$480 · /) });
    const state = latestInvoiceState([(w[0] as { body: string }).body]);
    expect(state?.number).toBe(first.invoice!.number);
    const paid = await collect(caseFromCard(h, q, cfg(), { invoice: applyPayment(state, { paidOn: "2026-12-20", ref: "pi_123", link: "https://pay.example/x" }) }), null, ctx({ today: "2026-12-21" }));
    expect(paid.status).toBe("PAID");
    expect(cardWrites(paid, "crd_c")[1]).toMatchObject({ status: "done", note: expect.stringMatching(/^PAID · \$480/) });
  });
});
