"""Matching records to people.

From the public roll we only ever take the owner of record and the tax-bill mailing address. We
group parcels that share an owner (same normalized name + mailing address) into one owner_id, so a
landlord with twelve over-assessed condos becomes one signup worth twelve appeals.

Deliberately not done here: skip tracing, phone numbers, emails. Cold contact goes by mail; phone
and text need prior consent (TCPA), which only the Sign up desk can collect.
"""
from __future__ import annotations

import hashlib
import re

import pandas as pd

from .normalize import norm_name_series, norm_street_series, owner_type_series, split_unit, unit_from_legal, unit_of


# Fla. Stat. 119.071(4)(d) exempts the home address of a long list of people — police, judges,
# prosecutors, firefighters, code officers, victims of domestic violence and others, usually
# extending to spouses and children. Under 119.071(4)(d)4.a. the property appraiser removes the
# NAME while the parcel address may legitimately stay public, so the signature of a suppressed
# owner in a public roll is a blank or placeholder owner name against a real address.
#
# DOR states its public files exclude exempt owners, but the 2026 NAL user guide documents no
# confidentiality flag and does not say how suppression is applied. Until that is confirmed in
# writing we fail CLOSED: an owner name we cannot read is treated as do-not-contact, never as a
# data-quality defect to be backfilled from another source.
SUPPRESSED_NAME_TOKENS = {
    "", "CONFIDENTIAL", "EXEMPT", "NOT AVAILABLE", "NOT AVAIL", "N/A", "NA", "NONE", "NO NAME",
    "WITHHELD", "RESTRICTED", "PRIVATE", "REDACTED", "UNKNOWN", "OWNER", "CURRENT OWNER",
    "CONFIDENTIAL RECORD", "PER FS 119.071", "SEE DEED",
}

STATE_CODES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO",
    "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY",
    "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND",
    "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY", "FLA": "FL",
}


def _clean(s: pd.Series) -> pd.Series:
    return s.astype("string").fillna("").str.strip()


def attach_owners(df: pd.DataFrame, home_state: str = "FL", copy: bool = True) -> pd.DataFrame:
    """Adds owner_id, owner_name, owner_type, mailing fields, absentee/out_of_state, parcels_in_county.

    copy=False mutates and returns the frame passed in. A county roll is close to a gigabyte, so the
    pipeline, which discards its reference anyway, passes False rather than paying for a duplicate.
    """
    out = df.copy() if copy else df
    name = _clean(out.get("OWN_NAME", pd.Series("", index=out.index)))
    a1 = _clean(out.get("OWN_ADDR1", pd.Series("", index=out.index)))
    a2 = _clean(out.get("OWN_ADDR2", pd.Series("", index=out.index)))
    city = _clean(out.get("OWN_CITY", pd.Series("", index=out.index)))
    st = _clean(out.get("OWN_STATE", pd.Series("", index=out.index))).str.upper().str.strip()
    st = st.map(lambda s: STATE_CODES.get(s, s))      # some counties write "FLORIDA", not "FL"
    z = _clean(out.get("OWN_ZIPCD", pd.Series("", index=out.index)))

    uniq_names = pd.Series(name.unique(), dtype="object")
    nmap = dict(zip(uniq_names, norm_name_series(uniq_names)))
    tmap = dict(zip(uniq_names, owner_type_series(uniq_names)))
    nn = name.map(nmap)
    uniq_a = pd.Series(a1.unique(), dtype="object")
    amap = dict(zip(uniq_a, norm_street_series(uniq_a)))
    na = a1.map(amap)
    nz = z.str.replace(r"\D", "", regex=True).str[:5]

    key = nn + "|" + na + "|" + nz
    ukeys = pd.Series(key.unique())
    idmap = dict(zip(ukeys, ukeys.map(lambda k: "own_" + hashlib.sha1(k.encode()).hexdigest()[:16])))
    out["owner_id"] = key.map(idmap)
    out["owner_name"] = name
    out["owner_type"] = name.map(tmap)
    out["mail_addr1"], out["mail_addr2"], out["mail_city"], out["mail_state"], out["mail_zip"] = a1, a2, city, st, z

    situs = _clean(out.get("PHY_ADDR1", pd.Series("", index=out.index)))
    uniq_s = pd.Series(situs.unique(), dtype="object")
    smap = dict(zip(uniq_s, norm_street_series(uniq_s)))
    sz = _clean(out.get("PHY_ZIPCD", pd.Series("", index=out.index))).str.replace(r"\D", "", regex=True).str[:5]
    out["absentee"] = ((situs.map(smap) + "|" + sz) != (na + "|" + nz)) & (na != "")
    out["out_of_state"] = (st != "") & (st != home_state.upper())
    out["parcels_in_county"] = out.groupby("owner_id")["owner_id"].transform("size").astype(int)

    # Confidential-owner suppression (see SUPPRESSED_NAME_TOKENS). Fail closed.
    bare = name.str.upper().str.replace(r"[^A-Z0-9/ ]", "", regex=True).str.strip()
    out["owner_suppressed"] = bare.isin(SUPPRESSED_NAME_TOKENS) | (bare == "")
    out["owner_suppression_reason"] = ""
    out.loc[out["owner_suppressed"], "owner_suppression_reason"] = (
        "Owner name is blank or a placeholder in the public roll. Under Fla. Stat. 119.071(4)(d) this is "
        "what a confidential-address exemption looks like, so this parcel is treated as do-not-contact. "
        "Do not attempt to identify the owner from another source.")

    # unit number for condos: the roll's own field, else the owner's mailing address when it is the
    # same street (owner lives there), else the legal description ("... CONDO UNIT 1105 ...")
    a2s = _clean(out.get("PHY_ADDR2", pd.Series("", index=out.index)))
    uniq_sit = pd.Series(situs.unique(), dtype="object")
    split = dict(zip(uniq_sit, uniq_sit.map(split_unit)))
    out["situs_street"] = situs.map(lambda v: split[v][0])
    unit = a2s.map(lambda v: unit_of(v) or re.sub(r"[^A-Z0-9-]", "", v.upper()) if v else "")
    unit = unit.where(unit != "", situs.map(lambda v: split[v][1]))
    # the owner's mailing unit is only this parcel's unit when they own one parcel in that building
    same_street = (situs.map(smap) == na) & (na != "")
    in_building = (out["owner_id"] + "|" + situs.map(smap) + "|" + sz)
    owns_one_here = in_building.map(in_building.value_counts()) == 1
    from_mail = a1.map(unit_of).where(same_street & owns_one_here, "")
    legal = _clean(out.get("S_LEGAL", pd.Series("", index=out.index)))
    is_condo = out.get("DOR_UC", pd.Series("", index=out.index)).astype("string").fillna("") == "004"
    from_legal = legal.where(is_condo, "").map(unit_from_legal)
    # a "unit" shared by several parcels at one address is a phase or building, not an apartment
    bkey = situs.map(smap) + "|" + sz + "|" + from_legal
    from_legal = from_legal.where((from_legal == "") | (bkey.map(bkey.value_counts()) == 1), "")
    final = unit.where(unit != "", from_mail).where(lambda u: u != "", from_legal)
    # a unit that two parcels in the same building both claim identifies neither
    ukey = situs.map(smap) + "|" + sz + "|" + final.str.upper()
    final = final.where((final == "") | (ukey.map(ukey.value_counts()) == 1), "")
    out["unit"] = final
    out["unit_source"] = "roll"
    out.loc[(unit == "") & (from_mail != ""), "unit_source"] = "mailing_address"
    out.loc[(unit == "") & (from_mail == "") & (from_legal != ""), "unit_source"] = "legal_description"
    out.loc[out["unit"] == "", "unit_source"] = ""
    return out


def portfolio_rollup(candidates: pd.DataFrame, savings_col: str = "est_savings") -> pd.DataFrame:
    """Per owner: how many flagged parcels and how much savings this run found."""
    g = candidates.groupby("owner_id").agg(flagged_parcels_in_run=("owner_id", "size"),
                                           portfolio_savings_in_run=(savings_col, "sum"))
    return candidates.merge(g, left_on="owner_id", right_index=True, how="left")
