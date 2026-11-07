"""Upload parser: turn whatever a partner or homeowner hands us (CSV, TSV, Excel, a PDF such as a
TRIM notice, plain text) into rows, then match each row to a parcel on the roll.

Matching order: parcel id (exact, separators ignored) -> street + ZIP (exact after normalization)
-> street within the same ZIP (fuzzy, >= 0.92 similarity) -> street alone when it is unique.
"""
from __future__ import annotations

import csv
import difflib
import io
import re
from pathlib import Path

import pandas as pd

from .normalize import norm_parcel, norm_street, norm_zip, split_unit, unit_of

_DIRS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}

FIELD_SYNONYMS = {
    "parcel_id": ["parcel_id", "parcel", "parcel number", "parcel no", "folio", "folio id", "strap", "account",
                  "account number", "apn", "pin", "property id", "alt key", "altkey"],
    "address": ["address", "property address", "site address", "situs", "situs address", "street", "street address",
                "address1", "address line 1", "location", "property"],
    "unit": ["unit", "apt", "unit number", "address2", "address line 2"],
    "city": ["city", "property city", "site city"],
    "zip": ["zip", "zipcode", "zip code", "postal code", "postal"],
    "owner": ["owner", "owner name", "name", "homeowner", "client", "full name"],
    "email": ["email", "e-mail", "email address"],
    "phone": ["phone", "phone number", "mobile", "cell"],
}


def _canon(h: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(h).lower().replace("_", " ")).strip()


def map_headers(cols: list[str]) -> dict[str, str]:
    """Return {standard_field: original_column}."""
    canon = {_canon(c): c for c in cols}
    out = {}
    for field, syns in FIELD_SYNONYMS.items():
        for s in syns:
            if s in canon and canon[s] not in out.values():
                out[field] = canon[s]
                break
    return out


def read_table(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, dtype=str)
    if ext in (".csv", ".tsv", ".txt"):
        raw = path.read_text(errors="replace")
        try:
            dialect = csv.Sniffer().sniff(raw[:5000], delimiters=",\t;|")
            sep = dialect.delimiter
        except csv.Error:
            sep = "\t" if ext == ".tsv" else ","
        df = pd.read_csv(io.StringIO(raw), sep=sep, dtype=str)
        if len(map_headers(list(df.columns))) == 0:      # free text, not a table
            return pd.DataFrame({"_text": [raw]})
        return df
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("PDF uploads need the optional dependency: pip install 'taxappeal-find[uploads]'") from e
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
        return pd.DataFrame({"_text": [text]})
    raise ValueError(f"unsupported upload type: {ext}")


_ADDR_LINE = re.compile(r"\b(\d{1,6}\s+(?:[NSEW]{1,2}\s+)?[A-Z0-9][A-Z0-9 .'-]{2,40}?\s(?:ST|AVE|BLVD|DR|RD|LN|CT|CIR|PL|TER|PKWY|HWY|TRL|WAY|PT|CV|LOOP|PLZ)\b\.?)", re.I)


def rows_from_text(text: str, parcel_index: set[str]) -> list[dict]:
    """Pull parcel ids (any token that matches the roll once separators are dropped) and street
    addresses out of free text such as a TRIM notice."""
    rows, seen = [], set()
    for tok in re.findall(r"[A-Z0-9][A-Z0-9.\- ]{8,30}[A-Z0-9]", text.upper()):
        for cand in {norm_parcel(tok), norm_parcel(tok.split(" ")[0])}:
            if len(cand) >= 8 and cand in parcel_index and cand not in seen:
                seen.add(cand)
                rows.append({"parcel_id": cand})
    if not rows:
        for m in _ADDR_LINE.finditer(text):
            rows.append({"address": m.group(1)})
    return rows


class ParcelMatcher:
    def __init__(self, roll: pd.DataFrame):
        r = roll[["PARCEL_ID", "PHY_ADDR1", "PHY_ADDR2", "PHY_ZIPCD"]].copy()
        r["pk"] = r.PARCEL_ID.map(norm_parcel)
        r["st"] = r.PHY_ADDR1.map(norm_street)
        r["z"] = r.PHY_ZIPCD.map(norm_zip)
        def _unit(row_a1, row_a2):
            a2 = "" if row_a2 is None or pd.isna(row_a2) else str(row_a2)
            u = unit_of(a2) or re.sub(r"[^A-Z0-9]", "", a2.upper())
            return u or split_unit(row_a1)[1].replace(" ", "")
        r["unit"] = [_unit(a1, a2) for a1, a2 in zip(r.PHY_ADDR1, r.PHY_ADDR2)]
        self.street_of = dict(zip(r.PARCEL_ID, r.st))
        self.zip_of = dict(zip(r.PARCEL_ID, r.z))
        self.by_pk = dict(zip(r.pk, r.PARCEL_ID))
        alt = roll.get("ALT_KEY")
        if alt is not None:
            # alternate keys are often short counters ("1", "1001") that collide with CRM account
            # numbers; only long ones that point at exactly one parcel are trusted
            ak = alt.map(norm_parcel)
            counts = ak.value_counts()
            for a, p in zip(ak, roll.PARCEL_ID):
                if a and len(a) >= 6 and counts.get(a, 0) == 1:
                    self.by_pk.setdefault(a, p)
        self.by_addr: dict[str, list[tuple[str, str]]] = {}
        self.by_zip: dict[str, dict[str, list[tuple[str, str]]]] = {}
        self.by_street: dict[str, list[tuple[str, str]]] = {}
        for pid, st, z, u in zip(r.PARCEL_ID, r.st, r.z, r.unit):
            if not st:
                continue
            self.by_addr.setdefault(f"{st}|{z}", []).append((pid, u))
            self.by_zip.setdefault(z, {}).setdefault(st, []).append((pid, u))
            self.by_street.setdefault(st, []).append((pid, u))

    @property
    def parcel_index(self) -> set[str]:
        return set(self.by_pk)

    @staticmethod
    def _pick(hits: list[tuple[str, str]], unit: str) -> tuple[str | None, bool]:
        if len(hits) == 1:
            return hits[0][0], True
        if unit:
            u = re.sub(r"[^A-Z0-9]", "", unit.upper())
            exact = [p for p, hu in hits if hu == u]
            if len(exact) == 1:
                return exact[0], True
        return None, False

    @staticmethod
    def _parts(st: str) -> tuple[str, frozenset, str]:
        """house number, directional tokens, the rest — fuzzy matching may only touch the rest."""
        toks = st.split()
        num = toks[0] if toks and toks[0][:1].isdigit() else ""
        dirs = frozenset(x for x in toks[1:] if x in _DIRS)
        rest = " ".join(x for x in toks[1 if num else 0:] if x not in _DIRS)
        return num, dirs, rest

    def _by_address(self, address, unit, zip_code) -> dict | None:
        st, z = norm_street(address), norm_zip(zip_code)
        unit = unit or unit_of(address) or split_unit(address)[1].replace(" ", "")
        if not st:
            return None
        hits = self.by_addr.get(f"{st}|{z}", []) if z else []
        if hits:
            pid, ok = self._pick(hits, unit)
            if ok:
                return {"parcel_id": pid, "method": "address+zip", "score": 1.0}
            return {"parcel_id": None, "method": "ambiguous", "score": 0.0, "candidates": [h[0] for h in hits[:10]]}
        if z and z in self.by_zip:
            num, dirs, rest = self._parts(st)
            same = [s for s in self.by_zip[z] if self._parts(s)[:2] == (num, dirs)] if num else []
            best = difflib.get_close_matches(rest, [self._parts(s)[2] for s in same], n=1, cutoff=0.88)
            if best:
                cand = [s for s in same if self._parts(s)[2] == best[0]]
                if len(cand) == 1:
                    pid, ok = self._pick(self.by_zip[z][cand[0]], unit)
                    if ok:
                        score = difflib.SequenceMatcher(None, rest, best[0]).ratio()
                        return {"parcel_id": pid, "method": "fuzzy_in_zip", "score": round(score, 3)}
        hits = [h for h in self.by_street.get(st, []) if not z or self.zip_of.get(h[0]) in (z, "")]
        if hits:
            pid, ok = self._pick(hits, unit)
            if ok:
                return {"parcel_id": pid, "method": "street_unique", "score": 0.9}
        return None

    def match(self, parcel_id=None, address=None, unit=None, zip_code=None) -> dict:
        by_addr = self._by_address(address, unit, zip_code) if address else None
        if parcel_id:
            pid = self.by_pk.get(norm_parcel(parcel_id))
            if pid:
                # an id that points at a different street than the one given: trust the address
                if address and norm_street(address) and self.street_of.get(pid) and \
                        self.street_of[pid] != norm_street(address):
                    if by_addr and by_addr.get("parcel_id"):
                        return by_addr | {"method": by_addr["method"] + " (id disagreed)"}
                    return {"parcel_id": None, "method": "id_address_conflict", "score": 0.0, "candidates": [pid]}
                return {"parcel_id": pid, "method": "parcel_id", "score": 1.0}
        return by_addr or {"parcel_id": None, "method": "unmatched", "score": 0.0}


def parse_and_match(path: Path, roll: pd.DataFrame) -> pd.DataFrame:
    df = read_table(Path(path))
    matcher = ParcelMatcher(roll)
    if "_text" in df.columns:
        rows = rows_from_text(df["_text"].iloc[0], matcher.parcel_index)
        df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["parcel_id", "address"])
        cols = {c: c for c in df.columns}
    else:
        cols = map_headers(list(df.columns))
    res = []
    for i, row in df.iterrows():
        get = lambda f: (str(row[cols[f]]).strip() if f in cols and pd.notna(row[cols[f]]) else None)  # noqa: E731
        m = matcher.match(get("parcel_id"), get("address"), get("unit"), get("zip"))
        res.append({"row": int(i), "input_parcel": get("parcel_id"), "input_address": get("address"),
                    "input_zip": get("zip"), "owner_supplied": get("owner"), "email_supplied": get("email"),
                    "phone_supplied": get("phone"), **{k: v for k, v in m.items() if k != "candidates"},
                    "ambiguous_with": ",".join(m.get("candidates", []))})
    return pd.DataFrame(res)
