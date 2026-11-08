#!/usr/bin/env node
/**
 * Qualify CLI.
 *
 *   qualify run      --candidates <file> --config <file> [--suppression <file>] [--today YYYY-MM-DD]
 *                    [--llm naive|mock|off] [--out out/results.json] [--audit out/audit.jsonl]
 *   qualify show     --results <file> --case <caseId>
 *   qualify review   --results <file> --case <caseId> --by <name>
 *                    (--approve | --reject <CODE> | --exclude-comps id,id [--patch '<json>'])
 *                    [--note <text>] [--candidates <file> --config <file>]   (edit needs these)
 *   qualify cases    --results <file> [--candidates <file>] [--config <file>] [--export out/cases.json]
 *                    (exports results as dossier-shaped case records for the Claim OS UI)
 *   qualify card-notes --handoff <handoff.json> --cards <file | crd_id=case_id,...>
 *                    (one JSON line per card: the exact board_write to send, and the comment to send if the card is done)
 *   qualify find-run --find <candidates.jsonl> --template <desk template> [--case-ids <file>] [--tiers strong,possible]
 *                    [--replay (each county judged inside its own filing window) | --as-of YYYY-MM-DD] [--today YYYY-MM-DD] [--suppression <file>]
 *                    [--llm naive|mock|off] [--out-dir out/find-run] [--translate-only]
 *                    (translates a Find run, one desk config per jurisdiction, runs Qualify)
 *   qualify validate-config --config <file>
 *   qualify codes
 *
 * Env: NAIVE_API_KEY (or the repo's VETTA_API_KEY), NAIVE_API_BASE_URL (or VETTA_API_BASE_URL),
 *      QUALIFY_MODEL, QUALIFY_ESCALATION_MODEL, QUALIFY_TIMEZONE. Read from qualify/.env, then the repo-root .env.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { parseArgs } from "node:util";
import { loadDeskConfig, loadSuppression } from "./config.js";
import { CODES } from "./codes.js";
import { appendAudit, toAuditRecord } from "./audit.js";
import type { QualifyContext } from "./draft.js";
import { FileLlmCache, type LlmClient } from "./llm/client.js";
import { NaiveLlmClient, naiveCredentialsFromEnv } from "./llm/naive.js";
import { HeuristicReviewer } from "./llm/mock.js";
import { qualifyAll } from "./pipeline.js";
import { renderCase, renderTable } from "./report.js";
import { toCaseRecord, toQualifyBeat } from "./case.js";
import { applyReview, ReviewError, type ReviewAction } from "./review.js";
import type { QualifyResult } from "./types.js";
import { getPath, todayIn } from "./util.js";
import { jurisdictionIdFor, parseJsonl, translateRun } from "./adapters/find-v2.js";
import { cardWrites } from "./adapters/card-writes.js";
import { addDays } from "./util.js";

// qualify/.env first, then the repo-root .env (where the team keeps VETTA_API_KEY).
// loadEnvFile never overwrites a variable that is already set, so the first file wins.
for (const envFile of [".env", "../.env"]) {
  try {
    (process as unknown as { loadEnvFile?: (p: string) => void }).loadEnvFile?.(envFile);
  } catch {
    /* file absent — fine */
  }
}


interface ResultsFile {
  runAt: string;
  today: string;
  configVersion: string;
  counts: Record<string, number>;
  results: QualifyResult[];
}

const [cmd, ...rest] = process.argv.slice(2);
const { values: a } = parseArgs({
  args: rest,
  options: {
    candidates: { type: "string" },
    config: { type: "string" },
    suppression: { type: "string" },
    today: { type: "string" },
    llm: { type: "string" },
    out: { type: "string", default: "out/results.json" },
    audit: { type: "string", default: "out/audit.jsonl" },
    results: { type: "string", default: "out/results.json" },
    case: { type: "string" },
    by: { type: "string" },
    approve: { type: "boolean" },
    reject: { type: "string" },
    "exclude-comps": { type: "string" },
    patch: { type: "string" },
    note: { type: "string" },
    json: { type: "boolean" },
    export: { type: "string" },
    find: { type: "string" },
    template: { type: "string" },
    "case-ids": { type: "string" },
    "as-of": { type: "string" },
    "out-dir": { type: "string", default: "out/find-run" },
    "translate-only": { type: "boolean" },
    replay: { type: "boolean" },
    tiers: { type: "string" },
    handoff: { type: "string" },
    cards: { type: "string" },
  },
  allowPositionals: false,
});

function need(v: string | undefined, name: string): string {
  if (!v) fail(`--${name} is required`);
  return v!;
}
function fail(msg: string): never {
  console.error(`error: ${msg}`);
  process.exit(2);
}
const readJson = (p: string) => JSON.parse(readFileSync(p, "utf8"));
function writeJson(p: string, v: unknown) {
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(v, null, 2) + "\n");
}

function makeLlm(mode: string | undefined): { client: LlmClient | null; note: string } {
  const { apiKey: key, baseUrl } = naiveCredentialsFromEnv();
  const m = mode ?? (key ? "naive" : "off");
  if (m === "off") return { client: null, note: key ? "LLM off (--llm off)" : "LLM off (no NAIVE_API_KEY / VETTA_API_KEY; use --llm mock for an offline reviewer)" };
  if (m === "mock") return { client: new HeuristicReviewer(), note: "LLM: offline heuristic reviewer (mock)" };
  if (m === "naive") {
    if (!key) fail("--llm naive needs NAIVE_API_KEY (or VETTA_API_KEY) in the environment, qualify/.env, or the repo-root .env");
    return { client: new NaiveLlmClient({ apiKey: key, baseUrl }), note: "LLM: Naïve model proxy" };
  }
  fail(`unknown --llm ${m} (naive|mock|off)`);
}

async function run() {
  const config = loadDeskConfig(need(a.config, "config"));
  const today = a.today ?? todayIn(process.env.QUALIFY_TIMEZONE);
  const raws = readJson(need(a.candidates, "candidates"));
  if (!Array.isArray(raws)) fail("candidates file must be a JSON array");

  const prior = new Map<string, QualifyResult>();
  if (existsSync(a.out!)) for (const r of (readJson(a.out!) as ResultsFile).results ?? []) prior.set(r.caseId, r);

  const { client, note } = makeLlm(a.llm);
  const primary = process.env.QUALIFY_MODEL || config.llm.model || (a.llm === "mock" ? "mock-model" : null);
  const ctx: QualifyContext = {
    config,
    today,
    suppression: loadSuppression(a.suppression),
    priorResults: prior,
    llm: client,
    llmCache: client ? new FileLlmCache(".cache/llm") : undefined,
    models: { primary, escalation: process.env.QUALIFY_ESCALATION_MODEL || config.llm.escalationModel },
  };

  const sum = await qualifyAll(raws, ctx);
  const file: ResultsFile = { runAt: new Date().toISOString(), today, configVersion: config.version, counts: sum.counts, results: sum.results };
  writeJson(a.out!, file);
  appendAudit(a.audit!, sum.results.map((r) => toAuditRecord(r, "qualified", today)));

  if (a.json) return console.log(JSON.stringify(file, null, 2));
  console.log(`Qualify · ${config.jurisdiction.name} · config ${config.version} · today ${today}`);
  console.log(note + (client && primary ? ` · model ${primary}` : ""));
  console.log();
  console.log(renderTable(sum));
  console.log(`\nWrote ${a.out} and appended ${sum.results.length} record(s) to ${a.audit}`);
}

async function review() {
  const path = a.results!;
  const file = readJson(path) as ResultsFile;
  const id = need(a.case, "case");
  const by = need(a.by, "by");
  const i = file.results.findIndex((r) => r.caseId === id);
  if (i < 0) fail(`no case ${id} in ${path}`);
  const current = file.results[i]!;

  let action: ReviewAction;
  if (a.approve) action = { type: "approve", note: a.note };
  else if (a.reject) action = { type: "reject", code: a.reject, note: a.note };
  else if (a["exclude-comps"] || a.patch)
    action = {
      type: "edit",
      excludeComps: a["exclude-comps"]?.split(",").map((s) => s.trim()).filter(Boolean),
      patch: a.patch ? JSON.parse(a.patch) : undefined,
      note: a.note,
    };
  else fail("choose one of --approve, --reject <CODE>, --exclude-comps, --patch");

  let opts = {};
  if (action.type === "edit") {
    const config = loadDeskConfig(need(a.config, "config"));
    const raws = readJson(need(a.candidates, "candidates")) as unknown[];
    const candidate = raws.filter((r) => getPath(r, "parcelId") === current.parcelId && getPath(r, "jurisdictionId") === current.jurisdictionId).at(-1);
    if (!candidate) fail(`candidate ${current.parcelId} not found in ${a.candidates}`);
    opts = {
      candidate,
      ctx: { config, today: file.today, suppression: loadSuppression(a.suppression), priorResults: new Map(), llm: null } satisfies QualifyContext,
    };
  }

  try {
    const updated = await applyReview(current, action, by, opts);
    file.results[i] = updated;
    file.counts = file.results.reduce<Record<string, number>>((m, r) => ((m[r.status] = (m[r.status] ?? 0) + 1), m), {});
    writeJson(path, file);
    appendAudit(a.audit!, [toAuditRecord(updated, "reviewed")]);
    console.log(renderCase(updated));
  } catch (e) {
    if (e instanceof ReviewError) fail(e.message);
    throw e;
  }
}

function show() {
  const file = readJson(a.results!) as ResultsFile;
  const r = file.results.find((x) => x.caseId === need(a.case, "case"));
  if (!r) fail(`no case ${a.case}`);
  console.log(a.json ? JSON.stringify(r, null, 2) : renderCase(r!));
}

/** Export results as dossier-shaped case records (prototype `caseRecord` fields + Qualify fields). */
function cases() {
  const file = readJson(a.results!) as ResultsFile;
  const config = a.config ? loadDeskConfig(a.config) : undefined;
  const raws = a.candidates ? (readJson(a.candidates) as unknown[]) : [];
  // Newest record per parcel, matching qualifyAll's dedupe.
  const byKey = new Map<string, unknown>();
  for (const c of [...raws].sort((x, y) => String(getPath(x, "provenance.fetchedAt") ?? "").localeCompare(String(getPath(y, "provenance.fetchedAt") ?? ""))))
    byKey.set(`${getPath(c, "jurisdictionId")}|${getPath(c, "parcelId")}`, c);
  const out = {
    exportedAt: new Date().toISOString(),
    today: file.today,
    configVersion: file.configVersion,
    counts: file.counts,
    cases: file.results.map((r) => ({
      ...toCaseRecord(r, { candidate: byKey.get(`${r.jurisdictionId}|${r.parcelId}`), config }),
      beat: toQualifyBeat(r),
    })),
  };
  if (a.export) {
    writeJson(a.export, out);
    console.log(`Wrote ${out.cases.length} case record(s) to ${a.export}`);
  } else console.log(JSON.stringify(out, null, 2));
}

/**
 * Qualify a Find run: translate Find's candidates.jsonl (full records), group by jurisdiction,
 * build each jurisdiction's desk config from --template + Find's filing window, run Qualify.
 * Writes <out-dir>/results.json (all jurisdictions) and <out-dir>/handoff.json (one line per
 * case, keyed by Find's case_id, for the agent to post).
 */
async function findRun() {
  const template = loadDeskConfig(need(a.template, "template"));
  const { records, bad } = parseJsonl(readFileSync(need(a.find, "find"), "utf8"));
  if (bad.length) console.error(`warning: skipped ${bad.length} malformed line(s) in ${a.find}: ${bad.slice(0, 5).join(", ")}`);
  let recs = records;
  if (a["case-ids"]) {
    const txt = readFileSync(a["case-ids"], "utf8").trim();
    const ids = new Set<string>(txt.startsWith("[") ? (JSON.parse(txt) as string[]) : txt.split(/\r?\n/).map((s) => s.trim()).filter(Boolean));
    recs = records.filter((r) => ids.has(r.case_id));
    const missing = [...ids].filter((id) => !records.some((r) => r.case_id === id));
    if (missing.length) console.error(`warning: ${missing.length} case id(s) not in ${a.find}: ${missing.slice(0, 3).join(", ")}`);
  }
  if (a.tiers) {
    const tiers = new Set(a.tiers.split(",").map((t) => t.trim()).filter(Boolean));
    recs = recs.filter((r) => tiers.has(String(r.tier)));
  }
  if (!recs.length) fail("no Find records to qualify");

  const asOf = a["as-of"];
  const realToday = todayIn(process.env.QUALIFY_TIMEZONE);
  const fixedToday = a.today ?? asOf ?? realToday;
  // --replay: each jurisdiction is replayed at a date inside its own filing window
  // (10 days after it opens, or the last day the work still fits).
  const batches = translateRun(recs, template, { asOf }).map((b) => {
    if (!a.replay) return { ...b, today: fixedToday };
    const r = b.config.routes[0]!;
    let day = addDays(r.opens, 10);
    const lastFeasible = addDays(r.closes, -(r.bufferDays + r.workDaysNeeded));
    if (day > lastFeasible) day = lastFeasible < r.opens ? r.opens : lastFeasible;
    const own = recs.filter((x) => jurisdictionIdFor(x) === b.jurisdictionId);
    return { ...translateRun(own, template, { asOf: day })[0]!, today: day };
  });
  const replay = Boolean(a.replay || asOf);
  const base = loadSuppression(a.suppression);
  const outDir = a["out-dir"]!;

  if (a["translate-only"]) {
    for (const b of batches) {
      writeJson(`${outDir}/${b.jurisdictionId}/candidates.json`, b.candidates);
      writeJson(`${outDir}/${b.jurisdictionId}/config.json`, b.config);
      writeJson(`${outDir}/${b.jurisdictionId}/suppression.json`, b.suppression);
      console.log(`${b.jurisdictionId}: ${b.candidates.length} candidate(s) → ${outDir}/${b.jurisdictionId}/`);
    }
    return;
  }

  const { client, note } = makeLlm(a.llm);
  const all: QualifyResult[] = [];
  const handoff: Record<string, unknown>[] = [];
  let cost = 0;
  if (replay) console.log(`REPLAY (real date ${realToday}): each county is judged as of a date inside its filing window. Results show what Qualify would have decided then.`);
  for (const b of batches) {
    const suppression = {
      ...base,
      dncParcels: [...new Set([...base.dncParcels, ...b.suppression.dncParcels])],
    };
    const primary = process.env.QUALIFY_MODEL || b.config.llm.model || (a.llm === "mock" ? "mock-model" : null);
    const ctx: QualifyContext = {
      config: b.config,
      today: b.today,
      suppression,
      priorResults: new Map(),
      llm: client,
      llmCache: client ? new FileLlmCache(".cache/llm") : undefined,
      models: { primary, escalation: process.env.QUALIFY_ESCALATION_MODEL || b.config.llm.escalationModel },
    };
    const sum = await qualifyAll(b.candidates, ctx);
    cost += sum.llmCostUsd;
    writeJson(`${outDir}/${b.jurisdictionId}/candidates.json`, b.candidates);
    writeJson(`${outDir}/${b.jurisdictionId}/config.json`, b.config);
    writeJson(`${outDir}/${b.jurisdictionId}/results.json`, { runAt: new Date().toISOString(), today: b.today, replay, configVersion: b.config.version, counts: sum.counts, results: sum.results });
    const findIdByParcel = new Map(b.candidates.map((c) => [c.parcelId, c.provenance.sources.find_case_id]));
    for (const r of sum.results) {
      all.push(r);
      handoff.push({
        find_case_id: findIdByParcel.get(r.parcelId) ?? null,
        caseId: r.caseId,
        jurisdictionId: r.jurisdictionId,
        judgedAsOf: b.today,
        address: r.address,
        status: r.status,
        reasonCodes: r.reasonCodes,
        flags: r.flags,
        summary: r.summary,
        annualSavings: r.economics?.annualSavings ?? null,
        fee: r.economics?.fee ?? null,
        pWin: r.economics?.pWin ?? null,
        ev: r.economics?.ev ?? null,
        route: r.route ? { id: r.route.id, form: r.route.formId, deadline: r.route.deadline, daysLeft: r.route.daysLeft } : null,
        priority: r.priority,
        releaseDate: r.releaseDate,
        requalifyOn: r.requalifyOn,
        translatorNotes: b.notes.get(r.parcelId) ?? [],
      });
    }
    console.log(`\nQualify · ${b.config.jurisdiction.name} · config ${b.config.version} · today ${b.today}${replay ? " (replay)" : ""}`);
    console.log(note + (client && primary ? ` · model ${primary}` : ""));
    console.log(renderTable(sum));
  }
  const counts: Record<string, number> = {};
  for (const r of all) counts[r.status] = (counts[r.status] ?? 0) + 1;
  writeJson(`${outDir}/results.json`, { runAt: new Date().toISOString(), realDate: realToday, replay, counts, llmCostUsd: cost, results: all });
  writeJson(`${outDir}/handoff.json`, { realDate: realToday, replay, counts, llmCostUsd: cost, cases: handoff });
  console.log(`\nAll jurisdictions: ${Object.entries(counts).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(" · ")} · LLM cost $${cost.toFixed(4)}`);
  console.log(`Wrote ${outDir}/results.json and ${outDir}/handoff.json`);
}

/** Exact board writes for the agent (see adapters/card-writes.ts). */
function cardNotes() {
  const h = readJson(need(a.handoff, "handoff")) as { replay?: boolean; cases: Record<string, unknown>[] };
  const src = need(a.cards, "cards");
  const pairs = existsSync(src) ? readFileSync(src, "utf8").split(/[\r\n,]+/) : src.split(",");
  for (const line of cardWrites(h, pairs)) console.log(JSON.stringify(line));
}

async function main() {
  switch (cmd) {
    case "card-notes":
      return cardNotes();
    case "run":
      return run();
    case "find-run":
      return findRun();
    case "review":
      return review();
    case "show":
      return show();
    case "cases":
      return cases();
    case "validate-config":
      loadDeskConfig(need(a.config, "config"));
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
