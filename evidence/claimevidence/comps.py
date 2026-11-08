from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .model import ym_label
from .records import CountyData, as_int, as_str


@dataclass
class CompParams:
    lookback_months: int = 24
    size_band: float = 0.25
    age_band: int = 15
    land_band: float = 0.50
    min_comps: int = 3
    max_comps: int = 6
    outlier_iqr: float = 3.0
    gross_adjustment_flag: float = 0.25
    net_adjustment_flag: float = 0.15
    cod_good: float = 0.15
    cod_max: float = 0.25

    def basis(self) -> dict:
        return {
            "lookback_months": "Sales in the 24 months before the 1 January valuation date; older sales need more time adjustment and are excluded.",
            "size_band": "Living area within 25% of the subject (log ratio), so the size adjustment stays small.",
            "age_band": "Effective year built within 15 years; age is controlled by selection and is not adjusted.",
            "land_band": "Houses only: county land value within a factor of about 1.65 (log ratio 0.5), keeping waterfront and interior lots apart.",
            "min_comps": "At least three suitable sales are required before any indication of value is reported.",
            "outlier_iqr": "A qualified sale whose county-value-to-price ratio falls outside 3 interquartile ranges of the county's own ratios is set aside as potentially atypical.",
            "gross_adjustment_flag": "A comparable whose gross adjustments exceed 25% of its price is flagged for review (a common residential appraisal guideline, applied here as a screening heuristic, not a legal rule).",
            "net_adjustment_flag": "A comparable whose net adjustment exceeds 15% of its price is flagged for review (same guideline).",
            "cod_max": "If the adjusted indications vary by more than a 25% coefficient of dispersion, the comparables do not agree and the result is insufficient evidence.",
        }


TIER_LABEL = {1: "same peer group as the subject", 2: "same appraisal neighborhood", 3: "same market area"}


def _tiers(subject: pd.Series, pool: pd.DataFrame) -> pd.Series:
    tier = pd.Series(np.nan, index=pool.index)
    if "MKT_AR" in pool.columns and pd.notna(subject.get("MKT_AR")) and str(subject.get("MKT_AR")).strip():
        tier[pool.MKT_AR.astype("string") == str(subject.MKT_AR)] = 3
    if "NBRHD_ORIG" in pool.columns and pd.notna(subject.get("NBRHD_ORIG")):
        tier[pool.NBRHD_ORIG.astype("string") == str(subject.NBRHD_ORIG)] = 2
    tier[pool.NBRHD_CD.astype("string") == str(subject.NBRHD_CD)] = 1
    return tier


def _ratio_fences(cd: CountyData, uc: str) -> tuple[float, float]:
    g = cd.qualified[(cd.qualified.DOR_UC == uc) & (cd.qualified.ym < cd.valuation_ym)]
    r = g.JV / (g.SALE_PRC * g.tadj)
    if len(r) < 30:
        return (0.0, float("inf"))
    q1, q3 = r.quantile([0.25, 0.75])
    return (float(q1), float(q3))


def analyze(cd: CountyData, subject: pd.Series, p: CompParams | None = None) -> dict:
    p = p or CompParams()
    uc = subject.DOR_UC
    condo = uc == "004"
    vym = cd.valuation_ym
    level = cd.level.get(uc, 0.85)
    pool = cd.qualified[(cd.qualified.DOR_UC == uc) & (cd.qualified.PARCEL_ID != subject.PARCEL_ID)].copy()
    pool["tier"] = _tiers(subject, pool)
    pool = pool[pool.tier.notna()]
    pool = pool.sort_values("ym").groupby("PARCEL_ID").tail(1)
    q1, q3 = _ratio_fences(cd, uc)
    iqr = q3 - q1
    lo_f, hi_f = q1 - p.outlier_iqr * iqr, q3 + p.outlier_iqr * iqr
    considered, subsequent = [], []
    for x in pool.itertuples(index=False):
        reasons = []
        if x.ym >= vym:
            subsequent.append(x)
            continue
        if x.ym < vym - p.lookback_months:
            reasons.append(("STALE", f"sold {ym_label(x.ym)}, more than {p.lookback_months} months before the valuation date"))
        size_gap = abs(np.log(x.sqft / subject.sqft))
        if size_gap > p.size_band:
            reasons.append(("SIZE", f"{x.sqft:,.0f} sq ft vs subject {subject.sqft:,.0f} ({np.exp(size_gap) - 1:.0%} apart)"))
        if pd.notna(x.eff) and pd.notna(subject.eff) and abs(x.eff - subject.eff) > p.age_band:
            reasons.append(("AGE", f"effective year {x.eff:.0f} vs subject {subject.eff:.0f}"))
        if not condo:
            land_gap = abs(np.log(max(x.land, 1) / max(subject.land, 1)))
            if land_gap > p.land_band:
                reasons.append(("LAND", f"county land value ${x.land:,.0f} vs subject ${subject.land:,.0f}"))
        ratio = x.JV / (x.SALE_PRC * x.tadj)
        if not (lo_f <= ratio <= hi_f):
            reasons.append(("ATYPICAL", f"county value is {ratio:.2f}x the time-adjusted price, outside the county's normal range ({lo_f:.2f}-{hi_f:.2f}); the sale may not reflect market terms"))
        nb_s = as_int(getattr(subject, "NO_BULDNG", None)) or 1
        nb_c = as_int(getattr(x, "NO_BULDNG", None)) or 1
        if nb_s != nb_c:
            reasons.append(("BUILDINGS", f"{nb_c} building(s) vs subject {nb_s}"))
        similarity = (size_gap / p.size_band + (abs(x.eff - subject.eff) / p.age_band if pd.notna(x.eff) and pd.notna(subject.eff) else 1.0)
                      + (0 if condo else abs(np.log(max(x.land, 1) / max(subject.land, 1))) / p.land_band)
                      + (vym - x.ym) / p.lookback_months + (x.tier - 1) * 0.75)
        considered.append({"row": x, "reasons": reasons, "score": float(similarity)})
    usable = sorted([c for c in considered if not c["reasons"]], key=lambda c: (c["row"].tier, c["score"]))
    selected = usable[:p.max_comps]
    tier_used = int(max((c["row"].tier for c in selected), default=0)) or None
    excluded = [c for c in considered if c["reasons"]]
    excluded.sort(key=lambda c: c["score"])

    def comp_record(c, include):
        x = c["row"]
        rec = {"parcel_id": x.PARCEL_ID, "address": as_str(x.PHY_ADDR1) or "", "sale_month": ym_label(x.ym),
               "sale_price": as_int(x.SALE_PRC), "qualification_code": as_str(x.QUAL_CD),
               "record": {"or_book": as_str(getattr(x, "OR_BOOK", None)), "or_page": as_str(getattr(x, "OR_PAGE", None)),
                          "clerk_no": as_str(getattr(x, "CLERK_NO", None)), "sale_id": as_str(getattr(x, "SALE_ID_CD", None))},
               "sqft": as_int(x.sqft), "effective_year_built": as_int(x.eff), "actual_year_built": as_int(getattr(x, "ACT_YR_BLT", None)),
               "county_land_value": as_int(x.land), "county_special_features_value": as_int(getattr(x, "SPEC_FEAT_VAL", 0) or 0),
               "county_just_value": as_int(x.JV), "location": TIER_LABEL[int(x.tier)], "time_factor": round(float(x.tadj), 4),
               "similarity_score": round(c["score"], 3)}
        if not include:
            rec["excluded_because"] = [{"code": k, "detail": d} for k, d in c["reasons"]]
        return rec

    result = {"params": asdict(p), "param_basis": p.basis(), "level": level, "level_source": cd.level_source.get(uc),
              "time_method": cd.time_method.get(uc), "valuation_date": f"{cd.tax_year}-01-01",
              "candidates_considered": len(considered), "candidates_usable": len(usable),
              "location_tier_used": TIER_LABEL.get(tier_used) if tier_used else None,
              "exclusion_counts": pd.Series([k for c in excluded for k, _ in c["reasons"]]).value_counts().to_dict() if excluded else {},
              "excluded_nearest": [comp_record(c, False) for c in excluded[:12]],
              "subsequent_sales": [{"parcel_id": x.PARCEL_ID, "address": as_str(x.PHY_ADDR1) or "", "sale_month": ym_label(x.ym),
                                    "sale_price": as_int(x.SALE_PRC), "sqft": as_int(x.sqft), "location": TIER_LABEL[int(x.tier)]}
                                   for x in sorted(subsequent, key=lambda r: (r.tier, abs(np.log(r.sqft / subject.sqft))))[:6]]}
    if len(selected) < p.min_comps:
        result.update({"selected": [comp_record(c, True) for c in selected], "indication": None,
                       "reliability": "insufficient", "reliability_reason": f"only {len(selected)} suitable sale(s); at least {p.min_comps} are required"})
        return result

    feat_s = float(getattr(subject, "SPEC_FEAT_VAL", 0) or 0)
    land_s = 0.0 if condo else float(subject.land)
    building = []
    for c in selected:
        x = c["row"]
        price_t = float(x.SALE_PRC) * float(x.tadj)
        land_m = 0.0 if condo else float(x.land) / level
        feat_m = float(getattr(x, "SPEC_FEAT_VAL", 0) or 0) / level
        building.append((price_t - land_m - feat_m) / float(x.sqft))
    building_rate = float(np.median(building))
    rows = []
    for c in selected:
        x = c["row"]
        price = float(x.SALE_PRC)
        a_time = price * (float(x.tadj) - 1.0)
        a_land = 0.0 if condo else (land_s - float(x.land)) / level
        a_feat = (feat_s - float(getattr(x, "SPEC_FEAT_VAL", 0) or 0)) / level
        a_size = (float(subject.sqft) - float(x.sqft)) * building_rate
        adj = {"time": a_time, "land": a_land, "special_features": a_feat, "living_area": a_size}
        net = sum(adj.values())
        gross = sum(abs(v) for v in adj.values())
        indicated = price + net
        flags = []
        if gross / price > p.gross_adjustment_flag:
            flags.append(f"gross adjustments {gross / price:.0%} of price")
        if abs(net) / price > p.net_adjustment_flag:
            flags.append(f"net adjustment {net / price:+.0%} of price")
        rec = comp_record(c, True)
        rec.update({"adjustments": {k: int(round(v)) for k, v in adj.items()}, "net_adjustment": int(round(net)),
                    "gross_adjustment_pct": round(gross / price, 4), "net_adjustment_pct": round(net / price, 4),
                    "indicated_value": int(round(indicated)), "flags": flags})
        rows.append(rec)
    ind = np.array([r["indicated_value"] for r in rows], dtype=float)
    med = float(np.median(ind))
    cod = float(np.mean(np.abs(ind - med)) / med)
    reliability = "good" if cod <= p.cod_good else ("acceptable" if cod <= p.cod_max else "insufficient")
    clean = np.array([r["indicated_value"] for r in rows if not r["flags"]], dtype=float)
    sensitivity = None
    if len(clean) and len(clean) < len(rows):
        alt = float(np.median(clean))
        shift = (alt - med) / med
        sensitivity = {"without_flagged_comparables": int(round(alt)), "comparables_used": int(len(clean)), "shift": round(shift, 4),
                       "detail": (f"without the {len(rows) - len(clean)} flagged sale(s) the median indication would be ${alt:,.0f} "
                                  f"({shift:+.1%}) on {len(clean)} sale(s)")}
        if len(clean) < p.min_comps:
            sensitivity["detail"] += "; fewer than three unflagged sales remain, so the result leans on heavily adjusted sales"
    downgrade = sensitivity is not None and (abs(sensitivity["shift"]) > 0.10 or sensitivity["comparables_used"] < p.min_comps)
    if downgrade and reliability == "good":
        reliability = "acceptable"
    result.update({
        "sensitivity": sensitivity,
        "selected": rows,
        "building_rate_per_sqft": round(building_rate, 2),
        "building_rate_basis": "median, over the selected sales, of (time-adjusted price - county land value - county special-features value, both converted to market terms by dividing by the county level) / living area",
        "adjustment_basis": {
            "time": "sale price x (county time factor - 1); the factor moves each sale to 1 January using the county's own monthly median price per sq ft",
            "land": "(subject county land value - comparable county land value) / county level; condos are not land-adjusted",
            "special_features": "(subject county special-features value - comparable's) / county level",
            "living_area": "(subject sq ft - comparable sq ft) x building rate per sq ft",
            "not_adjusted": "age (controlled by selection), condition, quality and view: no reliable public data; disclosed as limitations",
        },
        "indication": {"market_value": int(round(med)), "low": int(ind.min()), "high": int(ind.max()),
                       "method": "median of adjusted comparable indications", "comparables": len(rows)},
        "dispersion_cod": round(cod, 4),
        "reliability": reliability,
        "reliability_reason": f"coefficient of dispersion {cod:.1%} across {len(rows)} adjusted sales"
                              + ("; downgraded because the result depends on heavily adjusted sales" if downgrade else ""),
    })
    return result


def subject_sales(cd: CountyData, subject: pd.Series, p: CompParams | None = None) -> list[dict]:
    p = p or CompParams()
    s = cd.all_sales[cd.all_sales.PARCEL_ID == subject.PARCEL_ID].sort_values("ym")
    out = []
    qual = set(cd.qualified[cd.qualified.PARCEL_ID == subject.PARCEL_ID].ym.astype(int))
    for x in s.itertuples(index=False):
        tf = cd.time_index.get(subject.DOR_UC, {}).get(int(x.ym), None)
        q = int(x.ym) in qual
        out.append({"sale_month": ym_label(x.ym), "sale_price": as_int(x.SALE_PRC), "qualification_code": as_str(x.QUAL_CD),
                    "qualified": q, "before_valuation_date": int(x.ym) < cd.valuation_ym,
                    "time_adjusted_price": as_int(float(x.SALE_PRC) * tf) if (q and tf) else None,
                    "record": {"or_book": as_str(getattr(x, "OR_BOOK", None)), "or_page": as_str(getattr(x, "OR_PAGE", None)),
                               "clerk_no": as_str(getattr(x, "CLERK_NO", None))}})
    return out


def assessment_peers(cd: CountyData, subject: pd.Series, size_band: float = 0.20, k: int = 8) -> dict:
    g = cd.homes[(cd.homes.DOR_UC == subject.DOR_UC) & (cd.homes.NBRHD_CD == subject.NBRHD_CD) & (cd.homes.PARCEL_ID != subject.PARCEL_ID)]
    g = g[np.abs(np.log(g.sqft / subject.sqft)) <= size_band]
    if g.empty:
        return {"peers": 0, "median_value_per_sqft": None, "subject_value_per_sqft": round(float(subject.ppsf), 2), "ratio": None, "examples": []}
    med = float(g.ppsf.median())
    near = g.assign(d=np.abs(np.log(g.sqft / subject.sqft))).sort_values("d").head(k)
    return {"peers": int(len(g)), "median_value_per_sqft": round(med, 2), "subject_value_per_sqft": round(float(subject.ppsf), 2),
            "ratio": round(float(subject.ppsf) / med, 4) if med else None,
            "basis": "county just value per sq ft of homes in the same peer group within 20% of the subject's living area",
            "examples": [{"parcel_id": r.PARCEL_ID, "address": as_str(r.PHY_ADDR1) or "", "sqft": as_int(r.sqft),
                          "county_just_value": as_int(r.JV), "value_per_sqft": round(float(r.ppsf), 2)} for r in near.itertuples()]}
