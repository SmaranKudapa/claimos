/**
 * S3 · Valuation — is the property overassessed, by how much, and how sure are we?
 *
 * 1. Select comps by the desk's comp rules; score each on similarity; keep the best.
 * 2. Each comp implies a subject value (v1: price per unit area × subject area).
 * 3. Estimate = median implied value; range = middle half (25th–75th percentile).
 * 4. Confidence from comp count, spread, similarity, and missing optional fields.
 * 5. Target = the cautious end: estimate moved toward assessed value as confidence falls.
 * 6. Optional uniformity basis if the desk allows it and the data is present.
 */
import { stop, log, type Draft } from "../draft.js";
import type { BasisOption, Candidate, Comp, DeskConfig, ScoredComp } from "../types.js";
import { clamp, daysBetween, mean, median, quantile, round } from "../util.js";

export interface CompSelection {
  selected: (ScoredComp & { comp: Comp })[];
  considered: number;
}

export function selectComps(c: Candidate, cfg: DeskConfig, excluded: Set<string>, today: string): CompSelection {
  const r = cfg.compRules;
  const vd = cfg.jurisdiction.valuationDate;
  const span = r.saleWindowBeforeDays + r.saleWindowAfterDays || 1;
  const subj = c.physical.livingArea;
  const out: (ScoredComp & { comp: Comp })[] = [];
  for (const k of c.comps ?? []) {
    if (excluded.has(k.compId) || k.compId === c.parcelId) continue;
    const offset = daysBetween(vd, k.saleDate); // negative = before valuation date
    if (offset < -r.saleWindowBeforeDays || offset > r.saleWindowAfterDays || k.saleDate > today) continue;
    if (k.distance > r.maxDistance) continue;
    const sizeDiff = Math.abs(k.livingArea - subj) / subj;
    if (sizeDiff > r.sizeTolerance) continue;
    if (r.armsLengthOnly && !k.armsLength) continue;
    if (r.sameTypeOnly && k.propertyType !== c.propertyType) continue;
    let ageTerm = 0;
    if (r.ageTolerance && k.yearBuilt !== undefined && c.physical.yearBuilt !== undefined) {
      const ageDiff = Math.abs(k.yearBuilt - c.physical.yearBuilt);
      if (ageDiff > r.ageTolerance) continue;
      ageTerm = ageDiff / r.ageTolerance;
    }
    const similarity = clamp(
      1 - (0.35 * (k.distance / r.maxDistance) + 0.35 * (sizeDiff / r.sizeTolerance) + 0.2 * (Math.abs(offset) / span) + 0.1 * ageTerm),
      0,
      1,
    );
    out.push({ compId: k.compId, similarity: round(similarity, 3), impliedValue: round((k.price / k.livingArea) * subj), comp: k });
  }
  out.sort((a, b) => b.similarity - a.similarity);
  return { selected: out.slice(0, r.maxComps), considered: c.comps?.length ?? 0 };
}

export function valuation(d: Draft): void {
  const { cand: c, cfg } = d;
  const t = cfg.thresholds;

  if (!c.comps) return stop(d, "S3", "I_NO_COMPS", "comps were never fetched");

  const sel = selectComps(c, cfg, d.excludedComps, d.today);
  if (sel.selected.length < cfg.compRules.minComps)
    return stop(d, "S3", "V_INSUFFICIENT_COMPS", `${sel.selected.length} usable of ${sel.considered} (need ${cfg.compRules.minComps})`);

  const implied = sel.selected.map((s) => s.impliedValue);
  const estimate = median(implied);
  const low = quantile(implied, 0.25);
  const high = quantile(implied, 0.75);

  const countF = Math.min(1, sel.selected.length / (cfg.compRules.minComps + 2));
  const spreadF = clamp(1 - (2 * (high - low)) / estimate, 0.3, 1);
  const simF = 0.5 + 0.5 * mean(sel.selected.map((s) => s.similarity));
  const missing = [c.physical.yearBuilt, c.physical.lotArea].filter((x) => x === undefined).length;
  const confidence = round(clamp(countF * spreadF * simF - 0.05 * missing, 0, 1), 2);

  const assessed = c.assessment.assessedValue;
  const bases: BasisOption[] = [];
  const marketTarget = Math.min(assessed, estimate + (1 - confidence) * (high - low));
  if (cfg.jurisdiction.allowedClaimBases.includes("market_value")) bases.push(option("market_value", marketTarget, assessed));
  if (cfg.jurisdiction.allowedClaimBases.includes("uniformity") && c.neighborhood) {
    // Equal treatment: argue for the neighborhood's typical assessment ratio, applied to our cautious value.
    const uniTarget = Math.min(assessed, marketTarget * c.neighborhood.medianAssessmentRatio);
    bases.push(option("uniformity", uniTarget, assessed));
  }
  const positive = bases.filter((b) => b.gap > 0).sort((a, b) => b.gap - a.gap);
  const best = positive[0];

  d.valuation = {
    estimate: round(estimate),
    low: round(low),
    high: round(high),
    confidence,
    compsUsed: sel.selected.map(({ comp: _comp, ...s }) => s),
    compsExcluded: [...d.excludedComps],
    bases: positive,
    basis: best?.basis ?? "market_value",
    target: round(best?.target ?? marketTarget),
    gap: round(best?.gap ?? assessed - marketTarget),
    gapPct: round(best?.gapPct ?? (assessed - marketTarget) / assessed, 4),
  };

  if (!best) return stop(d, "S3", "V_NO_GAP", `assessed ${round(assessed)} ≤ cautious estimate ${round(marketTarget)}`);
  if (best.gapPct < t.minGapPct)
    return stop(d, "S3", "V_GAP_SMALL", `gap ${(best.gapPct * 100).toFixed(1)}% < ${(t.minGapPct * 100).toFixed(1)}%`);

  if (confidence < t.minConfidence) {
    const savings = best.gap * c.assessment.taxRate;
    if (savings < t.highValueReviewThreshold)
      return stop(d, "S3", "V_LOW_CONFIDENCE", `confidence ${confidence} < ${t.minConfidence}`);
    d.flags.add("F_LOW_CONFIDENCE");
  }

  log(d, "S3", "pass", `${sel.selected.length} comps · est ${round(estimate)} · conf ${confidence} · ${best.basis} gap ${(best.gapPct * 100).toFixed(1)}%`);
}

function option(basis: BasisOption["basis"], target: number, assessed: number): BasisOption {
  const gap = assessed - target;
  return { basis, target: round(target), gap: round(gap), gapPct: round(gap / assessed, 4) };
}
