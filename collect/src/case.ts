/**
 * Website hookup: the "collect" entry of `claimBeats` and a `caseRecord` patch, matching
 * prototype/assets/demo-data.js. Money fields are null for CLOSED and INCOMPLETE cases.
 */
import type { CollectResult, Status } from "./types.js";

export interface CollectBeat {
  id: "collect";
  label: "Collect";
  title: string;
  kicker: string;
  summary: string;
  source: string;
  value: string;
  actor: string;
  state: string;
}

const TITLE: Record<Status, string> = {
  WAITING: "The win waits for the county's corrected bill.",
  INVOICED: "Verified savings become a success-fee invoice.",
  PAID: "The fee is paid; the case is complete.",
  CLOSED: "The case closes, with no fee charged.",
  INCOMPLETE: "The case needs its records again.",
};
const STATE: Record<Status, string> = { WAITING: "waiting", INVOICED: "invoiced", PAID: "reconciled", CLOSED: "closed", INCOMPLETE: "re-fetching" };

export function toCollectBeat(r: CollectResult): CollectBeat {
  const value =
    r.status === "INVOICED" || r.status === "PAID"
      ? `$${r.invoice?.amount} fee on $${r.savings?.annual ?? "?"} first-year savings`
      : r.status === "WAITING"
        ? r.reasonCodes.includes("P_AWAIT_BILL") ? "Waiting for the corrected bill" : `Invoice due ${r.invoice?.dueOn}`
        : r.status === "CLOSED"
          ? "No fee"
          : "Records re-requested";
  return {
    id: "collect",
    label: "Collect",
    title: TITLE[r.status],
    kicker: r.savings ? `Savings ${r.savings.fromBill ? "from the corrected bill" : "estimated"} · fee checked against the cap` : "Outcome checked",
    summary: r.ownerMessage?.body ?? r.summary,
    source: `${r.bill.docId ? `Corrected bill ${r.bill.docId}` : "No corrected bill yet"} · rules ${r.audit.configVersion}`,
    value,
    actor: "Recovery Agent",
    state: STATE[r.status],
  };
}

export function toCaseRecordPatch(r: CollectResult) {
  const money = r.status !== "CLOSED" && r.status !== "INCOMPLETE";
  return {
    id: r.caseId,
    apn: r.parcelId,
    address: r.address,
    potentialRecovery: money && r.savings ? r.savings.annual : null,
    estimatedFee: money && r.invoice ? r.invoice.amount : null,
    collectStatus: r.status,
    collectReasonCodes: r.reasonCodes,
    invoiceNumber: money ? (r.invoice?.number ?? null) : null,
  };
}
