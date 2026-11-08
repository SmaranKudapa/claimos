/**
 * Adapters from a QualifyResult to the shapes the Claim OS UI already reads
 * (`caseRecord` and the "qualify" entry of `claimBeats` in prototype/assets/demo-data.js).
 *
 * The repo has no shared Case schema yet, so this module is the mapping. It keeps the
 * prototype's field names, adds the Qualify-specific fields the dossier needs, and carries
 * the full result under `qualify` so nothing is lost. These are presentation adapters:
 * they never change a decision.
 */
import type { DeskConfig, QualifyResult, Status } from "./types.js";

export interface CaseRecord {
  /** Prototype fields (same names and units as demo-data.js `caseRecord`). */
  id: string;
  desk: string;
  claimant: string | null;
  address: string;
  apn: string;
  assessedValue: number | null;
  /** The cautious target value we'd argue for (not the raw comp median). */
  proposedValue: number | null;
  /** Estimated annual tax savings. */
  potentialRecovery: number | null;
  probability: number | null;
  expectedValue: number | null;
  estimatedFee: number | null;
  /** Agent and evidence spend if pursued, excluding the filing fee. */
  caseCost: number | null;
  filingFee: number | null;
  /** e.g. "Dec 18, 2026", or null when no route is open. */
  deadline: string | null;
  /** Qualify additions. */
  status: Status;
  summary: string;
  reasonCodes: string[];
  flags: string[];
  confidence: number | null;
  routeName: string | null;
  formId: string | null;
  priority: number;
  releaseDate: string | null;
  requalifyOn: string | null;
  decidedBy: string;
  configVersion: string;
  qualify: QualifyResult;
}

export interface CaseRecordOptions {
  /** The candidate record from Find, for the claimant's names and the assessed value. */
  candidate?: unknown;
  /** The desk config, for the route's filing fee. */
  config?: DeskConfig;
  /** The desk label shown in the UI. Desk configs don't carry one yet. */
  deskName?: string;
}

const DATE_FMT = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
export const formatDeadline = (iso: string) => DATE_FMT.format(new Date(`${iso}T00:00:00Z`));

function candidateFacts(raw: unknown): { names: string[]; assessed: number | null } {
  const c = (raw ?? {}) as { owner?: { names?: unknown }; assessment?: { assessedValue?: unknown } };
  const names = Array.isArray(c.owner?.names) ? c.owner!.names.filter((n): n is string => typeof n === "string" && n.trim() !== "") : [];
  const assessed = typeof c.assessment?.assessedValue === "number" ? c.assessment.assessedValue : null;
  return { names, assessed };
}

export function toCaseRecord(r: QualifyResult, opts: CaseRecordOptions = {}): CaseRecord {
  const { names, assessed } = candidateFacts(opts.candidate);
  const v = r.valuation;
  const e = r.economics;
  const route = r.route ? opts.config?.routes.find((x) => x.id === r.route!.id) : undefined;
  const filingFee = route ? route.filingFee : null;
  const priced = r.status === "QUALIFIED" || r.status === "NEEDS_REVIEW" || r.status === "NEXT_CYCLE";

  return {
    id: r.caseId,
    desk: opts.deskName ?? "Property Tax",
    claimant: names.length ? names.join(" & ") : null,
    address: r.address,
    apn: r.parcelId,
    assessedValue: assessed ?? (v ? v.target + v.gap : null),
    proposedValue: priced && v ? v.target : null,
    potentialRecovery: priced && e ? e.annualSavings : null,
    probability: priced && e ? e.pWin : null,
    expectedValue: priced && e ? e.ev : null,
    estimatedFee: priced && e ? e.fee : null,
    caseCost: priced && e ? Math.round((e.maxLoss - (filingFee ?? 0)) * 100) / 100 : null,
    filingFee,
    deadline: r.route ? formatDeadline(r.route.deadline) : null,
    status: r.status,
    summary: r.summary,
    reasonCodes: r.reasonCodes,
    flags: r.flags,
    confidence: v ? v.confidence : null,
    routeName: r.route?.name ?? null,
    formId: r.route?.formId ?? null,
    priority: r.priority,
    releaseDate: r.releaseDate,
    requalifyOn: r.requalifyOn,
    decidedBy: r.audit.decidedBy,
    configVersion: r.audit.configVersion,
    qualify: r,
  };
}

/** Same shape as the prototype's `claimBeats` entries. */
export interface ClaimBeat {
  id: "qualify";
  label: "Qualify";
  title: string;
  kicker: string;
  summary: string;
  source: string;
  value: string;
  actor: string;
  state: string;
}

const BEAT_TITLE: Record<Status, string> = {
  QUALIFIED: "Eligibility and economics clear the threshold.",
  NEEDS_REVIEW: "Worth pursuing, but a person checks it first.",
  NEXT_CYCLE: "A good claim, waiting for its filing window.",
  INCOMPLETE: "Not enough data to judge yet.",
  REJECTED: "Not worth pursuing, with reasons recorded.",
};
const BEAT_STATE: Record<Status, string> = {
  QUALIFIED: "qualified",
  NEEDS_REVIEW: "review",
  NEXT_CYCLE: "waiting",
  INCOMPLETE: "incomplete",
  REJECTED: "rejected",
};

const usd = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);

export function toQualifyBeat(r: QualifyResult): ClaimBeat {
  const e = r.economics;
  const priced = !!e && (r.status === "QUALIFIED" || r.status === "NEEDS_REVIEW" || r.status === "NEXT_CYCLE");
  const kicker = priced
    ? `${Math.round(e!.pWin * 100)}% estimated win probability`
    : r.reasonCodes.length
      ? r.reasonCodes.join(" · ")
      : r.status.toLowerCase();
  const value = priced ? `${usd(e!.ev)} expected value` : r.status === "INCOMPLETE" ? "Sent back to Find" : "No spend";
  return {
    id: "qualify",
    label: "Qualify",
    title: BEAT_TITLE[r.status],
    kicker,
    summary: r.summary,
    source: `Eligibility rules + desk config ${r.audit.configVersion} + comparable-sales valuation${r.llm?.ran ? " + LLM review" : ""}`,
    value,
    actor: "Eligibility Agent",
    state: BEAT_STATE[r.status],
  };
}
