/**
 * S5 · Timing & route — is a filing route open with enough time to finish, and which one?
 *
 * A route is feasible when it is open today and
 *   closes − today − bufferDays ≥ workDaysNeeded
 * and it accepts the claim basis. Among feasible (route, basis) pairs we pick the highest EV,
 * breaking ties by more days left. Nothing feasible → NEXT_CYCLE with a re-qualify date.
 */
import { stop, log, type Draft } from "../draft.js";
import { addDays, clamp, daysBetween, round } from "../util.js";
import { pairs } from "./s4-economics.js";

export function timing(d: Draft): void {
  const { cfg, today } = d;
  const t = cfg.thresholds;
  // A pair is viable if its basis clears the gap minimum and its EV clears the EV minimum.
  const all = pairs(d)
    .map((p) => ({ ...p, daysLeft: daysBetween(today, p.route.closes) - p.route.bufferDays }))
    .filter((p) => p.basis.gapPct >= t.minGapPct && p.econ.ev >= t.minExpectedValue);
  if (all.length === 0) return stop(d, "S5", "C_EV_LOW", "no route + basis clears both the gap and EV minimums");
  const feasible = all.filter((p) => p.route.opens <= today && today <= p.route.closes && p.daysLeft >= p.route.workDaysNeeded);

  // Viable claims exist (S4 guaranteed at least one) but none can be filed now → wait for a window.
  if (feasible.length === 0) {
    const later = cfg.routes.map((r) => r.opens).filter((o) => o > today).sort()[0] ?? cfg.nextCycleOpens ?? null;
    d.requalifyOn = later ? addDays(later, -cfg.timing.requalifyLeadDays) : null;
    if (d.requalifyOn && d.requalifyOn < today) d.requalifyOn = today;
    const why = all
      .map((p) => {
        const r = p.route;
        const state =
          today < r.opens ? `opens ${r.opens}` : today > r.closes ? `closed ${r.closes}` : `${p.daysLeft}d left, need ${r.workDaysNeeded}`;
        return `${p.basis.basis} via ${r.id}: ${state}`;
      })
      .join("; ");
    return stop(d, "S5", "T_NO_ROUTE", `${why}${d.requalifyOn ? ` · re-qualify ${d.requalifyOn}` : " · load next cycle's config"}`);
  }

  // File now if we can, even if a stronger claim would open later.
  feasible.sort((a, b) => b.econ.ev - a.econ.ev || b.daysLeft - a.daysLeft);
  const pick = feasible[0]!;

  const work = Math.max(pick.route.workDaysNeeded, 1);
  const slack = pick.daysLeft - pick.route.workDaysNeeded;
  const urgency = 1 + (cfg.timing.urgencyMaxBoost - 1) * clamp(1 - slack / (2 * work), 0, 1);

  const v = d.valuation!;
  Object.assign(v, { basis: pick.basis.basis, target: pick.basis.target, gap: pick.basis.gap, gapPct: pick.basis.gapPct });
  d.economics = pick.econ;
  d.route = {
    id: pick.route.id,
    name: pick.route.name,
    formId: pick.route.formId,
    deadline: pick.route.closes,
    daysLeft: pick.daysLeft,
    urgency: round(urgency, 2),
  };
  log(d, "S5", "pass", `${pick.route.id} (${pick.basis.basis}) · ${pick.daysLeft}d left · EV ${pick.econ.ev}`);
}
