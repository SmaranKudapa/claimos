// Copies every real desk template (config/desk.*.json, except the placeholder) into the agent bundle.
import { copyFileSync, mkdirSync, readdirSync } from "node:fs";
const out = "dist-agent/taxappeal-qualify/config";
mkdirSync(out, { recursive: true });
for (const f of readdirSync("config").filter((f) => /^desk\..+\.json$/.test(f) && f !== "desk.placeholder.json")) {
  copyFileSync(`config/${f}`, `${out}/${f}`);
  console.log(`bundled ${f}`);
}
