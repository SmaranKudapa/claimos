/**
 * Website hookup: map an EscalateResult onto the shapes the Claim OS site reads
 * (`caseRecord` and the escalate entry of `claimBeats` in prototype/assets/demo-data.js).
 * The step label is "Appeal again". Money fields are null for CLOSED and INCOMPLETE cases.
 */
import type { EscalateResult, Status } from "./types.js";
import { round } from "./util.js";

export interface AppealBeat {
  id: "escalate";
  label: "Appeal again";
  title: string;
  kicker: string;
  summary: string;
  source: string;
  value: string;
  actor: string;
  state: string;
}

const DATE_FMT = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
export const formatDeadline = (iso: string) => DATE_FMT.format(new Date(`${iso}T00:00:00Z`));

const TITLE: Record<Status, string> = {
  ESCALATE: "A denial becomes the next move.",
  COLLECT: "The county's answer becomes a recovery.",
  CLOSED: "The case closes with a reason.",
  PENDING: "The case waits on the county, with a date to check again.",
  INCOMPLETE: "The county's letter needs to be fetched again.",
};
const STATE: Record<Status, string> = { ESCALATE: "escalating", COLLECT: "won", CLOSED: "closed", PENDING: "waiting", INCOMPLETE: "re-fetching" };

export function toAppealBeat(r: EscalateResult): AppealBeat {
  const f = r.reading.verified;
  const read = f ? f.outcome.replace(/_/g, " ") : "not read";
  const reasons = f?.reasonCategories.length ? ` · ${f.reasonCategories.map((k) => k.replace(/_/g, " ")).join(", ")}` : "";
  const value = (() => {
    switch (r.status) {
      case "ESCALATE":
        return r.nextLevel ? `${r.nextLevel.name} by ${formatDeadline(r.nextLevel.deadline)}` : "Next appeal prepared";
      case "COLLECT":
        return r.reasonCodes.includes("W_FULL_WIN") ? "Full reduction granted" : "Partial reduction accepted";
      case "CLOSED":
        return `Closed: ${r.reasonCodes.find((c) => c.startsWith("C_"))?.slice(2).toLowerCase().replace(/_/g, " ") ?? "no further step"}`;
      case "PENDING":
        return r.requeueOn ? `Check again ${formatDeadline(r.requeueOn)}` : "Waiting on the county";
      default:
        return "Letter re-requested";
    }
  })();
  return {
    id: "escalate",
    label: "Appeal again",
    title: TITLE[r.status],
    kicker: `Decision read: ${read}${reasons}`,
    summary: r.ownerUpdate?.body ?? r.summary,
    source: `County decision letter${r.decisionId ? ` ${r.decisionId}` : ""} · ${r.reading.readers.length ? `${r.reading.readers[0]} reader${r.reading.secondRead ? " + second read" : ""}` : "no reader"} · rules ${r.audit.configVersion}`,
    value,
    actor: "Appeal Agent",
    state: STATE[r.status],
  };
}

export interface CaseRecordPatch {
  id: string;
  apn: string;
  address: string;
  assessedValue: number | null;
  proposedValue: number | null;
  potentialRecovery: number | null;
  probability: number | null;
  expectedValue: number | null;
  estimatedFee: number | null;
  caseCost: number | null;
  filingFee: number | null;
  deadline: string | null;
  appealStatus: Status;
  appealReasonCodes: string[];
}

export function toCaseRecordPatch(r: EscalateResult): CaseRecordPatch {
  const money = r.status !== "CLOSED" && r.status !== "INCOMPLETE";
  const e = money ? r.economics : null;
  const nv = r.reading.verified?.newAssessedValue;
  return {
    id: r.caseId,
    apn: r.parcelId,
    address: r.address,
    assessedValue: money && nv !== undefined ? nv : null,
    proposedValue: null,
    potentialRecovery: e ? round(e.annual) : null,
    probability: e ? e.pWin : null,
    expectedValue: e ? round(e.ev) : null,
    estimatedFee: e ? round(e.revenue) : null,
    caseCost: e ? e.costs : null,
    filingFee: money && r.nextLevel ? r.nextLevel.filingFee : null,
    deadline: r.nextLevel ? formatDeadline(r.nextLevel.deadline) : null,
    appealStatus: r.status,
    appealReasonCodes: r.reasonCodes,
  };
}
