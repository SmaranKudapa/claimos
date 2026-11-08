import { readFileSync } from "node:fs";
import { DeskConfigSchema, SuppressionSchema, type DeskConfig, type Suppression } from "./types.js";

/**
 * Load and validate a desk config. A bad config throws — it must stop the run
 * rather than produce wrong decisions.
 */
export function loadDeskConfig(path: string): DeskConfig {
  const raw = JSON.parse(readFileSync(path, "utf8"));
  const parsed = DeskConfigSchema.safeParse(raw);
  if (!parsed.success) {
    const lines = parsed.error.issues.map((i) => `  - ${i.path.join(".") || "(root)"}: ${i.message}`);
    throw new Error(`Invalid desk config ${path}:\n${lines.join("\n")}`);
  }
  return parsed.data;
}

export function loadSuppression(path?: string): Suppression {
  if (!path) return SuppressionSchema.parse({});
  return SuppressionSchema.parse(JSON.parse(readFileSync(path, "utf8")));
}
