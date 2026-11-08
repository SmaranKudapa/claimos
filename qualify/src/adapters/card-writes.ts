/** Board writes for the Qualify agent, built from a find-run handoff.json. */
/**
 * Exact board writes for an agent to send: one JSON line per card, built from a find-run
 * handoff.json. Input pairs are "<card id>=<Find case id>". Each line carries `write` (send it
 * as is with board_write) and `if_done` (send instead if the card is already done). The agent
 * never composes, splits or shortens a card update itself.
 */
export function cardWrites(h: { replay?: boolean; cases: Record<string, unknown>[] }, pairs: string[]): Record<string, unknown>[] {
  const byId = new Map(h.cases.map((c) => [String(c.find_case_id), c]));
  const money = (v: unknown) => (typeof v === "number" ? `$${Math.round(v).toLocaleString("en-US")}` : "?");
  const out: Record<string, unknown>[] = [];
  for (const raw of pairs) {
    const [cardId, caseId] = raw.split("=").map((x) => x?.trim() ?? "");
    if (!cardId) continue;
    if (!caseId) {
      out.push({ card_id: cardId, error: "expected <card id>=<case id>" });
      continue;
    }
    const c = byId.get(caseId) as
      | { status: string; summary: string; flags: string[]; reasonCodes: string[]; annualSavings: number | null; fee: number | null; pWin: number | null; route: { form: string; deadline: string } | null; requalifyOn: string | null; releaseDate: string | null; replayed?: boolean; jurisdictionId?: string }
      | undefined;
    if (!c) {
      out.push({ card_id: cardId, case_id: caseId, error: "case not in handoff.json; leave this card untouched" });
      continue;
    }
    // Replay is per case (only counties whose real window has closed); older handoffs carry one flag.
    const tag = (c.replayed ?? h.replay) ? " (replay)" : "";
    let status = "blocked";
    let note: string;
    // No desk for this state yet: hold the card (not a rejection) so it can be qualified once a desk exists.
    const noDesk = c.reasonCodes.includes("E_NO_DESK");
    switch (noDesk ? "NO_DESK" : c.status) {
      case "NO_DESK":
        note = `NO_DESK · no Qualify desk settings for ${String(c.jurisdictionId ?? "this jurisdiction").split("-")[0]} yet; held, not judged`;
        break;
      case "QUALIFIED":
        status = "done";
        note =
          `QUALIFIED${tag} · savings ${money(c.annualSavings)}/yr · fee ${money(c.fee)} · P(win) ${c.pWin ?? "?"}` +
          (c.route ? ` · ${c.route.form} due ${c.route.deadline}` : "") +
          (c.releaseDate ? ` · released ${c.releaseDate}` : " · queued") +
          ` · ${c.summary}`;
        break;
      case "NEEDS_REVIEW":
        note = `NEEDS_REVIEW${tag} · ${c.flags.join(", ")} · ${c.summary}`;
        break;
      case "NEXT_CYCLE":
        note = `NEXT_CYCLE${tag} · re-qualify on ${c.requalifyOn ?? "?"} · ${c.summary}`;
        break;
      case "INCOMPLETE":
        note = `INCOMPLETE${tag} · ${c.reasonCodes.join(", ")} · ${c.summary}`;
        break;
      default:
        status = "done";
        note = `REJECTED${tag} · ${c.reasonCodes.join(", ")} · ${c.summary}`;
    }
    out.push({
      card_id: cardId,
      case_id: caseId,
      write: { op: "update", card_id: cardId, status, note },
      if_done: { op: "comment", card_id: cardId, body: note },
    });
  }
  return out;
}
