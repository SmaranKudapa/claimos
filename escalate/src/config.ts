import { readFileSync } from "node:fs";
import { EscalateConfigSchema, type EscalateConfig, type Rung } from "./types.js";

/** Load and validate a desk config. A bad config throws and lists every bad path. */
export function parseConfig(raw: unknown, label = "config"): EscalateConfig {
  const parsed = EscalateConfigSchema.safeParse(raw);
  if (!parsed.success) {
    const lines = parsed.error.issues.map((i) => `  - ${i.path.join(".") || "(root)"}: ${i.message}`);
    throw new Error(`Invalid escalate config ${label}:\n${lines.join("\n")}`);
  }
  return parsed.data;
}

export function loadConfig(path: string): EscalateConfig {
  return parseConfig(JSON.parse(readFileSync(path, "utf8")), path);
}

/** A rung by id or alias. */
export function rungById(cfg: EscalateConfig, id: string): Rung | undefined {
  return cfg.ladder.find((r) => r.id === id || r.aliases.includes(id));
}

/** Does a case's jurisdiction belong to this desk? Exact id, or a sub-jurisdiction "<desk id>-…". */
export function coversJurisdiction(cfg: EscalateConfig, jurisdictionId: string): boolean {
  return jurisdictionId === cfg.jurisdictionId || jurisdictionId.startsWith(`${cfg.jurisdictionId}-`);
}
