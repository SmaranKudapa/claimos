/**
 * The working state a lead carries through the pipeline. Stages read and mutate it;
 * a stage stops the lead by calling `stop()`.
 */
import { statusForCode } from "./codes.js";
import type {
  Candidate,
  DecidedBy,
  DeskConfig,
  Economics,
  LlmReview,
  RoutePick,
  StageId,
  StageLogEntry,
  Status,
  Suppression,
  QualifyResult,
  Valuation,
} from "./types.js";
import type { LlmClient, LlmCache } from "./llm/client.js";

export interface QualifyContext {
  config: DeskConfig;
  today: string;
  suppression: Suppression;
  /** Last run's results by caseId — used for the rejection cache (S_CACHED). */
  priorResults: Map<string, QualifyResult>;
  /** Null disables S6 (the lead is still decided by rules). */
  llm: LlmClient | null;
  llmCache?: LlmCache;
  /** Model ids resolved from config/env. */
  models?: { primary: string | null; escalation: string | null };
}

export interface Draft {
  cand: Candidate;
  cfg: DeskConfig;
  today: string;
  caseId: string;
  inputHash: string;
  flags: Set<string>;
  codes: string[];
  stageLog: StageLogEntry[];
  stopped?: { status: Status };
  valuation?: Valuation;
  economics?: Economics;
  route?: RoutePick;
  requalifyOn: string | null;
  excludedComps: Set<string>;
  /** Reasons a human must look at this lead, beyond flags. */
  forceReview: string[];
  decidedBy: DecidedBy;
  llm?: LlmReview;
  /** Bounded adjustment from the LLM, applied in S4/S5 math. */
  pWinAdjustment: number;
}

export function log(d: Draft, stage: StageId, outcome: StageLogEntry["outcome"], detail?: string) {
  d.stageLog.push(detail ? { stage, outcome, detail } : { stage, outcome });
}

/** Stop the lead with one or more codes. Status comes from the first code's prefix. */
export function stop(d: Draft, stage: StageId, codes: string | string[], detail: string) {
  const list = Array.isArray(codes) ? codes : [codes];
  d.codes.push(...list);
  const status = statusForCode(list[0]!) ?? "REJECTED";
  d.stopped = { status };
  log(d, stage, "stop", detail);
}

export const caseIdFor = (jurisdictionId: string, parcelId: string) => `case_${jurisdictionId}_${parcelId}`;
