/** Writes data/cases.sample.json ([{ case, bill, reading }]) from scripts/samples.ts. */
import { mkdirSync, writeFileSync } from "node:fs";
import { buildSamples } from "./samples.js";

const samples = buildSamples();
mkdirSync("data", { recursive: true });
writeFileSync("data/cases.sample.json", JSON.stringify(samples.map((s) => ({ case: s.case, bill: s.bill, reading: s.reading })), null, 2) + "\n");
console.log(`wrote ${samples.length} sample cases to data/`);
