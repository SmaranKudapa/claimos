/**
 * A reading supplied from outside, e.g. by the Naïve agent that read the letter itself (agents
 * cannot call the model proxy with an API key). The program still checks every quote and decides.
 * Readings[0] answers the first read; readings[1], if given, answers the second read.
 */
import { DecisionReadingSchema, type DecisionReading } from "../types.js";
import { ReaderError, type ReadOutcome, type Reader } from "./types.js";

export class ProvidedReader implements Reader {
  readonly name = "agent";
  private readings: DecisionReading[];

  constructor(raw: unknown) {
    const list = Array.isArray(raw) ? raw : [raw];
    this.readings = list.map((r, i) => {
      const p = DecisionReadingSchema.safeParse(r);
      if (!p.success) throw new ReaderError(`reading ${i + 1} is invalid: ${p.error.issues.slice(0, 2).map((x) => `${x.path.join(".")}: ${x.message}`).join("; ")}`);
      return p.data;
    });
    if (!this.readings.length) throw new ReaderError("no reading supplied");
  }

  async read(_d: unknown, _c: unknown, _cfg: unknown, opts: { secondRead: boolean }): Promise<ReadOutcome> {
    const r = opts.secondRead ? (this.readings[1] ?? this.readings[0]!) : this.readings[0]!;
    return { reading: r, model: opts.secondRead && this.readings[1] ? "agent-second-read" : "agent", costUsd: 0, cached: false };
  }
}
