#!/usr/bin/env node
/**
 * Collect CLI.
 *
 *   collect run    --cases <file> --config <file> [--today YYYY-MM-DD] [--out out/collect-results.json] [--audit out/audit.jsonl] [--json]
 *                  (cases file: [{ "case": {...}, "bill": {...} | null }], offline bill reader)
 *   collect show   --results <file> --case <caseId> [--json]
 *   collect cases  --results <file> --export <file>                 (UI records with "Collect" beats)
 *   collect from-board --card <card id> --card-body <file> --qualify-handoff <handoff.json> --config <file>
 *                  [--bill <file>] [--bill-reading <file>] [--invoice-state <json>] [--authorization <file | line>]
 *                  [--payment-link <url> [--payment-link-id <id>]] [--paid-on YYYY-MM-DD --payment-ref <ref>] [--today YYYY-MM-DD]
 *                  (agent mode: one Collect card in, the exact board writes out)
 *   collect validate-config --config <file>
 *   collect codes
 *
 * There is deliberately no review or approve command: every result is acted on automatically.
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { parseArgs } from "node:util";
import { applyPayment, caseFromCard, cardWrites, feeFromAuthorization, parseBillComment, parseHandoff, type QualifyEntry } from "./board.js";
import { toCaseRecordPatch, toCollectBeat } from "./case.js";
import { CODES } from "./codes.js";
import { loadConfig } from "./config.js";
import { collect, collectAll, type CollectContext } from "./pipeline.js";
import { ProvidedBillReader, ReadingsByBill } from "./reader/provided.js";
import type { CollectResult, InvoiceState } from "./types.js";
import { todayIn } from "./util.js";

const [cmd, ...rest] = process.argv.slice(2);
const { values: a } = parseArgs({
  args: rest,
  options: {
    cases: { type: "string" },
    config: { type: "string" },
    today: { type: "string" },
    out: { type: "string", default: "out/collect-results.json" },
    audit: { type: "string", default: "out/audit.jsonl" },
    results: { type: "string", default: "out/collect-results.json" },
    case: { type: "string" },
    export: { type: "string" },
    json: { type: "boolean" },
    card: { type: "string" },
    "card-body": { type: "string" },
    "qualify-handoff": { type: "string" },
    bill: { type: "string" },
    "bill-reading": { type: "string" },
    "invoice-state": { type: "string" },
    authorization: { type: "string" },
    "payment-link": { type: "string" },
    "payment-link-id": { type: "string" },
    "paid-on": { type: "string" },
    "payment-ref": { type: "string" },
  },
  allowPositionals: false,
});

function fail(msg: string): never {
  console.error(`error: ${msg}`);
  process.exit(2);
}
const need = (v: string | undefined, name: string) => v ?? fail(`--${name} is required`);
const readJson = (p: string) => JSON.parse(readFileSync(p, "utf8"));
const textOf = (v: string) => (existsSync(v) ? readFileSync(v, "utf8") : v);
function writeJson(p: string, v: unknown) {
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(v, null, 2) + "\n");
}
const pad = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s.padEnd(n));

async function run() {
  const config = loadConfig(need(a.config, "config"));
  const today = a.today ?? todayIn(process.env.COLLECT_TIMEZONE);
  const items = readJson(need(a.cases, "cases"));
  if (!Array.isArray(items)) fail("cases file must be a JSON array of { case, bill, reading }");
  const readings = Object.fromEntries(items.filter((i: { bill?: { docId?: string } | null; reading?: unknown }) => i.bill?.docId && i.reading).map((i: { bill: { docId: string }; reading: unknown }) => [i.bill.docId, i.reading]));
  const results = await collectAll(items, { config, today, reader: new ReadingsByBill(readings) });
  writeJson(a.out!, { runAt: new Date().toISOString(), today, configVersion: config.version, results });
  mkdirSync(dirname(a.audit!), { recursive: true });
  for (const r of results) appendFileSync(a.audit!, JSON.stringify({ at: r.audit.decidedAt, step: "collect", caseId: r.caseId, status: r.status, reasonCodes: r.reasonCodes, flags: r.flags, summary: r.summary, configVersion: r.audit.configVersion, inputHash: r.audit.inputHash }) + "\n");
  if (a.json) return console.log(JSON.stringify(results, null, 2));
  console.log(`Collect · ${config.jurisdictionId} · config ${config.version} · today ${today}\n`);
  console.log([pad("STATUS", 11), pad("CASE", 26), pad("CODE", 24), pad("SAVINGS/YR", 11), pad("FEE", 10), pad("NEXT", 22), "FLAGS"].join(" "));
  console.log("─".repeat(130));
  for (const r of results) {
    const code = r.summary.split(" · ")[1] ?? "";
    console.log([pad(r.status, 11), pad(r.caseId, 26), pad(code, 24), pad(r.savings ? `$${r.savings.annual}` : "—", 11), pad(r.invoice ? `$${r.invoice.amount}` : "—", 10), pad(r.requeueOn ? `check ${r.requeueOn}` : "—", 22), r.flags.join(",")].join(" "));
  }
  const counts: Record<string, number> = {};
  for (const r of results) counts[r.status] = (counts[r.status] ?? 0) + 1;
  const invoiced = results.filter((r) => r.reasonCodes.includes("V_INVOICE_ISSUED")).reduce((s, r) => s + (r.invoice?.amount ?? 0), 0);
  console.log("─".repeat(130));
  console.log(`${Object.entries(counts).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(" · ")} · invoiced today $${invoiced.toFixed(2)}`);
  console.log(`\nWrote ${a.out} and appended ${results.length} record(s) to ${a.audit}`);
}

function show() {
  const r = (readJson(a.results!) as { results: CollectResult[] }).results.find((x) => x.caseId === need(a.case, "case"));
  if (!r) fail(`no case ${a.case}`);
  if (a.json) return console.log(JSON.stringify(r, null, 2));
  console.log(`${r!.caseId} · ${r!.address}\n${r!.summary}\nCodes: ${r!.reasonCodes.join(", ")}${r!.flags.length ? ` · Flags: ${r!.flags.join(", ")}` : ""}`);
  if (r!.bill.verified) {
    console.log(`\nBill ${r!.bill.docId}:`);
    for (const e of r!.bill.verified.evidence) console.log(`  ${e.field}: "${e.quote}"`);
    if (r!.bill.droppedFields.length) console.log(`  dropped (quote not in bill): ${r!.bill.droppedFields.join(", ")}`);
  }
  if (r!.savings) console.log(`\nSavings $${r!.savings.annual}/yr (${r!.savings.fromBill ? "bill" : "estimate"})${r!.fee ? ` · fee $${r!.fee.computed}${r!.fee.capped ? ` capped $${r!.fee.charged}` : ""}` : ""}`);
  if (r!.invoice) console.log(`Invoice ${r!.invoice.number}: $${r!.invoice.amount}, issued ${r!.invoice.issuedOn}, due ${r!.invoice.dueOn}`);
  console.log("\nStages:");
  for (const s of r!.stageLog) console.log(`  ${s.stage} ${s.outcome.padEnd(4)} ${s.detail}`);
  if (r!.ownerMessage) console.log(`\nOwner message (${r!.ownerMessage.channel}, auto-send): ${r!.ownerMessage.subject}\n  ${r!.ownerMessage.body}`);
}

function cases() {
  const file = readJson(a.results!) as { today: string; configVersion: string; results: CollectResult[] };
  const out = { exportedAt: new Date().toISOString(), today: file.today, configVersion: file.configVersion, cases: file.results.map((r) => ({ ...toCaseRecordPatch(r), beat: toCollectBeat(r) })) };
  writeJson(need(a.export, "export"), out);
  console.log(`Wrote ${out.cases.length} case record(s) with "Collect" beats to ${a.export}`);
}

/** Agent mode: one Collect card; prints one JSON line with the board writes to send. */
async function fromBoard() {
  const config = loadConfig(need(a.config, "config"));
  const today = a.today ?? todayIn(process.env.COLLECT_TIMEZONE);
  const card = need(a.card, "card");
  const h = parseHandoff(readFileSync(need(a["card-body"], "card-body"), "utf8"));
  if (!h) return console.log(JSON.stringify({ card_id: card, error: "no collect-handoff line in the agreed shape on this card; leave it untouched" }));
  const handoff = readJson(need(a["qualify-handoff"], "qualify-handoff")) as { cases: QualifyEntry[] };
  const q = handoff.cases.find((x) => x.find_case_id === h.caseId);
  const feePct = a.authorization ? feeFromAuthorization(textOf(a.authorization), h.caseId) : null;
  let invoice: InvoiceState | null = a["invoice-state"] ? (JSON.parse(a["invoice-state"]) as InvoiceState) : null;
  invoice = applyPayment(invoice, { link: a["payment-link"], linkId: a["payment-link-id"], paidOn: a["paid-on"], ref: a["payment-ref"] });
  const billParsed = a.bill ? parseBillComment(readFileSync(a.bill, "utf8")) : null;
  if (a.bill && !billParsed) return console.log(JSON.stringify({ card_id: card, error: "the bill file is not a tax-bill comment in the agreed shape; leave the card untouched" }));
  if (billParsed && !a["bill-reading"]) return console.log(JSON.stringify({ card_id: card, error: "a tax-bill comment needs your reading in --bill-reading; leave the card untouched" }));
  const reader = a["bill-reading"] ? new ProvidedBillReader(readJson(a["bill-reading"])) : new ReadingsByBill({});
  const ctx: CollectContext = { config, today, reader };
  const r = await collect(caseFromCard(h, q, config, { feePct, invoice }), billParsed, ctx);
  console.log(JSON.stringify({ card_id: card, case_id: r.caseId, status: r.status, reader: billParsed ? reader.name : "none", paymentRequest: r.paymentRequest, writes: cardWrites(r, card) }));
}

async function main() {
  switch (cmd) {
    case "run":
      return run();
    case "show":
      return show();
    case "cases":
      return cases();
    case "from-board":
      return fromBoard();
    case "validate-config":
      loadConfig(need(a.config, "config"));
      return console.log("config OK");
    case "codes":
      for (const [k, v] of Object.entries(CODES)) console.log(`${k.padEnd(24)} ${v}`);
      return;
    default:
      console.log(readFileSync(new URL(import.meta.url), "utf8").split("*/")[0]!.replace(/^#!.*\n\/\*\*?/, "").replace(/^ \* ?/gm, ""));
  }
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
