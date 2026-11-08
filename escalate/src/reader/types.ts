import type { CountyDecision, DecisionReading, EscalateCase, EscalateConfig } from "../types.js";

export interface ReadOutcome {
  reading: DecisionReading;
  model: string;
  costUsd: number;
  cached: boolean;
}

/** Reads facts out of a decision letter. It never decides what to do. */
export interface Reader {
  readonly name: string;
  /** `model` is the configured model for this read (first read or the stronger second read). */
  read(decision: CountyDecision, c: EscalateCase, cfg: EscalateConfig, opts: { model: string | null; secondRead: boolean }): Promise<ReadOutcome>;
}

/** Network error, invalid JSON twice, or over the cost cap. The pipeline retries later. */
export class ReaderError extends Error {}
