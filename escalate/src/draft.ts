/** The working state one case carries through stages E0–E7. */
import type { DecisionReading, EscalateCase, EscalateConfig, CountyDecision, EscalateResult, EvidenceRequest, Rung, StageLogEntry } from "./types.js";
import type { Reader } from "./reader/types.js";

export interface EscalateContext {
  config: EscalateConfig;
  today: string;
  /** Null only in tests; a real run without a reader is a config error. */
  reader: Reader | null;
  models?: { primary: string | null; escalation: string | null };
}

export type Mode = "partial" | "denied";

export interface Draft {
  ctx: EscalateContext;
  c: EscalateCase;
  d: CountyDecision;
  codes: string[];
  flags: Set<string>;
  log: StageLogEntry[];
  stopped: boolean;
  inputHash: string;
  reading: EscalateResult["reading"];
  /** The verified reading the rules act on (after quote check, numbers and fallbacks). */
  facts: DecisionReading | null;
  mode: Mode | null;
  currentValue: number;
  next: { rung: Rung; deadline: string; daysLeft: number; fastTrack: boolean } | null;
  economics: EscalateResult["economics"];
  evidenceRequests: EvidenceRequest[];
  requeueOn: string | null;
  readState: EscalateResult["readState"];
}

export function log(d: Draft, stage: string, outcome: StageLogEntry["outcome"], detail: string): void {
  d.log.push({ stage, outcome, detail });
}

/** Stop the case with a decisive reason code. */
export function stop(d: Draft, stage: string, code: string, detail: string): void {
  d.codes.push(code);
  d.stopped = true;
  log(d, stage, "stop", `${code}: ${detail}`);
}

/**
 * Stop a case that is blocked from appealing further. In partial mode the county already granted
 * a reduction, so the conservative outcome is to accept it (COLLECT), never to close the case.
 */
export function block(d: Draft, stage: string, closeCode: string, detail: string): void {
  if (d.mode === "partial") {
    d.flags.add("F_ESCALATION_BLOCKED");
    stop(d, stage, "W_PARTIAL_ACCEPTED", `${detail} (would be ${closeCode}; partial win accepted instead)`);
  } else stop(d, stage, closeCode, detail);
}
