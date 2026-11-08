/**
 * S4 · Economics — is it worth the money and effort to pursue?
 *
 *   EV = p(signup) × ( p(win) × fee − post_costs ) − pre_costs
 *
 * pre_costs are spent on every lead we contact; post_costs only after sign-up.
 * Economics depend on the route (fee, persistence, p(win) multiplier), so this stage
 * checks the best case over all routes; S5 then picks among the feasible ones.
 */
import { stop, log, type Draft } from "../draft.js";
import type { BasisOption, Economics, Route } from "../types.js";
import { clamp, round, sigmoid, sum } from "../util.js";

export function pWinFor(d: Draft, gapPct: number, route: Route): number {
  const p = d.cfg.economics.pWin;
  const conf = d.valuation!.confidence;
  const penalized = [...d.flags].filter((f) => p.penalizedFlags.includes(f)).length;
  const raw =
    sigmoid((gapPct - p.midpointGapPct) / p.scale) *
    (p.confidenceFloor + (1 - p.confidenceFloor) * conf) *
    route.pWinMultiplier *
    (1 - p.flagPenalty) ** penalized;
  return clamp(raw + d.pWinAdjustment, 0, p.cap);
}

export function evaluate(d: Draft, route: Route, b: BasisOption): Economics {
  const e = d.cfg.economics;
  const j = d.cfg.jurisdiction;
  const annualSavings = b.gap * d.cand.assessment.taxRate;
  const cycles = route.reductionPersistenceCycles ?? j.reductionPersistenceCycles;
  let totalSavings = 0;
  for (let k = 0; k < cycles; k++) totalSavings += annualSavings / (1 + j.discountRate) ** k;
  const fee = e.feePct * (e.feeBasis === "first_cycle" ? annualSavings : totalSavings);
  const pWin = pWinFor(d, b.gapPct, route);
  const pSignup = e.pSignupPrior * (d.flags.has("F_COMPLEX_OWNER") ? e.complexOwnerSignupFactor : 1);
  const preCosts = sum(e.preCosts);
  const postCosts = sum(e.postCosts) + route.filingFee;
  const ev = pSignup * (pWin * fee - postCosts) - preCosts;
  return {
    annualSavings: round(annualSavings),
    totalSavings: round(totalSavings),
    fee: round(fee, 2),
    pWin: round(pWin, 3),
    pSignup: round(pSignup, 3),
    preCosts: round(preCosts, 2),
    postCosts: round(postCosts, 2),
    ev: round(ev, 2),
    maxLoss: round(preCosts + postCosts, 2),
  };
}

/** Every (route, basis) pair the route accepts. */
export function pairs(d: Draft): { route: Route; basis: BasisOption; econ: Economics }[] {
  const out = [];
  for (const route of d.cfg.routes) {
    for (const b of d.valuation!.bases) {
      if (route.claimBases.includes(b.basis)) out.push({ route, basis: b, econ: evaluate(d, route, b) });
    }
  }
  return out;
}

export function economics(d: Draft): void {
  const t = d.cfg.thresholds;
  const best = d.valuation!.bases[0]!;
  const annual = best.gap * d.cand.assessment.taxRate;
  if (annual < t.minAnnualSavings)
    return stop(d, "S4", "C_SAVINGS_LOW", `savings ${round(annual)}/yr < ${t.minAnnualSavings}`);

  const all = pairs(d);
  if (all.length === 0) return stop(d, "S4", "C_EV_LOW", "no route accepts any claim basis with a gap");
  const top = all.reduce((a, b) => (b.econ.ev > a.econ.ev ? b : a));
  d.economics = top.econ; // provisional; S5 replaces with the feasible pick
  if (top.econ.ev < t.minExpectedValue)
    return stop(d, "S4", "C_EV_LOW", `best-case EV ${top.econ.ev} < ${t.minExpectedValue}`);

  log(d, "S4", "pass", `best-case EV ${top.econ.ev} via ${top.route.id}/${top.basis.basis}`);
}
