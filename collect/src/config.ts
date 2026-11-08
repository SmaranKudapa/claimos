import { readFileSync } from "node:fs";
import { CollectConfigSchema, type CollectConfig } from "./types.js";

/** Load and validate a desk config. A bad config throws and lists every bad path. */
export function parseConfig(raw: unknown, label = "config"): CollectConfig {
  const parsed = CollectConfigSchema.safeParse(raw);
  if (!parsed.success) {
    const lines = parsed.error.issues.map((i) => `  - ${i.path.join(".") || "(root)"}: ${i.message}`);
    throw new Error(`Invalid collect config ${label}:\n${lines.join("\n")}`);
  }
  return parsed.data;
}
export const loadConfig = (path: string) => parseConfig(JSON.parse(readFileSync(path, "utf8")), path);
export const coversJurisdiction = (cfg: CollectConfig, id: string) => id === cfg.jurisdictionId || id.startsWith(`${cfg.jurisdictionId}-`);
