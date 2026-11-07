"""Home-value estimates (AVMs) as an independent second opinion on the shortlist.

Why only the shortlist: lookups cost money per home and Lee County alone has 360k houses and
condos. The roll screen is free and covers everything; the AVM confirms or kills its top picks.
Why not as evidence: appeal boards weigh comparable sales, not Zestimates. The AVM's job is to
catch false positives (waterfront, renovations, wrong square footage) before anyone is mailed.

Providers, tried in the configured order until one returns a value:
  naive         Naive data catalogue, domain real_estate (tool id from NAIVE_REAL_ESTATE_TOOL)
  apify_zillow  maxcopell/zillow-detail-scraper (addresses[]), then kawsar/affordable-zillow-details-scraper (address[])
  apify_redfin  tri_angle/redfin-detail (addresses[])
  mock          deterministic fake values for offline demos; always labelled provider="mock"
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

import requests

from ..engine.naive import NaiveClient
from ..engine.normalize import norm_street, norm_zip, split_unit, unit_of

APIFY = "https://api.apify.com/v2"


@dataclass
class Estimate:
    provider: str
    value: float | None
    low: float | None = None
    high: float | None = None
    sqft: float | None = None
    year_built: float | None = None
    beds: float | None = None
    baths: float | None = None
    last_sold_price: float | None = None
    last_sold_date: str | None = None
    home_type: str | None = None
    url: str | None = None
    raw_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Lookup:
    key: str          # normalized "STREET|ZIP"
    query: str        # "4012 SW 17th Ave, Cape Coral, FL 33914"
    unit: str | None = None


def lookup_for(p: dict) -> Lookup:
    pr = p["property"]
    street = pr["address"] + (f" #{pr['unit']}" if pr.get("unit") else "")
    q = f"{street}, {pr.get('city') or ''}, {p['jurisdiction']['state']} {pr.get('zip') or ''}".replace(" ,", ",").strip()
    return Lookup(key=f"{norm_street(pr['address'])}|{norm_zip(pr.get('zip'))}|{pr.get('unit') or ''}", query=q, unit=pr.get("unit"))


# ---------------- helpers ----------------
_MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*([KkMm])?")


def money(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    m = _MONEY.search(str(v))
    if not m:
        try:
            x = float(str(v).replace(",", ""))
            return x if x > 0 else None
        except ValueError:
            return None
    x = float(m.group(1).replace(",", ""))
    return x * {"k": 1e3, "m": 1e6}.get((m.group(2) or "").lower(), 1)


def dig(d, *paths, default=None):
    """First non-empty value among dotted paths."""
    for path in paths:
        cur = d
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        if cur not in (None, "", [], {}):
            return cur
    return default


def _addr_parts(item: dict) -> tuple[str, str, str]:
    """(normalized street, zip, unit) of a provider row, from whichever fields it carries."""
    a = dig(item, "streetAddress", "street_address", "address", "mainHouseInfo.fullStreetAddress", "addressLine1")
    zp = dig(item, "zipcode", "zip", "postalCode", "address.zipcode", "addressSectionInfo.zip")
    if isinstance(a, dict):
        zp = zp or a.get("zipcode") or a.get("zip")
        a = a.get("streetAddress") or a.get("street") or ""
    a = str(a or "")
    if not zp:
        m = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", a)
        zp = m.group(1) if m else ""
    street_part = a.split(",")[0]
    unit = unit_of(street_part) or split_unit(street_part)[1]
    return norm_street(street_part), norm_zip(zp), re.sub(r"[^A-Z0-9]", "", unit.upper())


def _match(items: list[dict], lookups: list[Lookup]) -> dict[str, dict]:
    """Map provider rows back to our lookups (providers rarely keep input order). A row may serve
    one lookup only. An echoed input query wins; otherwise the normalized street must be equal,
    the ZIP must agree when both sides have one, and a condo's unit must be equal."""
    out: dict[str, dict] = {}
    used: set[int] = set()
    by_query = {lk.query.upper(): lk for lk in lookups}
    for i, it in enumerate(items):
        echo = dig(it, "input_query", "scraperInput", "inputAddress")
        if isinstance(echo, str) and echo.upper() in by_query and by_query[echo.upper()].key not in out:
            out[by_query[echo.upper()].key] = it
            used.add(i)
    for i, it in enumerate(items):
        if i in used:
            continue
        street, zp, unit = _addr_parts(it)
        if not street:
            continue
        for lk in lookups:
            if lk.key in out:
                continue
            l_street, l_zip, _ = lk.key.split("|", 2)
            if street != l_street or (zp and l_zip and zp != l_zip):
                continue
            want = re.sub(r"[^A-Z0-9]", "", (lk.unit or "").upper())
            if want != unit:
                continue
            out[lk.key] = it
            used.add(i)
            break
    return out


# ---------------- providers ----------------
class Provider:
    name = "base"
    cost_per_lookup = 0.0

    def prime(self) -> None:
        """Anything that must be known before the first lookup is costed."""

    def available(self) -> bool:
        return True

    def estimate(self, lookups: list[Lookup]) -> dict[str, Estimate]:
        raise NotImplementedError


class ZillowApify(Provider):
    name = "apify_zillow"
    cost_per_lookup = 0.002   # ~ $1.70-2.00 per 1,000 results (store listing); budget guard uses this

    def __init__(self, token: str | None, actors: list[str], session: requests.Session | None = None, timeout: int = 300):
        self.token, self.actors, self.timeout = token, actors, timeout
        self.s = session or requests.Session()

    def available(self) -> bool:
        return bool(self.token)

    def _run(self, actor: str, payload: dict) -> list[dict]:
        r = self.s.post(f"{APIFY}/acts/{actor}/run-sync-get-dataset-items", params={"timeout": self.timeout},
                        headers={"Authorization": f"Bearer {self.token}"}, json=payload, timeout=self.timeout + 30)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("items", [])

    @staticmethod
    def parse(it: dict) -> Estimate:
        sold_date = dig(it, "dateSold", "lastSoldDate")
        hist = it.get("priceHistory") or []
        last_sold = money(dig(it, "lastSoldPrice"))
        if not last_sold and isinstance(hist, list):
            for h in hist:
                if isinstance(h, dict) and "sold" in str(h.get("event", "")).lower():
                    last_sold, sold_date = money(h.get("price")), h.get("date")
                    break
        url = dig(it, "url", "propertyUrl", "hdpUrl")
        if url and str(url).startswith("/"):
            url = "https://www.zillow.com" + url
        value = money(dig(it, "zestimate", "zestimateValue"))
        low, high = money(dig(it, "zestimateRangeLow", "zestimateLow")), money(dig(it, "zestimateRangeHigh", "zestimateHigh"))
        pct_lo, pct_hi = dig(it, "zestimateLowPercent"), dig(it, "zestimateHighPercent")
        if value and low is None and pct_lo not in (None, ""):
            low = value * (1 - float(pct_lo) / 100)
        if value and high is None and pct_hi not in (None, ""):
            high = value * (1 + float(pct_hi) / 100)
        return Estimate(provider="zillow", value=value, low=low, high=high,
                        sqft=money(dig(it, "livingArea", "livingAreaValue", "squareFeet")),
                        year_built=money(dig(it, "yearBuilt")), beds=money(dig(it, "bedrooms", "beds")),
                        baths=money(dig(it, "bathrooms", "baths")), last_sold_price=last_sold,
                        last_sold_date=str(sold_date) if sold_date else None, home_type=dig(it, "homeType"),
                        url=url, raw_keys=sorted(it.keys())[:60])

    def estimate(self, lookups: list[Lookup]) -> dict[str, Estimate]:
        found: dict[str, Estimate] = {}
        pending = list(lookups)
        for actor in self.actors:
            if not pending:
                break
            key = "addresses" if actor.startswith("maxcopell") else "address"
            try:
                items = self._run(actor, {key: [lk.query for lk in pending]} | ({"maxItems": len(pending)} if key == "address" else {}))
            except requests.RequestException:
                continue
            for k, it in _match(items, pending).items():
                est = self.parse(it)
                if est.value:
                    found[k] = est
            pending = [lk for lk in pending if lk.key not in found]
        return found


class RedfinApify(Provider):
    name = "apify_redfin"
    cost_per_lookup = 0.003

    def __init__(self, token: str | None, actor: str, session: requests.Session | None = None, timeout: int = 300):
        self.token, self.actor, self.timeout = token, actor, timeout
        self.s = session or requests.Session()

    def available(self) -> bool:
        return bool(self.token)

    @staticmethod
    def parse(it: dict) -> Estimate:
        value = money(dig(it, "avmInfo.predictedValue", "predictedValue", "redfinEstimate", "avm.predictedValue"))
        if value is None:
            value = money(dig(it, "avmInfo.sectionPreviewText"))
        url = dig(it, "mainHouseInfo.url", "url")
        if url and str(url).startswith("/"):
            url = "https://www.redfin.com" + url
        return Estimate(provider="redfin", value=value,
                        sqft=money(dig(it, "addressSectionInfo.sqFt.value", "sqFt.value", "sqft")),
                        year_built=money(dig(it, "addressSectionInfo.yearBuilt", "yearBuilt")),
                        beds=money(dig(it, "addressSectionInfo.beds", "beds")),
                        baths=money(dig(it, "addressSectionInfo.baths", "baths")),
                        last_sold_price=money(dig(it, "avmInfo.priceInfo.amount", "lastSoldPrice")),
                        url=url, raw_keys=sorted(it.keys())[:60])

    def estimate(self, lookups: list[Lookup]) -> dict[str, Estimate]:
        r = self.s.post(f"{APIFY}/acts/{self.actor}/run-sync-get-dataset-items", params={"timeout": self.timeout},
                        headers={"Authorization": f"Bearer {self.token}"},
                        json={"addresses": [lk.query for lk in lookups]}, timeout=self.timeout + 30)
        r.raise_for_status()
        items = [i for i in r.json() if i.get("ok", True) is not False]
        out = {}
        for k, it in _match(items, lookups).items():
            est = self.parse(it)
            if est.value:
                out[k] = est
        return out


class NaiveData(Provider):
    """Naive data catalogue. Input/output field names differ per tool, so they are discovered from the
    tool's own input schema (GET /v1/data/tools/{id}) and parsed defensively. Run
    `taxfind naive-tools` at the hackathon to pick the tool, then set NAIVE_REAL_ESTATE_TOOL."""
    name = "naive"

    def __init__(self, client: NaiveClient, tool_id: str | None):
        self.c, self.tool_id = client, tool_id
        self._schema = None
        self.cost_per_lookup = 0.0

    def available(self) -> bool:
        return self.c.live and bool(self.tool_id)

    def prime(self) -> None:
        self._input_slot()      # loads the tool's listed price before any lookup is costed

    def _input_slot(self) -> tuple[str, str]:
        if self._schema is None:
            self._schema = self.c.data_tool(self.tool_id)
            self.cost_per_lookup = (self._schema.get("price", {}).get("micro_usd") or 0) / 1e6
        inp = self._schema.get("input", {})
        for part in ("query", "body", "path"):
            props = inp.get(part) or {}
            props = props.get("properties", props) if isinstance(props, dict) else {}
            for name in props:
                if re.search(r"address|location|query|search", name, re.I):
                    return part, name
        return "query", "address"

    def estimate(self, lookups: list[Lookup]) -> dict[str, Estimate]:
        part, name = self._input_slot()
        out = {}
        for lk in lookups:
            run = self.c.run_data_tool(self.tool_id, **{part: {name: lk.query}}, idem=f"avm-{hashlib.sha1(lk.key.encode()).hexdigest()[:20]}")
            data = run.get("data")
            items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
            for it in items:
                v = money(dig(it, "zestimate", "estimate", "value", "price", "estimated_value", "avm", "predicted_value"))
                if v:
                    out[lk.key] = Estimate(provider=f"naive:{self.tool_id}", value=v,
                                           sqft=money(dig(it, "livingArea", "sqft", "living_area")),
                                           year_built=money(dig(it, "yearBuilt", "year_built")),
                                           url=dig(it, "url"), raw_keys=sorted(it.keys())[:60] if isinstance(it, dict) else [])
                    break
        return out


class Mock(Provider):
    """Deterministic stand-in for demos without keys: value = county value / county level, nudged
    by a hash of the address. Never used unless explicitly configured."""
    name = "mock"

    def __init__(self, payload_by_key: dict[str, dict]):
        self.by = payload_by_key

    def estimate(self, lookups: list[Lookup]) -> dict[str, Estimate]:
        out = {}
        for lk in lookups:
            p = self.by.get(lk.key)
            if not p:
                continue
            h = int(hashlib.sha1(lk.key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
            fair = p["values"]["just_value"] / (p["signals"]["county_level"] or 0.85)
            out[lk.key] = Estimate(provider="mock", value=round(fair * (0.80 + 0.30 * h), -3),
                                   sqft=p["property"].get("sqft"), raw_keys=["mock"])
        return out
