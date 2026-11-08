/**
 * Board hookup for the Escalate agent.
 *
 * In:  Chase's `decision-letter` comment on a case card:
 *        decision-letter · case <case_id> · level <filing level> · received <YYYY-MM-DD> · <messageId>
 *        <full letter text>
 *      plus the case's entry in Qualify's published handoff.json (same case id).
 * Out: one `escalate-result` comment for the card, which the next agent acts on.
 */
import type { CountyDecision, EscalateConfig, EscalateResult } from "./types.js";

export interface LetterComment {
  caseId: string | null;
  level: string | null;
  receivedOn: string;
  messageId: string;
  text: string;
}

const HEAD = /^\s*decision-letter\s*·\s*case\s+(\S+)\s*·\s*level\s+(\S+)\s*·\s*received\s+(\d{4}-\d{2}-\d{2})\s*·\s*(\S+)\s*$/i;

/** Parse a decision-letter comment. Returns null if the first line is not in the agreed shape. */
export function parseLetterComment(comment: string): LetterComment | null {
  const lines = comment.replace(/\r\n/g, "\n").split("\n");
  const m = (lines[0] ?? "").match(HEAD);
  if (!m) return null;
  const unknown = (v: string) => (v.toLowerCase() === "unknown" ? null : v);
  return { caseId: unknown(m[1]!), level: unknown(m[2]!), receivedOn: m[3]!, messageId: m[4]!, text: lines.slice(1).join("\n").trim() };
}

export function decisionFromComment(l: LetterComment, fallbackLevel: string | null): CountyDecision {
  return {
    decisionId: l.messageId,
    caseId: l.caseId ?? "unknown",
    level: l.level ?? fallbackLevel ?? "unknown",
    receivedOn: l.receivedOn,
    channel: "email",
    text: l.text,
    attachments: [],
  };
}

/** The fields of a Qualify handoff.json entry Escalate uses. */
export interface QualifyHandoffEntry {
  find_case_id: string | null;
  parcelId?: string;
  jurisdictionId?: string;
  address?: string;
  judgedAsOf?: string;
  pWin?: number | null;
  route?: { id: string } | null;
  assessedValue?: number | null;
  targetValue?: number | null;
  taxRate?: number | null;
  owner?: { names: string[]; type: string } | null;
}

/** The owner's choices Sign up records on the case card. */
export interface SignedAuthorization {
  caseId: string;
  scope: string[];
  feePct: number;
  appealPartialIfRemainingAnnualAbove?: number;
  acceptReopenRisk: boolean;
  signedOn?: string;
}

/**
 * Parse Sign up's authorization line, e.g.
 *   authorization: case_id FL-13-2026-1 · scope vab_petition · fee 30% · partial_above 500 · reopen_risk no · signed 2026-09-01
 * Fields may come in any order; scope is "all_levels" or a comma list. Returns null unless the line
 * starts with "authorization:" and names a case id, a scope and a fee; anything unreadable → null
 * (the caller then uses the desk's narrow default).
 */
export function parseAuthorizationLine(text: string): SignedAuthorization | null {
  const line = text.replace(/\r\n/g, "\n").split("\n").find((l) => /^\s*authorization\s*:/i.test(l));
  if (!line) return null;
  const fields = new Map<string, string>();
  for (const part of line.replace(/^\s*authorization\s*:/i, "").split("·")) {
    const m = part.trim().match(/^([a-z_]+)\s+(.+)$/i);
    if (m) fields.set(m[1]!.toLowerCase(), m[2]!.trim());
  }
  const caseId = fields.get("case_id");
  const scope = fields.get("scope")?.split(/[,\s]+/).filter(Boolean);
  const feeM = fields.get("fee")?.match(/^(\d+(?:\.\d+)?)\s*%$/);
  if (!caseId || !scope?.length || !feeM) return null;
  const feePct = Number(feeM[1]) / 100;
  if (!(feePct >= 0 && feePct <= 1)) return null;
  const pa = fields.get("partial_above");
  let appealPartialIfRemainingAnnualAbove: number | undefined;
  if (pa && !/^none$/i.test(pa)) {
    const n = Number(pa.replace(/[$,]/g, "").replace(/\/\s*(yr|year)$/i, ""));
    if (!Number.isFinite(n) || n < 0) return null;
    appealPartialIfRemainingAnnualAbove = n;
  }
  const rr = fields.get("reopen_risk");
  if (rr && !/^(yes|no)$/i.test(rr)) return null;
  const signed = fields.get("signed");
  return {
    caseId,
    scope,
    feePct,
    ...(appealPartialIfRemainingAnnualAbove !== undefined ? { appealPartialIfRemainingAnnualAbove } : {}),
    acceptReopenRisk: /^yes$/i.test(rr ?? "no"),
    ...(signed && /^\d{4}-\d{2}-\d{2}$/.test(signed) ? { signedOn: signed } : {}),
  };
}

/**
 * The Escalate case for a letter, from Qualify's handoff entry. Uses the owner's signed
 * authorization when Sign up recorded one for this case; otherwise the desk's narrow default,
 * marked authorizationSource: desk_default.
 */
export function caseFromQualify(entry: QualifyHandoffEntry, letter: LetterComment, cfg: EscalateConfig, opts: { readAttempts?: unknown[]; contactChannel?: string; signed?: SignedAuthorization | null } = {}): Record<string, unknown> {
  const auth = cfg.defaultAuthorization;
  const signed = opts.signed && opts.signed.caseId === entry.find_case_id ? opts.signed : null;
  const authorization = signed
    ? {
        signedOn: signed.signedOn ?? entry.judgedAsOf ?? letter.receivedOn,
        feePct: signed.feePct,
        scope: signed.scope,
        escalation: {
          ...(signed.appealPartialIfRemainingAnnualAbove !== undefined ? { appealPartialIfRemainingAnnualAbove: signed.appealPartialIfRemainingAnnualAbove } : {}),
          acceptReopenRisk: signed.acceptReopenRisk,
        },
      }
    : auth
      ? { signedOn: entry.judgedAsOf ?? letter.receivedOn, feePct: auth.feePct, scope: auth.scope }
      : undefined;
  return {
    caseId: entry.find_case_id,
    parcelId: entry.parcelId,
    jurisdictionId: entry.jurisdictionId,
    address: entry.address,
    owner: { names: entry.owner?.names ?? [], type: entry.owner?.type ?? "individual", contactChannel: opts.contactChannel ?? "mail" },
    assessedValue: entry.assessedValue ?? undefined,
    targetValue: entry.targetValue ?? undefined,
    taxRate: entry.taxRate ?? undefined,
    ...(typeof entry.pWin === "number" ? { qualify: { pWin: entry.pWin } } : {}),
    currentLevel: letter.level ?? entry.route?.id,
    filings: [],
    authorization,
    authorizationSource: signed ? "signed" : "desk_default",
    readAttempts: opts.readAttempts ?? [],
  };
}

const NEXT: Record<EscalateResult["status"], (r: EscalateResult) => string> = {
  ESCALATE: (r) => `Evidence (${r.evidenceRequests.map((e) => e.key).join(", ") || "no new items"}) → File by ${r.nextLevel?.deadline}`,
  COLLECT: () => "Collect",
  CLOSED: () => "case closed",
  PENDING: (r) => `Chase on ${r.requeueOn}`,
  INCOMPLETE: () => "Chase: re-fetch the letter",
};

/** The comment the agent posts on the case card. */
export function resultComment(r: EscalateResult, cardId: string): { op: "comment"; card_id: string; body: string } {
  const code = r.summary.split(" · ")[1] ?? r.reasonCodes[0] ?? "";
  const lines = [
    `escalate-result · ${r.status} · ${code} · ${r.decisionId ?? "no letter"}`,
    r.summary,
    `next: ${NEXT[r.status](r)}`,
    ...(r.flags.length ? [`flags: ${r.flags.join(", ")}`] : []),
    ...r.evidenceRequests.map((e) => `evidence: ${e.key} (${e.why})`),
    ...(r.ownerUpdate ? [`owner-update (${r.ownerUpdate.channel}, auto-send): ${r.ownerUpdate.subject}: ${r.ownerUpdate.body}`] : []),
    ...(r.readState ? [`read-state: ${JSON.stringify(r.readState)}`] : []),
  ];
  return { op: "comment", card_id: cardId, body: lines.join("\n") };
}

/** The last ```json block in a card body (Find's case data on a "Waiting on" card), or null. */
export function findCaseBlock(cardBody: string): string | null {
  const blocks = [...cardBody.matchAll(/```json\s*\n([\s\S]*?)```/g)];
  const last = blocks.at(-1)?.[1]?.trim();
  if (!last) return null;
  try {
    JSON.parse(last);
    return last;
  } catch {
    return null;
  }
}

export type BoardWrite =
  | { op: "comment"; card_id: string; body: string }
  | { op: "update"; card_id: string; status: "done" | "blocked"; note: string }
  | { op: "create"; title: string; assignee: string; status: "todo"; key: string; body: string };

/**
 * Every board write for one letter, in order:
 * 1. the escalate-result comment;
 * 2. the "Waiting on" card update, so the case's stage is visible (Chase stops on a card once it
 *    writes `escalate`, and the Escalate desk owns it from then on):
 *    COLLECT → done, note "WON · …" · CLOSED → done, note "STOPPED · …" · ESCALATE → blocked,
 *    note "APPEAL · …" · PENDING and INCOMPLETE → no update (Chase picks the card up again);
 * 3. ESCALATE only: an Evidence hand-off card assigned to `evidence`, in the shape the Evidence agent
 *    reads (body ends in the case's original ```json block). Skipped when the card has no case block.
 */
export function cardWrites(r: EscalateResult, card: { id: string; body?: string; address?: string }): { writes: BoardWrite[]; notes: string[] } {
  const writes: BoardWrite[] = [resultComment(r, card.id)];
  const notes: string[] = [];
  const code = r.summary.split(" · ")[1] ?? r.reasonCodes[0] ?? "";
  const tail = r.summary.split(" · ").slice(2).join(" · ");
  if (r.status === "COLLECT") {
    writes.push({ op: "update", card_id: card.id, status: "done", note: `WON · ${code} · ${tail} · next: Collect` });
    const f = r.reading.verified;
    if (f?.newAssessedValue !== undefined && r.collect) {
      const block = card.body ? findCaseBlock(card.body) : null;
      writes.push({
        op: "create",
        title: `Collect · ${card.address ?? r.address} · ${r.caseId}`,
        assignee: "collect",
        status: "todo",
        key: `escalate-collect-${r.caseId}-${r.decisionId ?? "letter"}`,
        body: [
          `From Escalate: ${code} · the county lowered the value; confirm the corrected bill, then invoice.`,
          `collect-handoff · case ${r.caseId} · old ${r.collect.oldValue} · won ${f.newAssessedValue} · decided ${r.collect.decidedOn} · letter ${r.decisionId} · code ${code}`,
          ...(block ? ["", "```json", block, "```"] : []),
        ].join("\n"),
      });
    } else notes.push("won without a verified new value; Collect card not created");
  }
  if (r.status === "CLOSED") writes.push({ op: "update", card_id: card.id, status: "done", note: `STOPPED · ${code} · ${tail}` });
  if (r.status === "ESCALATE") {
    writes.push({ op: "update", card_id: card.id, status: "blocked", note: `APPEAL · ${code} · ${tail} · next: Evidence → File` });
    const block = card.body ? findCaseBlock(card.body) : null;
    if (!block) notes.push("no case JSON block on the card; Evidence hand-off card not created");
    else {
      const fixes = r.evidenceRequests.map((e) => `fix: ${e.key} (${e.why})`);
      writes.push({
        op: "create",
        title: `Evidence · ${card.address ?? r.address} · ${r.caseId}`,
        assignee: "evidence",
        status: "todo",
        key: `escalate-evidence-${r.caseId}-${r.decisionId ?? "letter"}`,
        body: [
          `From Escalate: ${code} · ${r.nextLevel ? `${r.nextLevel.name} (${r.nextLevel.formId}) by ${r.nextLevel.deadline}` : "next filing"}`,
          ...fixes,
          r.nextLevel ? `petition_deadline: ${r.nextLevel.deadline}` : "",
          "",
          "```json",
          block,
          "```",
        ]
          .filter((l, i, all) => l !== "" || all[i + 1] === "```json")
          .join("\n"),
      });
    }
  }
  return { writes, notes };
}
