from __future__ import annotations

from .records import as_int

ASSUMED_SCHOOL_MILLS = 5.5
ASSUMED_OTHER_MILLS = 9.5
MILLS_BAND = (11.0, 22.0)
MATERIAL_REDUCTION = 0.05
ROUND_TO = 100


def round_value(v: float) -> int:
    return int(ROUND_TO * round(v / ROUND_TO))


def conclude(subject, analysis: dict, peers: dict, own_sales: list[dict], find_payload: dict | None, level: float,
             cost_of_sale: dict | None = None) -> dict:
    jv = float(subject.JV)
    av_sd = float(subject.AV_SD) if subject.get("AV_SD") == subject.get("AV_SD") and subject.get("AV_SD") is not None else jv
    av_nsd = float(subject.AV_NSD) if subject.get("AV_NSD") == subject.get("AV_NSD") and subject.get("AV_NSD") is not None else jv
    tv_sd = float(subject.TV_SD) if subject.get("TV_SD") == subject.get("TV_SD") and subject.get("TV_SD") is not None else av_sd
    tv_nsd = float(subject.TV_NSD) if subject.get("TV_NSD") == subject.get("TV_NSD") and subject.get("TV_NSD") is not None else av_nsd
    homestead = bool(subject.get("homestead"))
    county = {"just_value": as_int(jv), "assessed_value_school": as_int(av_sd), "assessed_value_non_school": as_int(av_nsd),
              "taxable_value_school": as_int(tv_sd), "taxable_value_non_school": as_int(tv_nsd), "homestead": homestead,
              "save_our_homes_gap": as_int(jv - av_nsd) if homestead else 0}
    ind = analysis.get("indication")
    market = float(ind["market_value"]) if ind else None
    indications = {}
    if market is not None and cost_of_sale:
        rate = float(cost_of_sale["rate"])
        indications["market_less_cost_of_sale"] = {"value": as_int(market * (1 - rate)),
                                                    "formula": f"market value indication {as_int(market):,} x (1 - {rate:.0%} cost of sale)",
                                                    "basis": f"the county's DR-493 eighth-criterion adjustment of {rate:.0%} to recorded sale prices ({cost_of_sale['section']})",
                                                    "source": cost_of_sale["source"], "rule": cost_of_sale.get("rule")}
    if market is not None:
        indications["market_at_county_level"] = {"value": as_int(market * level),
                                                  "formula": f"market value indication {as_int(market):,} x county level {level:.4f}",
                                                  "basis": "puts the subject at the same ratio of just value to sale price that the county applies to its typical qualified sale"}
    if peers.get("peers", 0) >= 8 and peers.get("median_value_per_sqft"):
        indications["assessment_uniformity"] = {"value": as_int(peers["median_value_per_sqft"] * float(subject.sqft)),
                                                "formula": f"peer median ${peers['median_value_per_sqft']:,.2f}/sq ft x {float(subject.sqft):,.0f} sq ft",
                                                "basis": "the county's own value per sq ft for similar homes in the same peer group"}
    contradiction = None
    for s in own_sales:
        if s["qualified"] and s["before_valuation_date"] and s["time_adjusted_price"]:
            implied = s["time_adjusted_price"] * level
            if implied >= jv * (1 - MATERIAL_REDUCTION):
                contradiction = {"sale_month": s["sale_month"], "sale_price": s["sale_price"], "implied_just_value": as_int(implied),
                                 "detail": "the subject's own qualified sale before the valuation date supports the county's value"}
    proposed = None
    if indications:
        proposed = round_value(max(v["value"] for v in indications.values()))
    reduction = max(0.0, jv - proposed) if proposed is not None else None
    if analysis.get("reliability") == "insufficient" or ind is None:
        outcome, why = "insufficient_evidence", analysis.get("reliability_reason") or "no reliable market indication"
    elif contradiction:
        outcome, why = "contradicted", contradiction["detail"]
    elif reduction is None or reduction < MATERIAL_REDUCTION * jv:
        outcome, why = "does_not_support", (f"the supported value {proposed:,} is within {MATERIAL_REDUCTION:.0%} of the county's "
                                             f"{as_int(jv):,}, so the evidence does not support a material reduction")
    else:
        outcome, why = "supports_reduction", f"the supported value {proposed:,} is {reduction / jv:.1%} below the county's {as_int(jv):,}"
    out = {"method_version": "fl-value/1", "county_values": county, "market_value_indication": as_int(market) if market else None,
           "county_level": round(level, 4), "cost_of_sale": ({"rate": cost_of_sale["rate"], "source": cost_of_sale["source"],
                                                               "section": cost_of_sale["section"]} if cost_of_sale else None),
           "just_value_indications": indications,
           "proposed_just_value": proposed if outcome == "supports_reduction" else None,
           "proposed_rule": "the higher (more conservative) of the available just value indications, rounded to the nearest $100",
           "outcome": outcome, "outcome_reason": why, "contradiction": contradiction}
    if outcome != "supports_reduction":
        out["effects"] = None
        out["tax_estimate"] = None
    else:
        new_sd, new_nsd = min(av_sd, proposed), min(av_nsd, proposed)
        cut_sd, cut_nsd = av_sd - new_sd, av_nsd - new_nsd
        tcut_sd, tcut_nsd = min(cut_sd, max(tv_sd, 0)), min(cut_nsd, max(tv_nsd, 0))
        point = tcut_sd * ASSUMED_SCHOOL_MILLS / 1000 + tcut_nsd * ASSUMED_OTHER_MILLS / 1000
        total_mills = ASSUMED_SCHOOL_MILLS + ASSUMED_OTHER_MILLS
        out["effects"] = {"just_value_reduction": as_int(reduction), "assessed_reduction_school": as_int(cut_sd),
                          "assessed_reduction_non_school": as_int(cut_nsd), "taxable_reduction_school": as_int(tcut_sd),
                          "taxable_reduction_non_school": as_int(tcut_nsd),
                          "note": ("A lower just value changes the assessed value only where it falls below it, and the taxable "
                                   "value only after exemptions. " + ("This homestead's Save Our Homes cap keeps its assessed "
                                   "value below just value, so part or all of the reduction may not lower the tax bill." if homestead else ""))}
        out["tax_estimate"] = {"annual_savings": as_int(point),
                               "annual_savings_range": [as_int(point * MILLS_BAND[0] / total_mills), as_int(point * MILLS_BAND[1] / total_mills)],
                               "rate_basis": "assumed",
                               "rates": {"school_mills": ASSUMED_SCHOOL_MILLS, "other_mills": ASSUMED_OTHER_MILLS, "band_mills": list(MILLS_BAND)},
                               "formula": "school taxable reduction x school mills / 1000 + non-school taxable reduction x other mills / 1000",
                               "caveat": "Estimate on assumed millage, not the parcel's billed rates. Not a result: the VAB may not grant any reduction."}
    if find_payload:
        fe = find_payload.get("estimate") or {}
        fv = fe.get("defensible_value")
        out["versus_find"] = {"find_defensible_value": as_int(fv), "find_annual_savings": as_int(fe.get("annual_savings")),
                              "find_tier": find_payload.get("tier"), "evidence_proposed_value": out["proposed_just_value"],
                              "evidence_outcome": outcome}
        changed = outcome != "supports_reduction" or (fv and proposed and abs(proposed - float(fv)) > MATERIAL_REDUCTION * jv)
        out["versus_find"]["material_change"] = bool(changed)
        out["versus_find"]["route"] = "requalify" if changed else "none"
    return out
