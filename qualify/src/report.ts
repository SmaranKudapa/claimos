import type { RunSummary } from "./pipeline.js";
import type { QualifyResult } from "./types.js";
import { money, pct } from "./util.js";

const pad = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s.padEnd(n));
const lpad = (s: string, n: number) => s.padStart(n);

export function renderTable(sum: RunSummary): string {
  const lines: string[] = [];
  lines.push(
    [pad("STATUS", 13), pad("PARCEL", 12), pad("ADDRESS", 24), lpad("GAP", 7), lpad("SAVE/YR", 8), lpad("P(WIN)", 7), lpad("EV", 7), lpad("PRIO", 7), "  NOTE"].join(" "),
  );
  lines.push("─".repeat(130));
  for (const r of sum.results) lines.push(row(r));
  lines.push("─".repeat(130));
  const c = sum.counts;
  lines.push(
    `${c.QUALIFIED ?? 0} qualified (${sum.results.filter((r) => r.releaseDate).length} released today) · ${c.NEEDS_REVIEW ?? 0} needs review · ` +
      `${c.NEXT_CYCLE ?? 0} next cycle · ${c.INCOMPLETE ?? 0} incomplete · ${c.REJECTED ?? 0} rejected` +
      (sum.merged ? ` · ${sum.merged} duplicate(s) merged` : "") +
      ` · LLM cost $${sum.llmCostUsd.toFixed(4)}`,
  );
  return lines.join("\n");
}

function row(r: QualifyResult): string {
  const v = r.valuation;
  const e = r.economics;
  const live = r.status === "QUALIFIED" || r.status === "NEEDS_REVIEW" || r.status === "NEXT_CYCLE";
  const note =
    r.status === "QUALIFIED"
      ? `${r.route?.id} due ${r.route?.deadline} (${r.route?.daysLeft}d)${r.releaseDate ? " · released" : " · queued"}`
      : r.status === "NEEDS_REVIEW"
        ? r.flags.join(", ")
        : r.reasonCodes.join(", ");
  return [
    pad(r.status, 13),
    pad(r.parcelId, 12),
    pad(r.address, 24),
    lpad(v && live ? pct(v.gapPct) : "—", 7),
    lpad(e && live ? money(e.annualSavings) : "—", 8),
    lpad(e && live ? pct(e.pWin, 0) : "—", 7),
    lpad(e && live ? money(e.ev) : "—", 7),
    lpad(r.priority ? r.priority.toFixed(0) : "—", 7),
    "  " + note,
  ].join(" ");
}

export function renderCase(r: QualifyResult): string {
  const out = [`${r.caseId} · ${r.status}`, r.summary, ""];
  for (const s of r.stageLog) out.push(`  ${s.stage} ${s.outcome.padEnd(4)} ${s.detail ?? ""}`);
  if (r.llm?.ran) {
    out.push("", `  LLM ${r.llm.model} → ${r.llm.recommendedAction}${r.llm.summary ? ": " + r.llm.summary : ""}`);
    for (const c of r.llm.checks) out.push(`    ${c.id} ${c.verdict.padEnd(7)} ${c.counted ? "" : "(ignored: no valid evidence) "}${c.note} [${c.evidence.join(", ")}]`);
  }
  return out.join("\n");
}
