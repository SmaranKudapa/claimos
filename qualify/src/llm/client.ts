/**
 * The LLM boundary. S6 talks to this interface, never to a vendor SDK directly, so tests and
 * demos can swap in a scripted or heuristic reviewer.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export interface LlmRequest {
  model: string;
  system: string;
  user: string;
  tool: { name: string; description: string; input_schema: Record<string, unknown> };
  maxTokens: number;
  window: "immediate" | "priority" | "loose";
}

export interface LlmResponse {
  /** The tool call's input if the model called the tool. */
  toolInput?: unknown;
  /** Any text the model returned (used as a JSON fallback). */
  text: string;
  model: string;
  usage: { inputTokens: number; outputTokens: number };
}

export interface LlmClient {
  readonly name: string;
  complete(req: LlmRequest): Promise<LlmResponse>;
}

/** Caches parsed reviews by input hash, so unchanged leads are not re-reviewed. */
export interface LlmCache {
  get(key: string): unknown | undefined;
  set(key: string, value: unknown): void;
}

export class MemoryLlmCache implements LlmCache {
  private m = new Map<string, unknown>();
  get(k: string) {
    return this.m.get(k);
  }
  set(k: string, v: unknown) {
    this.m.set(k, v);
  }
}

export class FileLlmCache implements LlmCache {
  constructor(private dir: string) {
    mkdirSync(dir, { recursive: true });
  }
  get(k: string) {
    const p = join(this.dir, k + ".json");
    return existsSync(p) ? JSON.parse(readFileSync(p, "utf8")) : undefined;
  }
  set(k: string, v: unknown) {
    writeFileSync(join(this.dir, k + ".json"), JSON.stringify(v, null, 2));
  }
}
