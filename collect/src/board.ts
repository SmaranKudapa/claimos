/**
 * Board hookup for the Collect agent.
 *
 * In:  the `Collect · <address> · <case_id>` card Escalate creates for a won case. Its body has
 *        collect-handoff · case <id> · old <value> · won <value> · decided <YYYY-MM-DD> · letter <id> · code <W_…>
 *      an optional `tax-bill` comment with the corrected bill's full text:
 *        tax-bill · case <id> · received <YYYY-MM-DD> · <document id>
 *        <full bill text>
 *      the latest `invoice-state:` line from an earlier collect-result comment, the case's entry
 *      in Qualify's handoff.json, and Sign up's `authorization:` line if any (fee %).
 * Out: a `collect-result` comment and an update of the same card.
 */
import type { CollectConfig, CollectResult, InvoiceState } from "./types.js";

export interface Handoff {
  caseId: string;
  oldValue: number;
  wonValue: number;
  wonOn: string;
  decisionId: string;
  wonCode: string;
}

const num = (s: string) => Number(s.replace(/[$,]/g, ""));

export function parseHandoff(cardBody: string): Handoff | null {
  const line = cardBody.split(/\r?\n/).find((l) => /^\s*collect-handoff\s*·/i.test(l));
  if (!line) return null;
  const f = new Map<string, string>();
  for (const part of line.split("·").slice(1)) {
    const m = part.trim().match(/^([a-z_]+)\s+(.+)$/i);
    if (m) f.set(m[1]!.toLowerCase(), m[2]!.trim());
  }
  const h = { caseId: f.get("case"), oldValue: num(f.get("old") ?? ""), wonValue: num(f.get("won") ?? ""), wonOn: f.get("decided"), decisionId: f.get("letter"), wonCode: f.get("code") };
  if (!h.caseId || !(h.oldValue > 0) || !(h.wonValue > 0) || !/^\d{4}-\d{2}-\d{2}$/.test(h.wonOn ?? "") || !h.decisionId || !/^W_/.test(h.wonCode ?? "")) return null;
  return h as Handoff;
}

export function parseBillComment(comment: string): { docId: string; caseId: string; receivedOn: string; text: string } | null {
  const lines = comment.replace(/\r\n/g, "\n").split("\n");
  const m = (lines[0] ?? "").match(/^\s*tax-bill\s*·\s*case\s+(\S+)\s*·\s*received\s+(\d{4}-\d{2}-\d{2})\s*·\s*(\S+)\s*$/i);
  if (!m) return null;
  return { caseId: m[1]!, receivedOn: m[2]!, docId: m[3]!, text: lines.slice(1).join("\n").trim() };
}

/** Fee % from Sign up's authorization line (`… · fee 30% · …`), when it names this case. */
export function feeFromAuthorization(text: string, caseId: string): number | null {
  const line = text.split(/\r?\n/).find((l) => /^\s*authorization\s*:/i.test(l));
  if (!line || !new RegExp(`case_id\\s+${caseId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\s|·|$)`).test(line)) return null;
  const m = line.match(/fee\s+(\d+(?:\.\d+)?)\s*%/i);
  const pct = m ? Number(m[1]) / 100 : NaN;
  return pct >= 0 && pct <= 1 ? pct : null;
}

export interface QualifyEntry {
  find_case_id: string | null;
  parcelId?: string;
  jurisdictionId?: string;
  address?: string;
  taxRate?: number | null;
  owner?: { names: string[]; type: string } | null;
}

export function caseFromCard(h: Handoff, q: QualifyEntry | undefined, cfg: CollectConfig, opts: { feePct?: number | null; invoice?: InvoiceState | null; contactChannel?: string } = {}): Record<string, unknown> {
  return {
    caseId: h.caseId,
    parcelId: q?.parcelId,
    jurisdictionId: q?.jurisdictionId,
    address: q?.address,
    owner: { names: q?.owner?.names ?? [], type: q?.owner?.type ?? "individual", contactChannel: opts.contactChannel ?? "mail" },
    oldAssessedValue: h.oldValue,
    wonAssessedValue: h.wonValue,
    taxRate: q?.taxRate ?? undefined,
    feePct: opts.feePct ?? cfg.fee.defaultPct,
    authorizationSource: opts.feePct != null ? "signed" : "desk_default",
    wonOn: h.wonOn,
    wonCode: h.wonCode,
    decisionId: h.decisionId,
    ...(opts.invoice ? { invoice: opts.invoice } : {}),
  };
}

/** Record a payment link or a payment the agent saw in Stripe onto the invoice state. */
export function applyPayment(inv: InvoiceState | null, p: { link?: string; linkId?: string; paidOn?: string; ref?: string }): InvoiceState | null {
  if (!inv) return null;
  return {
    ...inv,
    ...(p.link ? { paymentLink: { url: p.link, ...(p.linkId ? { id: p.linkId } : {}) } } : {}),
    ...(p.paidOn && p.ref ? { paid: { on: p.paidOn, ref: p.ref } } : {}),
  };
}

export type BoardWrite = { op: "comment"; card_id: string; body: string } | { op: "update"; card_id: string; status: "done" | "blocked"; note: string };

export function cardWrites(r: CollectResult, cardId: string): BoardWrite[] {
  const code = r.summary.split(" · ")[1] ?? r.reasonCodes[0] ?? "";
  const inv = r.invoice;
  const lines = [
    `collect-result · ${r.status} · ${code} · ${inv?.number ?? r.caseId}`,
    r.summary,
    ...(r.flags.length ? [`flags: ${r.flags.join(", ")}`] : []),
    ...(r.savings ? [`savings: $${r.savings.annual}/yr (${r.savings.fromBill ? "from the corrected bill" : "estimated from value cut × tax rate"})`] : []),
    ...(r.paymentRequest ? [`payment-request: ${JSON.stringify(r.paymentRequest)}`] : []),
    ...(r.ownerMessage ? [`owner-message (${r.ownerMessage.channel}, auto-send): ${r.ownerMessage.subject}: ${r.ownerMessage.body}`] : []),
    ...(inv ? [`invoice-state: ${JSON.stringify(inv)}`] : []),
  ];
  const note = (() => {
    switch (r.status) {
      case "WAITING":
        return { status: "blocked" as const, note: `WAITING · ${code === "P_AWAIT_BILL" ? "corrected bill" : `payment ${inv?.number}`} · check ${r.requeueOn}` };
      case "INVOICED":
        return { status: "blocked" as const, note: `INVOICED · $${inv?.amount} · ${inv?.number} · due ${inv?.dueOn}` };
      case "PAID":
        return { status: "done" as const, note: `PAID · $${inv?.amount} · ${inv?.number}` };
      case "CLOSED":
        return { status: "done" as const, note: `CLOSED · ${code}${inv ? ` · ${inv.number}` : ""}` };
      default:
        return { status: "blocked" as const, note: `INCOMPLETE · ${code}` };
    }
  })();
  return [
    { op: "comment", card_id: cardId, body: lines.join("\n") },
    { op: "update", card_id: cardId, ...note },
  ];
}

/** The latest invoice-state JSON from earlier collect-result comments, if any. */
export function latestInvoiceState(comments: string[]): InvoiceState | null {
  for (const c of [...comments].reverse()) {
    const m = c.match(/^invoice-state:\s*(\{.*\})\s*$/m);
    if (m) {
      try {
        return JSON.parse(m[1]!) as InvoiceState;
      } catch {
        /* skip a garbled line */
      }
    }
  }
  return null;
}
