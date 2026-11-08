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

/**
 * The Escalate case for a letter, from Qualify's handoff entry. Until Sign up records the owner's
 * authorization, the desk's narrow default is used and marked (authorizationSource: desk_default).
 */
export function caseFromQualify(entry: QualifyHandoffEntry, letter: LetterComment, cfg: EscalateConfig, opts: { readAttempts?: unknown[]; contactChannel?: string } = {}): Record<string, unknown> {
  const auth = cfg.defaultAuthorization;
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
    authorization: auth ? { signedOn: entry.judgedAsOf ?? letter.receivedOn, feePct: auth.feePct, scope: auth.scope } : undefined,
    authorizationSource: "desk_default",
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
