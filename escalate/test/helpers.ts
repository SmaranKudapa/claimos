import { loadConfig } from "../src/config.js";
import type { EscalateContext } from "../src/draft.js";
import { MockReader } from "../src/reader/mock.js";
import { ReaderError, type ReadOutcome, type Reader } from "../src/reader/types.js";
import type { DecisionReading, EscalateConfig } from "../src/types.js";
import { SAMPLE_TODAY } from "../scripts/samples.js";

export const config = (): EscalateConfig => loadConfig("config/escalate.placeholder.json");
export const floridaConfig = (): EscalateConfig => loadConfig("config/escalate.florida.json");

export function ctx(over: Partial<EscalateContext> = {}): EscalateContext {
  return { config: config(), today: SAMPLE_TODAY, reader: new MockReader(), models: { primary: "first-model", escalation: "strong-model" }, ...over };
}

/** Returns a scripted reading per model; records calls. */
export class ScriptedReader implements Reader {
  readonly name = "scripted";
  calls: string[] = [];
  constructor(private byModel: Record<string, DecisionReading>) {}
  async read(_d: unknown, _c: unknown, _cfg: unknown, opts: { model: string | null }): Promise<ReadOutcome> {
    this.calls.push(String(opts.model));
    const r = this.byModel[String(opts.model)];
    if (!r) throw new Error(`no scripted reading for ${opts.model}`);
    return { reading: r, model: String(opts.model), costUsd: 0.001, cached: false };
  }
}

/** Always fails like a network error or invalid JSON twice. */
export class FailingReader implements Reader {
  readonly name = "failing";
  async read(): Promise<ReadOutcome> {
    throw new ReaderError("simulated network error");
  }
}
