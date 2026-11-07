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


def filing_window(tax_year: int, today: dt.date | None = None) -> dict:
    """Value adjustment board petitions are due 25 days after the TRIM notice is mailed; TRIM
    notices usually go out in mid-August (Florida DOR, PT-101). Each county posts its exact date."""
    today = today or dt.date.today()
    opens = dt.date(tax_year, 8, 15)
    closes = opens + dt.timedelta(days=25)
    status = "upcoming" if today < opens else ("open" if today <= closes else "closed")
    return {"opens": opens.isoformat(), "closes": closes.isoformat(), "status": status,
            "basis": "estimate: 25 days after TRIM mailing (mid-August); confirm the county VAB's posted deadline"}


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


def build_payloads(r: pd.DataFrame, ev: dict, pair: dict[str, RollFile], run_id: str,
                   today: dt.date | None = None, county_check: dict | None = None) -> list[dict]:
    nal = pair["NAL"]
    county_check = county_check or {"status": "untested"}
    window = filing_window(nal.year, today)
    found_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for x in r.itertuples(index=False):
        own_ym = _f(x.own_sale_ym)
        out.append({
            "schema_version": SCHEMA_VERSION,
            "case_id": f"{STATE}-{nal.county_no}-{nal.year}-{x.PARCEL_ID}",
            "desk": "property_tax",
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
                        "avm_ratio": None, "avm": None, "county_level": _f(x.level)},
            "estimate": {"defensible_value": _f(x.defensible_value), "value_cut": _f(x.value_cut) or 0.0,
                         "taxable_cut": _f(x.taxable_cut) or 0.0, "taxable_cut_school": _f(x.taxable_cut_school) or 0.0,
                         "annual_savings": round(_f(x.est_savings) or 0.0, 2), "millage": _f(x.millage),
                         "millage_source": "assumed: 5.5 mills school (on school assessed value) + 9.5 other (on non-school assessed value)"},
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
            "evidence": ev.get(x.PARCEL_ID, {"neighbors": [], "sales": []}),
            "filing_window": window,
            "source": {"roll_file": nal.url, "sales_file": pair["SDF"].url, "run_id": run_id, "found_at": found_at},
        })
    return out


def run_county(settings: Settings, cache: HttpCache, pair: dict[str, RollFile], run_id: str,
               today: dt.date | None = None) -> tuple[list[dict], dict]:
    work = settings.cache_dir / "fl"
    work.mkdir(parents=True, exist_ok=True)
    nal, sdf, files_meta = load_pair(cache, pair, work)
    nal = attach_owners(nal, home_state=STATE)
    r, aux = screen(nal, sdf, roll_year=pair["NAL"].year, p=settings.screen)
    shots = settings.data_dir / "screens"
    shots.mkdir(parents=True, exist_ok=True)
    r.assign(scored=r.peer_ppsf.notna() & r.comp_ppsf.notna())[["PARCEL_ID", "tier", "scored", "est_savings"]].to_parquet(
        shots / f"{STATE}_{pair['NAL'].county_no}_{pair['NAL'].year}.parquet", index=False)
    flagged = r[r.tier.isin(EXPORT_TIERS)].copy()
    flagged = portfolio_rollup(flagged.assign(_sav=flagged.est_savings.where(flagged.tier.isin(OUTREACH_TIERS), 0.0)),
                               savings_col="_sav")
    ev = evidence(r, aux["comps"], flagged, settings.screen)
    payloads = build_payloads(flagged, ev, pair, run_id, today, county_check=aux["stats"]["holdout"])
    stats = aux["stats"] | {"county": pair["NAL"].county, "county_code": pair["NAL"].county_no,
                            "tax_year": pair["NAL"].year, "roll_stage": pair["NAL"].stage,
                            "parcels_on_roll": int(len(nal)), "files": files_meta,
                            "outreach_owners": int(flagged[flagged.tier.isin(OUTREACH_TIERS)].owner_id.nunique())}
    return payloads, stats


def discover(cache: HttpCache, year: int | None = None) -> dict[str, dict[str, RollFile]]:
    return latest_pairs(list_roll_files(cache), year)
