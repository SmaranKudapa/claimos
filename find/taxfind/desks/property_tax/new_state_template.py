"""Template for adding a state to the property-tax desk. Copy to `<state>/__init__.py`, fill in the
three functions, and register it in `taxfind/pipeline.py: DESKS`.

The detection rule (`screen.py`) is shared. A state's job is only to get its roll and sales into
the common columns screen.py reads, and to say when its filing window is:

  roll  (one row per parcel):
    PARCEL_ID   str   the county's parcel / account number
    DOR_UC      str   '001' single-family house, '004' condo (map the state's own use codes to these)
    NBRHD_CD    str   appraisal neighborhood (or MKT_AR market area as a fallback)
    JV          float the county's market value for the tax year
    AV_NSD      float the capped/assessed value taxes are figured on (= JV where there is no cap)
    JV_HMSTD    float >0 when an owner-occupied exemption applies, else NaN
    LND_VAL     float land value (keeps waterfront lots apart from dry lots)
    TOT_LVG_AREA float living area in sq ft
    EFF_YR_BLT / ACT_YR_BLT float  effective / actual year built
    PHY_ADDR1, PHY_ADDR2, PHY_CITY, PHY_ZIPCD   situs address
    OWN_NAME, OWN_ADDR1, OWN_ADDR2, OWN_CITY, OWN_STATE, OWN_ZIPCD   owner of record + mailing address
  sales:
    PARCEL_ID, SALE_YR, SALE_MO, SALE_PRC, QUAL_CD ('01' = arm's length), VI_CD ('I' = improved),
    MULTI_PAR_SAL (NA for single-parcel sales)

Non-disclosure states (sale prices not public — e.g. Texas): leave sales empty. screen.py then
has no sales signal, so nothing reaches `strong`/`possible`; for those states set the rule to
neighbors-only (uniformity), which is the legal basis for equity appeals there, and say so in
`county_check`.
"""
from __future__ import annotations

import datetime as dt

STATE = "XX"


def discover(cache, year: int | None = None) -> dict:
    """Return {county_code: {"NAL": RollFile, "SDF": RollFile}} for the newest roll per county."""
    raise NotImplementedError


def run_county(settings, cache, pair, run_id: str, today: dt.date | None = None):
    """Load the county, map to the common columns, call screen.screen(), attach_owners(),
    evidence(), and build payloads (see florida/__init__.py for the reference implementation)."""
    raise NotImplementedError


def filing_window(tax_year: int, today: dt.date | None = None) -> dict:
    """{"opens", "closes", "status", "basis"} for this state's residential appeal deadline."""
    raise NotImplementedError
