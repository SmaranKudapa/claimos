"""Normalization shared by every desk: addresses, owner names, parcel ids."""
from __future__ import annotations

import math
import re

_SUFFIX = {
    "STREET": "ST", "STR": "ST", "AVENUE": "AVE", "AV": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "ROAD": "RD", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR", "PLACE": "PL", "TERRACE": "TER",
    "PARKWAY": "PKWY", "HIGHWAY": "HWY", "TRAIL": "TRL", "WAY": "WAY", "POINT": "PT", "COVE": "CV",
    "SQUARE": "SQ", "LOOP": "LOOP", "PLAZA": "PLZ", "CROSSING": "XING", "ISLAND": "IS", "KEY": "KY",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "NORTHEAST": "NE", "NORTHWEST": "NW",
    "SOUTHEAST": "SE", "SOUTHWEST": "SW",
}
_UNIT = re.compile(r"(?:\b(?:APT|UNIT|STE|SUITE|BLDG|PH)\b\.?|#)\s*[A-Z0-9-]+")
_NONALNUM = re.compile(r"[^A-Z0-9 ]+")
_WS = re.compile(r"\s+")


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or str(v) in ("", "<NA>", "nan", "NaN", "None")


_TRAIL_UNIT = re.compile(r"^(.*?\S)\s{2,}([A-Z0-9][A-Z0-9-]{0,6}(?: [A-Z0-9]{1,2})?)\s*$")


def split_unit(addr) -> tuple[str, str]:
    """('1160 SCENIC GULF DR  A712') -> ('1160 SCENIC GULF DR', 'A712');
    ('500 BEACH BLVD #104') -> ('500 BEACH BLVD', '104'). Units after a single space are left alone:
    'COUNTY ROAD 30A' is a road, not unit 30A."""
    if _blank(addr):
        return "", ""
    s = str(addr).split(",")[0].rstrip()
    m = _UNIT.search(s.upper())
    if m:
        return s[:m.start()].rstrip(), unit_of(s)
    m = _TRAIL_UNIT.match(s.upper())
    if m and any(ch.isdigit() for ch in m.group(2)) and len(m.group(1).split()) >= 2:
        return s[:len(m.group(1))].rstrip(), m.group(2)
    return s, ""


def norm_street(addr: str | None, keep_unit: bool = False) -> str:
    """'4012 S.W. 17th Avenue, Unit 2' -> '4012 SW 17TH AVE'."""
    if _blank(addr):
        return ""
    s = str(addr).upper().replace(".", "")
    s = s.split(",")[0]
    if not keep_unit:
        s = split_unit(s)[0]
        s = _UNIT.sub(" ", s)
    s = _NONALNUM.sub(" ", s)
    toks = [_SUFFIX.get(t, t) for t in _WS.sub(" ", s).strip().split(" ") if t]
    return " ".join(toks)


def unit_of(addr: str | None) -> str:
    if _blank(addr):
        return ""
    ms = list(_UNIT.finditer(str(addr).upper()))
    if not ms:
        return ""
    # "BLDG 1 APT 1105" is apartment 1105: an apartment-level marker beats a building marker
    pick = [m for m in ms if not m.group(0).startswith(("BLDG", "PH"))] or ms
    return re.sub(r"^(?:APT|UNIT|STE|SUITE|BLDG|PH|#)\.?\s*", "", pick[-1].group(0)).strip()


_LEGAL_UNIT = re.compile(r"\b(?:UNIT|APT|U)\s*(?:NO\.?\s*)?#?\s*([A-Z]?\d+[A-Z0-9-]*)\b")


def unit_from_legal(legal) -> str:
    """'VILLA GRANDE CONDO UNIT 1105 BLDG 11' -> '1105'."""
    if _blank(legal):
        return ""
    m = _LEGAL_UNIT.search(str(legal).upper())
    return m.group(1) if m else ""


def norm_zip(z) -> str:
    if _blank(z):
        return ""
    s = re.sub(r"\D", "", str(z))
    return s[:5] if len(s) >= 5 else ""


def norm_parcel(pid) -> str:
    return "" if _blank(pid) else re.sub(r"[^A-Z0-9]", "", str(pid).upper())


def address_key(street: str | None, zip_code=None) -> str:
    return f"{norm_street(street)}|{norm_zip(zip_code)}"


# ---------------- owners ----------------
_ENTITY_PATTERNS = [
    ("government", r"\b(?:CITY OF|COUNTY|STATE OF|BOARD OF|SCHOOL BOARD|UNITED STATES|USA|TIITF|DISTRICT|AUTHORITY|HOUSING AUTH)\b"),
    ("association", r"\b(?:ASSOCIATION|ASSN|ASSOC|HOA|CONDOMINIUM|CONDO|PROPERTY OWNERS|COMMUNITY DEV)\b"),
    ("bank", r"\b(?:BANK|MORTGAGE|FEDERAL NATIONAL|FANNIE|FREDDIE|HUD|SECRETARY OF HOUSING|LENDING|LOAN)\b"),
    ("religious_charity", r"\b(?:CHURCH|MINISTR|DIOCESE|FOUNDATION|CHARIT)\b"),
    ("company", r"\b(?:LLC|L L C|INC|CORP|CORPORATION|CO|LP|LLP|LTD|PARTNERS|PARTNERSHIP|HOLDINGS|PROPERTIES|INVESTMENTS|GROUP|REALTY|CAPITAL|VENTURES|ENTERPRISES|FUND|REIT)\b"),
    ("estate", r"\b(?:ESTATE OF|EST OF|DECEASED|HEIRS)\b"),
    ("trust", r"\b(?:TRUST|TRUSTEE|TR|TRS|REV TR|LIV TR|LIVING TRUST)\b"),
]
_ENTITY_RE = [(k, re.compile(p)) for k, p in _ENTITY_PATTERNS]


def owner_type(name: str | None) -> str:
    s = "" if _blank(name) else _NONALNUM.sub(" ", str(name).upper())
    for kind, rx in _ENTITY_RE:
        if rx.search(s):
            return kind
    return "individual" if s.strip() else "unknown"


def norm_name(name: str | None) -> str:
    s = "" if _blank(name) else _NONALNUM.sub(" ", str(name).upper())
    s = re.sub(r"\b(THE|ET AL|ETAL|H/W|JTWROS|JT TEN|TEN COM|TIC|L/E|LE)\b", " ", s)
    return _WS.sub(" ", s).strip()


def split_people(name: str | None) -> list[str]:
    """'SMITH JOHN & MARY' -> ['SMITH JOHN', 'SMITH MARY'] (roll convention: LAST FIRST)."""
    s = norm_name(name)
    if not s or owner_type(name) != "individual":
        return [s] if s else []
    parts = [norm_name(p) for p in re.split(r"\s(?:AND)\s|&|\+", str(name).upper()) if norm_name(p)]
    if len(parts) <= 1:
        return parts
    last = parts[0].split(" ")[0]
    out = [parts[0]]
    for p in parts[1:]:
        out.append(p if len(p.split(" ")) > 1 else f"{last} {p}")
    return out


# ---------------- vectorized versions (same results, for whole rolls) ----------------
import pandas as _pd  # noqa: E402

_NAME_DROP = r"\b(?:THE|ET AL|ETAL|H/W|JTWROS|JT TEN|TEN COM|TIC|L/E|LE)\b"


def norm_name_series(s: "_pd.Series") -> "_pd.Series":
    x = s.fillna("").astype(str).str.upper().str.replace(r"[^A-Z0-9 ]+", " ", regex=True)
    x = x.str.replace(_NAME_DROP, " ", regex=True)
    return x.str.replace(r"\s+", " ", regex=True).str.strip()


def owner_type_series(s: "_pd.Series") -> "_pd.Series":
    x = s.fillna("").astype(str).str.upper().str.replace(r"[^A-Z0-9 ]+", " ", regex=True)
    out = _pd.Series("individual", index=s.index, dtype="object")
    out[x.str.strip() == ""] = "unknown"
    done = x.str.strip() == ""
    for kind, rx in _ENTITY_RE:
        hit = ~done & x.str.contains(rx, regex=True)
        out[hit] = kind
        done |= hit
    return out


_SUFFIX_RX = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _SUFFIX), key=len, reverse=True)) + r")\b")


def norm_street_series(s: "_pd.Series") -> "_pd.Series":
    x = s.fillna("").astype(str).str.upper().str.replace(".", "", regex=False).str.split(",").str[0]
    trail = x.str.extract(_TRAIL_UNIT)
    has = trail[1].notna() & trail[1].str.contains(r"\d", regex=True, na=False) & (trail[0].str.split().str.len() >= 2)
    x = x.where(~has, trail[0])
    x = x.str.replace(_UNIT, " ", regex=True).str.replace(r"[^A-Z0-9 ]+", " ", regex=True)
    x = x.str.replace(r"\s+", " ", regex=True).str.strip()
    return x.str.replace(_SUFFIX_RX, lambda m: _SUFFIX[m.group(1)], regex=True)
