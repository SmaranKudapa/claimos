"""Florida property-tax desk: data sources (DOR portal, 67 counties), detection rule, filing window."""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd

from ....config import Settings
from ....engine.ingest import HttpCache
from ....engine.normalize import norm_zip
from ....engine.people import attach_owners, portfolio_rollup
from ....schema import SCHEMA_VERSION
from ..screen import USES, evidence, screen
from .source import RollFile, latest_pairs, list_roll_files, load_pair

STATE = "FL"
OUTREACH_TIERS = ("strong", "possible")
EXPORT_TIERS = ("strong", "possible", "review", "cap_absorbs", "new_build")

# Find assumes an all-in rate when no per-county millage is configured. Florida's actual combined
# rate varies by county AND by taxing district within a county. This band is the plausible spread,
# used only to express uncertainty — it is NOT a verified rate for any parcel.
MILLAGE_BAND = (0.011, 0.022)


# Petition deadlines are 25 days after EACH COUNTY mails its TRIM notice (Fla. Stat. 194.011(3)),
# and counties mail on their own dates. Verified 2026-11-07 from each county's own publication:
# a 7-day spread for the same tax year, so a statewide constant is wrong by up to a week.
VERIFIED_DEADLINES = {
    ("volusia", 2026): ("2026-09-11", "https://www.volusia.org/file/7903/ADA_Petition_Deadline_2026_-_publication_date_08042026.pdf"),
    ("dade", 2026): ("2026-09-18", "https://www.miamidadeclerk.gov/clerk/value-adjustment-board.page"),
    ("miami-dade", 2026): ("2026-09-18", "https://www.miamidadeclerk.gov/clerk/value-adjustment-board.page"),
    ("broward", 2026): ("2026-09-18", "https://bcpa.net/value.asp"),
}
DEADLINES_CHECKED = "2026-11-07"


def filing_window(tax_year: int, today: dt.date | None = None, county: str | None = None) -> dict:
    """When a VAB petition for this county and year is due.

    Fla. Stat. 194.011(3): valuation petitions are due on or before the 25th day after the county
    mails its TRIM notice. Counties mail on different dates, so this is per county, not statewide.
    Where a county's own published deadline has been read and recorded, `verified` is True and
    `source` carries the URL. Otherwise the dates are a statewide ESTIMATE and `verified` is False.

    Note also: exemption/classification denials run 30 days from the denial notice, not 25 from
    TRIM, and Rule 12D-9.015(14) lets a board accept a late petition for good cause. Neither is
    modelled here; both belong to the File desk.
    """
    today = today or dt.date.today()
    key = ((county or "").strip().lower(), tax_year)
    verified = VERIFIED_DEADLINES.get(key)
    if verified:
        closes = dt.date.fromisoformat(verified[0])
        opens = closes - dt.timedelta(days=25)
        basis = (f"verified: {county} published a {closes.isoformat()} deadline for tax year {tax_year} "
                 f"(checked {DEADLINES_CHECKED}). The date printed on the owner's own TRIM notice remains "
                 "authoritative for that parcel.")
        src = verified[1]
    else:
        opens = dt.date(tax_year, 8, 15)
        closes = opens + dt.timedelta(days=25)
        basis = ("UNVERIFIED estimate: 25 days after an assumed mid-August TRIM mailing, applied statewide. "
                 "Counties mail on their own dates and a 7-day spread is confirmed for 2026, so this can be "
                 "wrong by weeks. Read the county VAB's posted deadline before relying on it.")
        src = None
    status = "upcoming" if today < opens else ("open" if today <= closes else "closed")
    return {"opens": opens.isoformat(), "closes": closes.isoformat(), "status": status,
            "verified": bool(verified), "source": src, "checked": DEADLINES_CHECKED if verified else None,
            "statute": "Fla. Stat. 194.011(3) — 25 days after the county mails its TRIM notice",
            "basis": basis}


def _f(v):
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _s(v) -> str | None:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    v = str(v).strip()
    return v or None


def _evidence_quality(x, county_check: dict) -> dict:
    """0..1 score for how well-supported a case is, independent of how big the estimate is.

    Ranking uses this ahead of the dollar estimate so a large speculative number cannot outrank a
    smaller, better-evidenced one.
    """
    peer_n, comp_n = int(getattr(x, "peer_n", 0) or 0), int(getattr(x, "comp_n", 0) or 0)
    status = (county_check or {}).get("status")
    comp = {
        "peer_support": round(min(peer_n / 40.0, 1.0) * 0.25, 4),
        "comp_support": round(min(comp_n / 15.0, 1.0) * 0.25, 4),
        "county_self_check": {"validated": 0.30, "untested": 0.10, "weak": 0.0}.get(status, 0.05),
        "no_contradicting_sale": 0.0 if bool(getattr(x, "own_sale_contradicts", False)) else 0.10,
        "owner_unchanged": 0.0 if _f(getattr(x, "deed_since_roll_ym", None)) else 0.10,
    }
    score = round(sum(comp.values()), 4)
    label = "strong" if score >= 0.75 else ("moderate" if score >= 0.5 else "thin")
    return {"evidence_quality": score, "evidence_label": label, "components": comp}


def _explain(x, savings: float, county_check: dict) -> str:
    nr, sr = _f(x.neighbor_ratio), _f(x.sales_ratio)
    return (
        f"Flagged because the county's value per sq ft is {((nr or 1) - 1) * 100:.0f}% above "
        f"{int(x.peer_n)} similar {('condos in the same building' if x.DOR_UC == '004' else 'homes in the same appraisal neighborhood')} "
        f"(ratio {nr or 0:.2f}, threshold 1.15), AND the county's value is {((sr or 1) - 1) * 100:.0f}% above what "
        f"{int(x.comp_n)} comparable sales imply once adjusted to Jan 1 and compared at the county's own "
        f"value-to-price level of {_f(x.level) or 0:.2f} (ratio {sr or 0:.2f}, threshold 1.10). "
        f"A home must fail both tests. The estimate moves the value to ${_f(x.defensible_value) or 0:,.0f}, "
        f"caps the cut at the assessed and taxable values, and applies an assumed millage to give "
        f"~${savings:,.0f}/yr. County self-check for this county: {(county_check or {}).get('status')}."
    )


def _verification(x, county_check: dict) -> list[str]:
    out = [
        "Confirm the parcel's actual millage for its taxing district — the savings here use an assumed rate, not a billed one.",
        "Confirm this county's VAB petition deadline from the county's own site; the filing window here is an unverified statewide estimate.",
        "Inspect condition and the county property record card. Public roll data cannot see damage, defects or unpermitted work.",
    ]
    if (county_check or {}).get("status") != "validated":
        out.append(f"County self-check is '{(county_check or {}).get('status')}' — the screen has not been shown to work here. Treat the estimate as unproven.")
    if int(getattr(x, "peer_n", 0) or 0) < 15:
        out.append(f"Thin peer group ({int(x.peer_n)} homes): check the peers are genuinely comparable.")
    if int(getattr(x, "comp_n", 0) or 0) < 5:
        out.append(f"Few comparable sales ({int(x.comp_n)}): the sales ratio rests on a small sample.")
    if _f(getattr(x, "deed_since_roll_ym", None)):
        out.append("A deed was recorded after Jan 1 — confirm the current owner before any contact.")
    if bool(getattr(x, "own_sale_contradicts", False)):
        out.append("This property's own sale supports the county value. Needs a person to look before proceeding.")
    return out


def _warnings(x, cluster: int | None) -> list[str]:
    w = []
    if _s(getattr(x, "unit_source", None)) and x.unit_source != "roll":
        w.append(f"Unit number was inferred from the {str(x.unit_source).replace('_', ' ')}, not stated on the roll.")
    if _f(getattr(x, "deed_since_roll_ym", None)):
        w.append("Owner of record may have changed since the roll was published.")
    if cluster and cluster > 1:
        w.append(f"{cluster} parcels share this owner, peer group and an identical county value — separate properties assessed identically, not duplicates.")
    if bool(getattr(x, "homestead", False)):
        w.append("Homesteaded: the Save Our Homes cap may absorb part or all of a value reduction.")
    return w


def build_payloads(r: pd.DataFrame, ev: dict, pair: dict[str, RollFile], run_id: str,
                   today: dt.date | None = None, county_check: dict | None = None,
                   level_source: dict | None = None) -> list[dict]:
    nal = pair["NAL"]
    county_check = county_check or {"status": "untested"}
    window = filing_window(nal.year, today, county=nal.county)
    found_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    retrieved = {k: getattr(pair[k], "modified", None) for k in ("NAL", "SDF")}
    out = []
    for x in r.itertuples(index=False):
        own_ym = _f(x.own_sale_ym)
        sav = round(_f(x.est_savings) or 0.0)
        lo, hi = (round(sav * MILLAGE_BAND[0] / (_f(x.millage) or 0.015)),
                  round(sav * MILLAGE_BAND[1] / (_f(x.millage) or 0.015)))
        cluster = int(getattr(x, "identical_cluster", 0) or 0) or None
        conf = _evidence_quality(x, county_check)
        out.append({
            "schema_version": SCHEMA_VERSION,
            "case_id": f"{STATE}-{nal.county_no}-{nal.year}-{x.PARCEL_ID}",
            "desk": "property_tax",
            "status": "candidate",
            "jurisdiction": {"state": STATE, "county": nal.county, "county_code": nal.county_no,
                             "tax_year": nal.year, "roll_stage": nal.stage, "county_check": county_check},
            "property": {"parcel_id": x.PARCEL_ID, "alt_key": _s(x.ALT_KEY), "address": _s(x.situs_street) or _s(x.PHY_ADDR1) or "",
                         "unit": _s(x.unit), "unit_source": _s(x.unit_source), "city": _s(x.PHY_CITY), "zip": norm_zip(x.PHY_ZIPCD) or None,
                         "use": USES[x.DOR_UC], "sqft": _f(x.sqft), "effective_year_built": _f(x.eff),
                         "neighborhood": _s(x.NBRHD_ORIG), "homestead": bool(x.homestead)},
            "values": {"just_value": _f(x.JV), "assessed_value": _f(x.AV_NSD), "taxable_value": _f(x.TV_NSD),
                       "land_value": _f(x.LND_VAL)},
            "signals": {"neighbor_ratio": _f(x.neighbor_ratio), "neighbor_count": int(x.peer_n),
                        "sales_ratio": _f(x.sales_ratio), "comp_count": int(x.comp_n),
                        "own_sale_ratio": _f(x.own_sale_ratio), "peer_basis": x.peer_basis,
                        "own_sale_contradicts": bool(x.own_sale_contradicts),
                        "later_sale": ({"price": _f(x.later_sale_price), "ratio": _f(x.later_sale_ratio),
                                        "month": f"{int(x.later_sale_ym)//12}-{int(x.later_sale_ym)%12+1:02d}"}
                                       if _f(x.later_sale_ym) else None),
                        "peer_group": _s(x.NBRHD_CD), "level_factor_now": _f(x.level_factor_now),
                        "own_sale": ({"price": _f(x.own_sale_price),
                                      "month": f"{int(own_ym)//12}-{int(own_ym)%12+1:02d}"} if own_ym else None),
                        "avm_ratio": None, "avm": None, "county_level": _f(x.level),
                        "county_level_source": (level_source or {}).get(x.DOR_UC)},
            "estimate": {"defensible_value": _f(x.defensible_value), "value_cut": _f(x.value_cut) or 0.0,
                         "taxable_cut": _f(x.taxable_cut) or 0.0, "taxable_cut_school": _f(x.taxable_cut_school) or 0.0,
                         "annual_savings": sav, "annual_savings_range": [lo, hi],
                         "millage": _f(x.millage), "millage_band": list(MILLAGE_BAND),
                         "is_estimate": True,
                         "millage_source": ("ASSUMED, not billed: 5.5 mills school (on school assessed value) + 9.5 other "
                                            "(on non-school assessed value). Actual rates vary by county and district.")},
            "confidence": conf,
            "explanation": _explain(x, sav, county_check),
            "assumptions": [
                "Millage is assumed, not read from the parcel's tax bill.",
                "Non-ad-valorem charges (fire, solid waste, lighting) are excluded; they do not change with value.",
                f"County value-to-price level for this use: {_f(x.level) or 0:.2f} ({(level_source or {}).get(x.DOR_UC) or 'unknown source'}).",
                "Sales are time-adjusted to Jan 1 of the tax year using the county's own monthly/quarterly medians.",
                "Savings are capped at the assessed value and again at the taxable value left after exemptions.",
            ],
            "warnings": _warnings(x, cluster),
            "needs_verification": _verification(x, county_check),
            "flags": {"identical_assessment_cluster": cluster},
            "tier": x.tier,
            "avm_check": "not_checked",
            "owner": {"owner_id": x.owner_id, "name": _s(x.owner_name) or "", "type": x.owner_type,
                      "mailing_address": {"line1": _s(x.mail_addr1), "line2": _s(x.mail_addr2), "city": _s(x.mail_city),
                                          "state": _s(x.mail_state), "zip": _s(x.mail_zip)},
                      "absentee": bool(x.absentee), "out_of_state": bool(x.out_of_state),
                      "may_have_changed": bool(_f(x.deed_since_roll_ym)),
                      "deed_since_roll": (f"{int(x.deed_since_roll_ym)//12}-{int(x.deed_since_roll_ym)%12+1:02d}"
                                          if _f(x.deed_since_roll_ym) else None),
                      "parcels_in_county": int(x.parcels_in_county),
                      "flagged_parcels_in_run": int(x.flagged_parcels_in_run),
                      "portfolio_savings_in_run": round(float(x.portfolio_savings_in_run), 2)},
            "portfolio": {
                "portfolio_id": x.owner_id,
                "owner_name": _s(x.owner_name) or "",
                "owner_name_as_recorded": _s(x.owner_name) or "",
                "match_basis": "normalized owner name + normalized mailing street + mailing ZIP, within one county roll",
                "match_confidence": "exact_key",
                "match_caveat": ("Entities with different names or mailing addresses are NOT merged, so one real owner "
                                 "may appear as several portfolios. Cross-county grouping is not performed in a "
                                 "single-county run."),
                "scope": "county",
                "parcels_in_county": int(x.parcels_in_county),
                "flagged_parcels": int(x.flagged_parcels_in_run),
                "savings_in_run": round(float(x.portfolio_savings_in_run), 2),
                "counties": [nal.county],
            },
            "outreach": {
                "eligible": False,
                "reason": ("Find never authorises contact. Qualify decides, and contact details are not verified here."
                           + (" This owner is suppressed as potentially confidential under Fla. Stat. 119.071(4)(d)."
                              if bool(getattr(x, "owner_suppressed", False)) else "")),
                "blocked_by": (["qualify_not_run", "no_verified_contact"]
                               + ([] if window.get("verified") else ["filing_window_unverified"])
                               + (["confidential_owner_suppressed"] if bool(getattr(x, "owner_suppressed", False)) else [])),
                "owner_suppressed": bool(getattr(x, "owner_suppressed", False)),
                "owner_suppression_reason": _s(getattr(x, "owner_suppression_reason", "")) or None,
                "contact_channels_available": ["mailing_address_from_public_roll"],
                "contact_provenance": "Florida DOR county tax roll (NAL), owner of record and tax-bill mailing address",
                "suppression_checked": False,
            },
            "evidence": ev.get(x.PARCEL_ID, {"neighbors": [], "sales": []}),
            "filing_window": window,
            "source": {"roll_file": nal.url, "sales_file": pair["SDF"].url, "run_id": run_id, "found_at": found_at,
                       "roll_published": retrieved.get("NAL"), "sales_published": retrieved.get("SDF"),
                       "roll_stage": nal.stage, "data_vintage": f"{nal.year} {nal.stage} roll"},
        })
    return out


def run_county(settings: Settings, cache: HttpCache, pair: dict[str, RollFile], run_id: str,
               today: dt.date | None = None) -> tuple[list[dict], dict]:
    work = settings.cache_dir / "fl"
    work.mkdir(parents=True, exist_ok=True)
    nal, sdf, files_meta = load_pair(cache, pair, work)
    dup_parcels = int(nal.PARCEL_ID.duplicated().sum())
    if dup_parcels:
        nal = nal.drop_duplicates(subset=["PARCEL_ID"], keep="first")
    nal = attach_owners(nal, home_state=STATE, copy=False)
    # attach_owners has copied what it needs out of the raw owner/legal columns. On a big county
    # each text column costs ~28 MB, so holding both the source and the derived copy is pure waste.
    nal.drop(columns=[c for c in ("S_LEGAL", "OWN_NAME", "OWN_ADDR1", "OWN_ADDR2", "OWN_CITY",
                                  "OWN_ZIPCD", "OWN_STATE", "PHY_ADDR2") if c in nal.columns],
             inplace=True)
    r, aux = screen(nal, sdf, roll_year=pair["NAL"].year, p=settings.screen)
    shots = settings.data_dir / "screens"
    shots.mkdir(parents=True, exist_ok=True)
    r.assign(scored=r.peer_ppsf.notna() & r.comp_ppsf.notna())[["PARCEL_ID", "tier", "scored", "est_savings"]].to_parquet(
        shots / f"{STATE}_{pair['NAL'].county_no}_{pair['NAL'].year}.parquet", index=False)
    flagged = r[r.tier.isin(EXPORT_TIERS)].copy()
    flagged = portfolio_rollup(flagged.assign(_sav=flagged.est_savings.where(flagged.tier.isin(OUTREACH_TIERS), 0.0)),
                               savings_col="_sav")
    # Separate properties that one owner holds in one peer group at an identical county value are a
    # real pattern (a tract of identical rental houses), not duplicates. Label them so Qualify can
    # tell the difference instead of guessing.
    ckey = flagged.owner_id.astype(str) + "|" + flagged.NBRHD_CD.astype(str) + "|" + flagged.JV.astype(str)
    flagged["identical_cluster"] = ckey.map(ckey.value_counts()).fillna(0).astype(int)
    flagged.loc[flagged.identical_cluster < 2, "identical_cluster"] = 0
    ev = evidence(r, aux["comps"], flagged, settings.screen)
    payloads = build_payloads(flagged, ev, pair, run_id, today, county_check=aux["stats"]["holdout"],
                              level_source=aux["stats"].get("level_source"))
    stats = aux["stats"] | {"county": pair["NAL"].county, "county_code": pair["NAL"].county_no,
                            "tax_year": pair["NAL"].year, "roll_stage": pair["NAL"].stage,
                            "parcels_on_roll": int(len(nal)), "files": files_meta,
                            "duplicate_parcel_rows_dropped": dup_parcels,
                            "identical_assessment_clusters": int((flagged.identical_cluster > 1).sum()),
                            "owners_suppressed_confidential": int(flagged.owner_suppressed.sum()),
                            "outreach_owners": int(flagged[flagged.tier.isin(OUTREACH_TIERS)].owner_id.nunique())}
    return payloads, stats


def discover(cache: HttpCache, year: int | None = None) -> dict[str, dict[str, RollFile]]:
    return latest_pairs(list_roll_files(cache), year)
