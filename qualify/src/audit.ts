/**
 * Append-only audit log (JSON Lines). One record per decision: inputs hash, config version,
 * every stage's outcome, the LLM review, the final decision, and who made it.
 * Answers "why did the agent contact this person?" and lets you replay decisions.
 */
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { QualifyResult } from "./types.js";

export interface AuditRecord {
  event: "qualified" | "reviewed";
  caseId: string;
  at: string;
  today?: string;
  configVersion: string;
  inputHash: string;
  status: string;
  reasonCodes: string[];
  flags: string[];
  decidedBy: string;
  stageLog: QualifyResult["stageLog"];
  llm?: QualifyResult["llm"];
  review?: QualifyResult["audit"]["review"];
}

export function toAuditRecord(r: QualifyResult, event: AuditRecord["event"], today?: string): AuditRecord {
  return {
    event,
    caseId: r.caseId,
    at: event === "reviewed" ? r.audit.review?.at ?? r.audit.decidedAt : r.audit.decidedAt,
    ...(today ? { today } : {}),
    configVersion: r.audit.configVersion,
    inputHash: r.audit.inputHash,
    status: r.status,
    reasonCodes: r.reasonCodes,
    flags: r.flags,
    decidedBy: r.audit.decidedBy,
    stageLog: r.stageLog,
    ...(r.llm ? { llm: r.llm } : {}),
    ...(r.audit.review ? { review: r.audit.review } : {}),
  };
}

export function appendAudit(path: string, records: AuditRecord[]) {
  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, records.map((r) => JSON.stringify(r)).join("\n") + (records.length ? "\n" : ""));
}
