"""The Find -> Qualify handoff contract (schema version 2).

One candidate = one property that might be over-assessed, with everything the next desks need:
who owns it (Sign up), how much is at stake and how strong the signals are (Qualify), which
neighbors and sales back it up (Evidence), and when the filing window closes (File).
"""
from __future__ import annotations

SCHEMA_VERSION = 2

CANDIDATE_JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "FindCandidate",
    "type": "object",
    "required": ["schema_version", "case_id", "desk", "status", "jurisdiction", "property", "values",
                 "signals", "estimate", "confidence", "explanation", "assumptions", "needs_verification",
                 "tier", "owner", "portfolio", "outreach", "filing_window", "source"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "status": {"enum": ["candidate"], "description": "Find only ever emits 'candidate'. Qualify owns every status after this."},
        "confidence": {
            "type": "object",
            "description": "How well-evidenced the case is, independent of how large the estimate is. Ranking uses this ahead of the dollar figure so a big speculative number cannot outrank a smaller well-supported one.",
            "properties": {"evidence_quality": {"type": "number", "description": "0..1"},
                           "evidence_label": {"enum": ["thin", "moderate", "strong"]},
                           "components": {"type": "object"}},
        },
        "explanation": {"type": "string", "description": "Plain-language account of why this property was flagged, which data supports it, and how the estimate was derived."},
        "assumptions": {"type": "array", "items": {"type": "string"}, "description": "Every assumption baked into the estimate. Read these before quoting a savings figure to anyone."},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "needs_verification": {"type": "array", "items": {"type": "string"}, "description": "Checks Qualify or Evidence must perform. Find cannot do these from public roll data."},
        "flags": {
            "type": "object",
            "properties": {"identical_assessment_cluster": {"type": ["integer", "null"], "description": "N>1 means N separate parcels share this owner, peer group and an identical county value. A real pattern (e.g. a tract of identical rental houses), NOT duplicate records."}},
        },
        "portfolio": {
            "type": "object",
            "description": "Owner grouping. Parcel-level records are always preserved; this is an overlay so Qualify can act on an owner once instead of N times.",
            "properties": {
                "portfolio_id": {"type": "string"}, "owner_name": {"type": "string"},
                "owner_name_as_recorded": {"type": "string", "description": "Exactly as the roll spells it; never overwritten by normalisation."},
                "match_basis": {"type": "string"}, "match_confidence": {"type": "string"},
                "match_caveat": {"type": "string"}, "scope": {"enum": ["county", "state"]},
                "parcels_in_county": {"type": "integer", "description": "All parcels this owner holds in the county."},
                "flagged_parcels": {"type": "integer", "description": "The subset Find flagged. Always <= parcels_in_county."},
                "savings_in_run": {"type": "number", "description": "Sum over flagged outreach-tier parcels only. Each parcel contributes once."},
                "counties": {"type": "array", "items": {"type": "string"}},
            },
        },
        "outreach": {
            "type": "object",
            "description": "Outreach eligibility is deliberately separate from candidate quality and from contact verification. Find always emits eligible=false.",
            "properties": {"eligible": {"const": False}, "reason": {"type": "string"},
                           "blocked_by": {"type": "array", "items": {"type": "string"}},
                           "contact_channels_available": {"type": "array", "items": {"type": "string"}},
                           "contact_provenance": {"type": "string"},
                           "suppression_checked": {"type": "boolean"}},
        },
        "case_id": {"type": "string", "description": "Stable id: <STATE>-<county code>-<tax year>-<parcel id>. Same property and year -> same id."},
        "desk": {"const": "property_tax"},
        "jurisdiction": {
            "type": "object",
            "required": ["state", "county", "county_code", "tax_year", "roll_stage"],
            "properties": {
                "state": {"type": "string"}, "county": {"type": "string"}, "county_code": {"type": "string"},
                "tax_year": {"type": "integer"}, "roll_stage": {"enum": ["preliminary", "final"]},
                "county_check": {"type": "object", "description": "Self-check on sales after the valuation date. status: validated | weak (cards held) | untested."},
            },
        },
        "property": {
            "type": "object",
            "required": ["parcel_id", "address", "use"],
            "properties": {
                "parcel_id": {"type": "string"}, "alt_key": {"type": ["string", "null"]},
                "address": {"type": "string"}, "unit": {"type": ["string", "null"]},
                "unit_source": {"type": ["string", "null"], "description": "roll | mailing_address | legal_description; null = unknown (look up by parcel id)"},
                "city": {"type": ["string", "null"]}, "zip": {"type": ["string", "null"]},
                "use": {"enum": ["single_family", "condo"]},
                "sqft": {"type": ["number", "null"], "description": "County's TOT_LVG_AREA: effective area, which may weight garages and porches in. Not a listing's heated sq ft; do not quote it to owners as living area."},
                "effective_year_built": {"type": ["number", "null"]}, "neighborhood": {"type": ["string", "null"]},
                "homestead": {"type": "boolean"},
            },
        },
        "values": {
            "type": "object",
            "description": "County's numbers for this tax year, in dollars.",
            "properties": {
                "just_value": {"type": "number"}, "assessed_value": {"type": ["number", "null"]},
                "taxable_value": {"type": ["number", "null"]}, "land_value": {"type": ["number", "null"]},
            },
        },
        "signals": {
            "type": "object",
            "description": "Ratios > 1 mean the county value looks high. null = not enough data.",
            "properties": {
                "neighbor_ratio": {"type": ["number", "null"]}, "neighbor_count": {"type": "integer"},
                "peer_basis": {"enum": ["neighborhood", "market_area", "building", "section", "township"], "description": "building = condo compared within its own building; section/township = an oversized neighborhood split by survey section (1 sq mi) or township (36 sq mi); market_area = county left the neighborhood code blank (coarser)"},
                "own_sale_contradicts": {"type": "boolean", "description": "the home's own sale (before or after Jan 1) supports the county value; tier is review"},
                "later_sale": {"type": ["object", "null"], "description": "arm's-length sale after Jan 1: price, month, ratio"},
                "peer_group": {"type": ["string", "null"], "description": "internal key of the group the home was compared within"},
                "level_factor_now": {"type": ["number", "null"], "description": "moves a value from today's market back to Jan 1 (used on AVM estimates)"},
                "sales_ratio": {"type": ["number", "null"]}, "comp_count": {"type": "integer"},
                "own_sale_ratio": {"type": ["number", "null"]},
                "avm_ratio": {"type": ["number", "null"]}, "avm": {"type": ["object", "null"]},
                "county_level": {"type": "number", "description": "County's typical value / sale price for this use."},
            },
        },
        "estimate": {
            "type": "object",
            "properties": {
                "defensible_value": {"type": ["number", "null"]}, "value_cut": {"type": "number"},
                "taxable_cut": {"type": "number", "description": "cut in non-school taxable value"},
                "taxable_cut_school": {"type": "number", "description": "cut in school taxable value (school levies use the school assessed value, which has no 10% non-homestead cap)"},
                "annual_savings": {"type": "number", "description": "school cut x school millage + non-school cut x other millage; never more than the taxable value left after exemptions"},
                "millage": {"type": "number"}, "millage_source": {"type": "string"},
                "annual_savings_range": {"type": "array", "description": "[low, high] from the plausible Florida millage band. The point estimate is not a promise."},
                "millage_band": {"type": "array"}, "is_estimate": {"const": True},
            },
        },
        "tier": {"enum": ["strong", "possible", "review", "cap_absorbs", "new_build"],
                 "description": "strong = both signals, clean data, savings >= threshold. Only strong/possible are meant for outreach."},
        "avm_check": {"enum": ["confirmed", "inconclusive", "disputed", "not_checked", "no_estimate", "no_unit"],
                      "description": "Zillow/Redfin/Naive estimate vs county value. disputed moves strong/possible to review."},
        "owner": {
            "type": "object",
            "description": "Owner of record from the public roll. No phone or email: cold contact is by mail.",
            "properties": {
                "owner_id": {"type": "string"}, "name": {"type": "string"}, "type": {"type": "string"},
                "mailing_address": {"type": "object"}, "absentee": {"type": "boolean"},
                "out_of_state": {"type": "boolean"}, "parcels_in_county": {"type": "integer"},
                "may_have_changed": {"type": "boolean", "description": "a deed was recorded after Jan 1; mail may need to go to a new owner"},
                "deed_since_roll": {"type": ["string", "null"]},
                "flagged_parcels_in_run": {"type": "integer"}, "portfolio_savings_in_run": {"type": "number"},
            },
        },
        "evidence": {
            "type": "object",
            "properties": {"neighbors": {"type": "array"}, "sales": {"type": "array"}},
        },
        "filing_window": {
            "type": "object",
            "properties": {"opens": {"type": "string"}, "closes": {"type": "string"},
                           "status": {"enum": ["upcoming", "open", "closed"]}, "basis": {"type": "string"},
                           "verified": {"type": "boolean", "description": "False until the deadline has been read from that county's own VAB page and recorded. A statewide estimate can be wrong by weeks."},
                           "source": {"type": ["string", "null"]}},
        },
        "source": {"type": "object", "properties": {"roll_file": {"type": "string"}, "sales_file": {"type": "string"},
                                                    "run_id": {"type": "string"}, "found_at": {"type": "string"}}},
    },
}
