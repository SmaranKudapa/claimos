/** Writes data/cases.sample.json and data/decisions.sample.json from scripts/samples.ts. */
import { mkdirSync, writeFileSync } from "node:fs";
import { buildSamples } from "./samples.js";

const samples = buildSamples();
mkdirSync("data", { recursive: true });
writeFileSync("data/cases.sample.json", JSON.stringify(samples.map((s) => s.case), null, 2) + "\n");
// Each letter names the case Chase delivered it with (deliveredFor), which can differ from the
// case the letter itself is about (sample 17).
writeFileSync("data/decisions.sample.json", JSON.stringify(samples.map((s) => ({ deliveredFor: s.case.caseId, ...s.decision })), null, 2) + "\n");
console.log(`wrote ${samples.length} sample cases and decision letters to data/`);
