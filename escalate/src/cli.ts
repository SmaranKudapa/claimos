#!/usr/bin/env node
/**
 * Escalate CLI ("Appeal again").
 *
 *   escalate run    --cases <file> --decisions <file> --config <file> [--today YYYY-MM-DD]
 *                   [--llm naive|mock] [--out out/escalate-results.json] [--audit out/audit.jsonl] [--json]
 *   escalate show   --results <file> --case <caseId> [--json]
 *   escalate cases  --results <file> --export <file>        (UI records with "Appeal again" beats)
 *   escalate from-board --card <card id> --letter <file> --qualify-handoff <handoff.json> --config <file>
 *                   [--reading <file>] [--read-state <json>] [--today YYYY-MM-DD]
 *                   (agent mode: one decision-letter comment in, the exact escalate-result comment out)
 *   escalate validate-config --config <file>
 *   escalate codes
 *
 * There is deliberately no review or approve command: every result is acted on automatically.
 * Decisions are paired with cases by `deliveredFor` (the case Chase delivered the letter with),
 * falling back to the letter's own caseId.
 *
 * Env: NAIVE_API_KEY (or VETTA_API_KEY), NAIVE_API_BASE_URL (or VETTA_API_BASE_URL),
 *      ESCALATE_MODEL, ESCALATE_ESCALATION_MODEL. Read from escalate/.env, then the repo-root .env.
 */
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { parseArgs } from "node:util";
import { CODES, statusFor } from "./codes.js";
import { loadConfig } from "./config.js";
import type { EscalateContext } from "./draft.js";
import { escalateAll, type Delivery } from "./pipeline.js";
import { MockReader } from "./reader/mock.js";
import type { Reader } from "./reader/types.js";
import { toAppealBeat, toCaseRecordPatch } from "./case.js";
import { caseFromQualify, decisionFromComment, parseLetterComment, resultComment, type QualifyHandoffEntry } from "./board.js";
import { ProvidedReader } from "./reader/provided.js";
import type { EscalateResult } from "./types.js";
import { todayIn } from "./util.js";

for (const envFile of [".env", "../.env"]) {
  try {
    (process as unknown as { loadEnvFile?: (p: string) => void }).loadEnvFile?.(envFile);
  } catch {
    /* absent — fine */
  }
}

const [cmd, ...rest] = process.argv.slice(2);
const { values: a } = parseArgs({
  args: rest,
  options: {
    cases: { type: "string" },
    decisions: { type: "string" },
    config: { type: "string" },
    today: { type: "string" },
    llm: { type: "string", default: "mock" },
    out: { type: "string", default: "out/escalate-results.json" },
    audit: { type: "string", default: "out/audit.jsonl" },
    results: { type: "string", default: "out/escalate-results.json" },
    case: { type: "string" },
    export: { type: "string" },
    card: { type: "string" },
    letter: { type: "string" },
    "qualify-handoff": { type: "string" },
    reading: { type: "string" },
    "read-state": { type: "string" },
    json: { type: "boolean" },
  },
  allowPositionals: false,
});

function fail(msg: string): never {
  console.error(`error: ${msg}`);
  process.exit(2);
}
const need = (v: string | undefined, name: string) => v ?? fail(`--${name} is required`);
const readJson = (p: string) => JSON.parse(readFileSync(p, "utf8"));
function writeJson(p: string, v: unknown) {
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(v, null, 2) + "\n");
}

async function makeReader(mode: string): Promise<Reader> {
  if (mode === "mock") return new MockReader();
  if (mode === "naive") {
    const { NaiveReader, naiveCredentialsFromEnv } = await import("./reader/naive.js");
    const { apiKey, baseUrl } = naiveCredentialsFromEnv();
    if (!apiKey) fail("--llm naive needs NAIVE_API_KEY (or VETTA_API_KEY) in the environment, escalate/.env, or the repo-root .env");
    return new NaiveReader({ apiKey, baseUrl });
  }
  fail(`unknown --llm ${mode} (naive|mock). A real run needs a reader.`);
}

const pad = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s.padEnd(n));

function table(results: EscalateResult[]): string {
  const lines = [[pad("STATUS", 10), pad("CASE", 26), pad("CODE", 20), pad("READ AS", 20), pad("NEXT / WHEN", 28), "FLAGS"].join(" ")];
  lines.push("─".repeat(130));
  for (const r of results) {
    const code = r.reasonCodes.find((c) => statusFor([c]) === r.status) ?? "";
    const read = r.reading.verified ? r.reading.verified.outcome : "—";
    const next = r.nextLevel ? `${r.nextLevel.id} by ${r.nextLevel.deadline}` : r.requeueOn ? `again ${r.requeueOn}` : "—";
    lines.push([pad(r.status, 10), pad(r.caseId, 26), pad(code, 20), pad(read, 20), pad(next, 28), r.flags.join(",")].join(" "));
  }
  const counts: Record<string, number> = {};
  for (const r of results) counts[r.status] = (counts[r.status] ?? 0) + 1;
  lines.push("─".repeat(130));
  lines.push(Object.entries(counts).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(" · ") + ` · reader cost $${results.reduce((s, r) => s + r.reading.costUsd, 0).toFixed(4)}`);
  return lines.join("\n");
}

async function run() {
  const config = loadConfig(need(a.config, "config"));
  const today = a.today ?? todayIn(process.env.ESCALATE_TIMEZONE);
  const cases = readJson(need(a.cases, "cases")) as Record<string, unknown>[];
  const decisions = readJson(need(a.decisions, "decisions")) as Record<string, unknown>[];
  if (!Array.isArray(cases) || !Array.isArray(decisions)) fail("cases and decisions files must be JSON arrays");
  const byId = new Map(cases.map((c) => [String(c.caseId), c]));
  const deliveries: Delivery[] = decisions.map((d) => {
    const { deliveredFor, ...decision } = d;
    return { case: byId.get(String(deliveredFor ?? d.caseId)) ?? { caseId: String(deliveredFor ?? d.caseId) }, decision };
  });
  const reader = await makeReader(a.llm!);
  const ctx: EscalateContext = {
    config,
    today,
    reader,
    models: { primary: process.env.ESCALATE_MODEL || config.reader.model, escalation: process.env.ESCALATE_ESCALATION_MODEL || config.reader.escalationModel },
  };
  const results = await escalateAll(deliveries, ctx);
  const file = { runAt: new Date().toISOString(), today, configVersion: config.version, results };
  writeJson(a.out!, file);
  mkdirSync(dirname(a.audit!), { recursive: true });
  for (const r of results)
    appendFileSync(a.audit!, JSON.stringify({ at: r.audit.decidedAt, step: "escalate", caseId: r.caseId, decisionId: r.decisionId, status: r.status, reasonCodes: r.reasonCodes, flags: r.flags, summary: r.summary, configVersion: r.audit.configVersion, inputHash: r.audit.inputHash, decidedBy: r.audit.decidedBy }) + "\n");
  if (a.json) return console.log(JSON.stringify(file, null, 2));
  console.log(`Escalate · ${config.jurisdictionId} · config ${config.version} · today ${today} · reader ${reader.name}\n`);
  console.log(table(results));
  console.log(`\nWrote ${a.out} and appended ${results.length} record(s) to ${a.audit}`);
}

function show() {
  const file = readJson(a.results!) as { results: EscalateResult[] };
  const r = file.results.find((x) => x.caseId === need(a.case, "case"));
  if (!r) fail(`no case ${a.case}`);
  if (a.json) return console.log(JSON.stringify(r, null, 2));
  const f = r!.reading.verified;
  console.log(`${r!.caseId} · ${r!.address}\n${r!.summary}\n`);
  console.log(`Codes: ${r!.reasonCodes.join(", ")}${r!.flags.length ? ` · Flags: ${r!.flags.join(", ")}` : ""}`);
  if (f) {
    console.log(`\nReading (${r!.reading.readers.join(" → ") || "none"}${r!.reading.secondRead ? ", second read" : ""}):`);
    console.log(`  outcome ${f.outcome}${f.newAssessedValue ? ` · new value ${f.newAssessedValue}` : ""}${f.decisionDate ? ` · decided ${f.decisionDate}` : ""}`);
    for (const e of f.evidence) console.log(`  ${e.field}: "${e.quote}"`);
    if (r!.reading.droppedFields.length) console.log(`  dropped (quote not in letter): ${r!.reading.droppedFields.join(", ")}`);
  }
  if (r!.economics) console.log(`\nEconomics: gap ${r!.economics.gap} · $${r!.economics.annual}/yr · P(win) ${r!.economics.pWin} · costs $${r!.economics.costs} · EV $${r!.economics.ev}`);
  if (r!.evidenceRequests.length) console.log(`Evidence to add: ${r!.evidenceRequests.map((x) => x.key).join(", ")}`);
  console.log("\nStages:");
  for (const s of r!.stageLog) console.log(`  ${s.stage} ${s.outcome.padEnd(4)} ${s.detail}`);
  if (r!.ownerUpdate) console.log(`\nOwner update (${r!.ownerUpdate.channel}, auto-send): ${r!.ownerUpdate.subject}\n  ${r!.ownerUpdate.body}`);
}

function cases() {
  const file = readJson(a.results!) as { today: string; configVersion: string; results: EscalateResult[] };
  const out = { exportedAt: new Date().toISOString(), today: file.today, configVersion: file.configVersion, cases: file.results.map((r) => ({ ...toCaseRecordPatch(r), beat: toAppealBeat(r) })) };
  writeJson(need(a.export, "export"), out);
  console.log(`Wrote ${out.cases.length} case record(s) with "Appeal again" beats to ${a.export}`);
}

/** Agent mode: one card, one decision-letter comment; prints one JSON line with the comment to post. */
async function fromBoard() {
  const config = loadConfig(need(a.config, "config"));
  const today = a.today ?? todayIn(process.env.ESCALATE_TIMEZONE);
  const card = need(a.card, "card");
  const letter = parseLetterComment(readFileSync(need(a.letter, "letter"), "utf8"));
  if (!letter) return console.log(JSON.stringify({ card_id: card, error: "not a decision-letter comment in the agreed shape; leave this card untouched" }));
  const handoff = readJson(need(a["qualify-handoff"], "qualify-handoff")) as { cases: QualifyHandoffEntry[] };
  const entry = letter.caseId ? handoff.cases.find((x) => x.find_case_id === letter.caseId) : undefined;
  const readAttempts = a["read-state"] ? [JSON.parse(a["read-state"])] : [];
  const reader = a.reading ? new ProvidedReader(readJson(a.reading)) : new MockReader();
  const ctx: EscalateContext = { config, today, reader };
  const decision = decisionFromComment(letter, entry?.route?.id ?? null);
  const caseRaw = entry ? caseFromQualify(entry, letter, config, { readAttempts }) : { caseId: letter.caseId ?? "unknown" };
  let [r] = await escalateAll([{ case: caseRaw, decision }], ctx);
  if (!entry) r = { ...r!, reasonCodes: ["I_CASE_NOT_FOUND"], summary: `INCOMPLETE · I_CASE_NOT_FOUND · no Qualify record for case ${letter.caseId ?? "unknown"}`, stageLog: [{ stage: "E0", outcome: "stop", detail: "I_CASE_NOT_FOUND" }] };
  console.log(JSON.stringify({ card_id: card, case_id: r!.caseId, status: r!.status, reader: reader.name, write: resultComment(r!, card) }));
}

async function main() {
  switch (cmd) {
    case "from-board":
      return fromBoard();
    case "run":
      return run();
    case "show":
      return show();
    case "cases":
      return cases();
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
