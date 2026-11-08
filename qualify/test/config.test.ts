import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadDeskConfig } from "../src/config.js";

const placeholder = () => JSON.parse(readFileSync("config/desk.placeholder.json", "utf8"));
const write = (cfg: unknown) => {
  const p = join(mkdtempSync(join(tmpdir(), "qualify-cfg-")), "desk.json");
  writeFileSync(p, JSON.stringify(cfg));
  return p;
};

describe("desk config validation", () => {
  it("the placeholder config loads, with defaults applied", () => {
    const c = loadDeskConfig("config/desk.placeholder.json");
    expect(c.jurisdiction.id).toBe("placeholder");
    expect(c.routes.map((r) => r.id)).toEqual(["review", "appeal"]);
  });

  it("a wrongly typed config throws and names every bad path", () => {
    const c = placeholder();
    c.thresholds.minGapPct = "x";
    c.routes[0].filer = "robot";
    delete c.compRules.minComps;
    let msg = "";
    try {
      loadDeskConfig(write(c));
    } catch (e) {
      msg = (e as Error).message;
    }
    expect(msg).toMatch(/^Invalid desk config/);
    for (const path of ["thresholds.minGapPct", "routes.0.filer", "compRules.minComps"]) expect(msg).toContain(path);
  });

  it("cross-field rules: unique route ids, closes ≥ opens, allowed bases, maxComps ≥ minComps", () => {
    const c = placeholder();
    c.routes[1].id = "review";
    c.routes[0].closes = "2026-08-01";
    c.jurisdiction.allowedClaimBases = ["market_value"];
    c.compRules.maxComps = 1;
    let msg = "";
    try {
      loadDeskConfig(write(c));
    } catch (e) {
      msg = (e as Error).message;
    }
    expect(msg).toContain("routes.1.id: duplicate route id review");
    expect(msg).toContain("routes.0.closes: closes before it opens");
    expect(msg).toContain("routes.1.claimBases: basis uniformity not allowed by jurisdiction");
    expect(msg).toContain("compRules.maxComps: maxComps < minComps");
  });
});
