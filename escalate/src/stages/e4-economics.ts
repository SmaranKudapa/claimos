/** E4 · Is it still worth it? Remaining gap, probability at the next level, cost, expected value. */
import { block, log, type Draft } from "../draft.js";
import { clamp, round } from "../util.js";

/** Denial reasons with unknown keys count as "other". */
export function reasonKeys(d: Draft): string[] {
  const cfg = d.ctx.config;
  return [...new Set((d.facts?.reasonCategories ?? []).map((k) => (cfg.denialReasons[k] ? k : "other")))];
}

export function economics(d: Draft): void {
  const { ctx, c } = d;
  const e = ctx.config.economics;
  const rung = d.next!.rung;
  const gap = d.currentValue - c.targetValue;
  const gapPct = gap / d.currentValue;
  const annual = gap * c.taxRate;
  const revenue = (c.authorization.feePct ?? e.feePct) * annual * e.persistenceCycles;
  let basePWin = c.qualify?.pWin;
  if (basePWin === undefined) {
    d.flags.add("F_DEFAULT_PWIN");
    basePWin = e.defaultPWin;
  }
  const reasonFactor = reasonKeys(d).reduce((p, k) => p * ctx.config.denialReasons[k]!.pWinMultiplier, 1);
  const pWin = clamp(basePWin * rung.pWinMultiplier * reasonFactor, 0, e.pWinCap);
  const costs = rung.filingFee + e.costs.evidenceRefresh + (rung.hearing ? e.costs.hearingPrep : 0) + e.costs.llm;
  const ev = pWin * revenue - costs;
  d.economics = {
    gap: round(gap),
    gapPct: round(gapPct, 4),
    annual: round(annual, 2),
    revenue: round(revenue, 2),
    pWin: round(pWin, 3),
    costs: round(costs, 2),
    ev: round(ev, 2),
    maxLoss: round(costs, 2),
  };
  if (gapPct < e.minRemainingGapPct || annual < e.minRemainingAnnualSavings)
    return block(d, "E4", "C_SMALL_GAP", `remaining gap ${(gapPct * 100).toFixed(1)}% / $${round(annual)}/yr below minimums`);
  if (pWin < e.pWinFloor) return block(d, "E4", "C_LOW_PWIN", `P(win) ${round(pWin, 3)} < ${e.pWinFloor}`);
  if (ev < e.minExpectedValue) return block(d, "E4", "C_LOW_EV", `EV $${round(ev, 2)} < $${e.minExpectedValue}`);
  log(d, "E4", "pass", `gap ${round(gap)} · $${round(annual)}/yr · P(win) ${round(pWin, 3)} · costs $${round(costs, 2)} · EV $${round(ev, 2)}`);
}
