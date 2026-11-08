/** E7 · Decision — the reason-code prefix decides the status; write the summary and owner update. */
import { statusFor } from "../codes.js";
import { log, type Draft } from "../draft.js";
import { ownerUpdate } from "../owner-update.js";
import type { OwnerUpdate, Status } from "../types.js";

export function decide(d: Draft): { status: Status; summary: string; ownerUpdate: OwnerUpdate | null } {
  if (!d.stopped && d.next) {
    const code = d.next.fastTrack ? "A_FAST_TRACK" : "A_NEXT_LEVEL";
    d.codes.push(code);
    log(d, "E7", "pass", `${code}: ${d.next.rung.id} by ${d.next.deadline}`);
  }
  let status = statusFor(d.codes);
  if (!status) {
    d.codes.push("C_UNHANDLED");
    log(d, "E7", "stop", "C_UNHANDLED: no decisive rule applied; closed conservatively");
    status = "CLOSED";
  }
  const lead = d.codes.find((c) => statusFor([c]) === status)!;
  return { status, summary: summarize(d, status, lead), ownerUpdate: ownerUpdate(d, status, lead) };
}

function summarize(d: Draft, status: Status, code: string): string {
  const f = d.facts;
  const read = f ? `${f.outcome.replace(/_/g, " ")}${f.newAssessedValue ? ` → ${f.newAssessedValue}` : ""}${f.reasonCategories.length ? ` (${f.reasonCategories.join(", ")})` : ""}` : "not read";
  const next = d.next ? ` · ${d.next.rung.name} by ${d.next.deadline}` : "";
  const ev = d.economics && status === "ESCALATE" ? ` · EV $${d.economics.ev}` : "";
  const when = d.requeueOn ? ` · check again ${d.requeueOn}` : "";
  return `${status} · ${code} · ${read}${next}${ev}${when}`;
}
