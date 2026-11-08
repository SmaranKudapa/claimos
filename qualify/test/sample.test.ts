/** End-to-end: the synthetic sample set should land every lead on its intended outcome. */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { loadSuppression } from "../src/config.js";
import { HeuristicReviewer } from "../src/llm/mock.js";
import { qualifyAll } from "../src/pipeline.js";
import { NOW, ctx } from "./helpers.js";

const EXPECTED: Record<string, string> = {
  "P-1001": "QUALIFIED",
  "P-1003": "QUALIFIED",
  "P-1023": "QUALIFIED",
  "P-1026": "QUALIFIED",
  "P-1002": "NEEDS_REVIEW",
  "P-1006": "NEEDS_REVIEW",
  "P-1007": "NEEDS_REVIEW",
  "P-1008": "NEEDS_REVIEW",
  "P-1020": "NEEDS_REVIEW",
  "P-1022": "NEEDS_REVIEW",
  "P-1021": "NEXT_CYCLE",
  "P-1010": "INCOMPLETE",
  "P-1011": "INCOMPLETE",
  "P-1016": "INCOMPLETE",
  "P-1004": "REJECTED",
  "P-1005": "REJECTED",
  "P-1009": "REJECTED",
  "P-1012": "REJECTED",
  "P-1013": "REJECTED",
  "P-1014": "REJECTED",
  "P-1015": "REJECTED",
  "P-1018": "REJECTED",
  "P-1019": "REJECTED",
  "P-1024": "REJECTED",
  "P-1025": "REJECTED",
};

describe("sample data", () => {
  it("every synthetic lead lands where it was designed to", async () => {
    const raws = JSON.parse(readFileSync("data/candidates.sample.json", "utf8"));
    const c = ctx({ llm: new HeuristicReviewer(), suppression: loadSuppression("data/suppression.sample.json") });
    const sum = await qualifyAll(raws, c, { now: NOW });
    expect(sum.merged).toBe(1);
    const got = Object.fromEntries(sum.results.map((r) => [r.parcelId, r.status]));
    expect(got).toEqual(EXPECTED);
    expect(sum.results.filter((r) => r.releaseDate)).toHaveLength(3);
  });
});
