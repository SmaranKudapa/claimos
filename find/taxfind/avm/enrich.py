"""Run the second opinion over the best candidates, within a spending cap, with caching."""
from __future__ import annotations

import statistics

from ..config import Settings
from ..engine.naive import NaiveClient
from ..engine.store import Store
from .providers import Lookup, Mock, NaiveData, Provider, RedfinApify, ZillowApify, lookup_for

CHECK_TIERS = ("strong", "possible", "review")
CONFIRM_AT, DISPUTE_BELOW = 1.05, 0.95


def build_providers(settings: Settings, naive: NaiveClient, mock_payloads: dict | None = None) -> list[Provider]:
    made: list[Provider] = []
    for name in [n.strip() for n in settings.avm_providers if n.strip()]:
        if name == "naive":
            made.append(NaiveData(naive, settings.naive_real_estate_tool))
        elif name == "apify_zillow":
            made.append(ZillowApify(settings.apify_token, settings.apify_zillow_actors))
        elif name == "apify_redfin":
            made.append(RedfinApify(settings.apify_token, settings.apify_redfin_actor))
        elif name == "mock":
            made.append(Mock(mock_payloads or {}))
    return [p for p in made if p.available()]


def _apply(p: dict, est: dict | None) -> None:
    sig = p["signals"]
    if not est or not est.get("value"):
        p["avm_check"] = "no_estimate"
        return
    level = sig.get("county_level") or 0.85
    back = sig.get("level_factor_now") or 1.0          # today's market -> Jan 1 of the tax year
    ratio = p["values"]["just_value"] / (est["value"] * back * level)
    sig["avm_ratio"] = round(ratio, 4)
    sig["avm"] = {k: est.get(k) for k in ("provider", "value", "low", "high", "sqft", "year_built", "beds", "baths",
                                           "last_sold_price", "last_sold_date", "home_type", "url")}
    if ratio >= CONFIRM_AT:
        p["avm_check"] = "confirmed"
    elif ratio < DISPUTE_BELOW:
        p["avm_check"] = "disputed"
        if p["tier"] in ("strong", "possible"):
            p["tier"] = "review"          # keep the case, take it off the mailing list
    else:
        p["avm_check"] = "inconclusive"


def enrich(payloads: list[dict], settings: Settings, store: Store, run_id: str, naive: NaiveClient,
           providers: list[Provider] | None = None, max_lookups: int | None = None, batch: int = 25) -> dict:
    max_lookups = max_lookups if max_lookups is not None else settings.avm_max_lookups
    eligible = [p for p in payloads if p["tier"] in CHECK_TIERS]
    for p in eligible:   # a building address would return the building, not this unit
        if p["property"]["use"] == "condo" and not p["property"].get("unit"):
            p["avm_check"] = "no_unit"
    targets = sorted((p for p in eligible if p.get("avm_check") != "no_unit"),
                     key=lambda p: -p["estimate"]["annual_savings"])[:max_lookups]
    by_key = {lookup_for(p).key: p for p in targets}
    providers = providers if providers is not None else build_providers(settings, naive, by_key)
    stats = {"targets": len(targets), "skipped_no_unit": sum(p.get("avm_check") == "no_unit" for p in eligible), "from_cache": 0, "looked_up": 0, "spend_usd": 0.0,
             "providers": [pr.name for pr in providers], "by_provider": {}}
    if not targets:
        return stats

    results: dict[str, dict] = {}
    pending: list[Lookup] = []
    for p in targets:
        lk = lookup_for(p)
        hit = None
        for pr in providers:
            hit = store.avm_get(lk.key, pr.name, settings.avm_cache_days)
            if hit:
                break
        if hit:
            results[lk.key] = hit
            stats["from_cache"] += 1
        else:
            pending.append(lk)

    for pr in providers:
        todo = [lk for lk in pending if lk.key not in results]
        if not todo:
            break
        try:
            pr.prime()
        except Exception as e:
            stats.setdefault("errors", []).append(f"{pr.name}: {type(e).__name__}: {str(e)[:200]}")
            continue
        for i in range(0, len(todo), batch):
            chunk = todo[i:i + batch]
            cost = len(chunk) * pr.cost_per_lookup
            if store.spend_total(run_id) + cost > settings.avm_budget_usd:
                stats["stopped_on_budget"] = True
                break
            try:
                got = pr.estimate(chunk)
            except Exception as e:  # one provider failing must not sink the run
                stats.setdefault("errors", []).append(f"{pr.name}: {type(e).__name__}: {str(e)[:200]}")
                break
            store.add_spend(run_id, pr.name, cost, len(chunk))
            stats["spend_usd"] += cost
            stats["looked_up"] += len(chunk)
            for k, est in got.items():
                d = est.to_dict()
                results[k] = d
                store.avm_put(k, pr.name, d)
                stats["by_provider"][pr.name] = stats["by_provider"].get(pr.name, 0) + 1

    # square-footage check against the county's own convention (some counties count garages and lanais)
    ratios = []
    for k, p in by_key.items():
        est = results.get(k)
        if est and est.get("sqft") and p["property"].get("sqft"):
            ratios.append(p["property"]["sqft"] / est["sqft"])
    norm = statistics.median(ratios) if len(ratios) >= 15 else None

    counts = {}
    for k, p in by_key.items():
        est = results.get(k)
        _apply(p, est)
        if norm and est and est.get("sqft") and p["property"].get("sqft"):
            rel = (p["property"]["sqft"] / est["sqft"]) / norm
            p["signals"]["sqft_vs_avm"] = round(rel, 3)
            if rel >= 1.15:
                p["signals"]["possible_sqft_error"] = True      # county may be taxing space that isn't there
        counts[p["avm_check"]] = counts.get(p["avm_check"], 0) + 1
    stats["checks"] = counts
    stats["sqft_norm"] = norm
    return stats


def carry_over(payloads: list[dict], store: Store) -> int:
    """A rerun that did not look a home up (budget, outside the top N, --no-avm) keeps the last
    estimate and its consequence: a case once disputed is not silently promoted back to strong."""
    n = 0
    for p in payloads:
        if p.get("avm_check") not in (None, "not_checked"):
            continue
        prev = store.get(p["case_id"])
        if not prev:
            continue
        old = prev.get("signals", {}).get("avm")
        if prev.get("avm_check") in ("confirmed", "inconclusive", "disputed") and old and old.get("value"):
            _apply(p, old)
            p["signals"]["avm_carried_over"] = True
            n += 1
        elif prev.get("avm_check") in ("no_estimate", "no_unit"):
            p["avm_check"] = prev["avm_check"]
    return n
