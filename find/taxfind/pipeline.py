"""One Find cycle: discover sources -> ingest -> detect -> match owners -> second opinion -> store -> hand off."""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import traceback

from .avm.enrich import carry_over, enrich
from .config import Settings
from .desks.property_tax import florida
from .engine.handoff import post_cards, write_files
from .engine.ingest import HttpCache
from .engine.naive import NaiveClient
from .engine.store import Store

DESKS = {"FL": florida}


def _key(s: str) -> str:
    """County name as a lookup key: 'St. Johns' == 'Saint Johns', 'Miami-Dade' == 'Dade'."""
    k = re.sub(r"^st\.?\s+", "saint ", s.strip().lower())
    k = re.sub(r"[^a-z]", "", k)
    return {"miamidade": "dade"}.get(k, k)


def select(pairs: dict, counties: list[str] | str) -> dict:
    if counties == "all" or counties == ["all"]:
        return pairs
    want = {_key(c) if not c.strip().isdigit() else c.strip().zfill(2) for c in counties}
    return {no: p for no, p in pairs.items() if no in want or _key(p["NAL"].county) in want}


def _processed_path(settings: Settings):
    return settings.data_dir / "processed.json"


def changed_only(settings: Settings, pairs: dict) -> dict:
    try:
        seen = json.loads(_processed_path(settings).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        seen = {}
    return {no: p for no, p in pairs.items()
            if seen.get(no) != {k: f"{p[k].year}/{p[k].stage}/{p[k].modified}" for k in ("NAL", "SDF")}}


def _mark_processed(settings: Settings, no: str, pair: dict) -> None:
    path = _processed_path(settings)
    try:
        seen = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        seen = {}
    seen[no] = {k: f"{pair[k].year}/{pair[k].stage}/{pair[k].modified}" for k in ("NAL", "SDF")}
    path.write_text(json.dumps(seen, indent=1, sort_keys=True))


def run(settings: Settings, state: str = "FL", counties: list[str] | str = "all", year: int | None = None,
        avm: bool = True, max_avm: int | None = None, handoff: str = "file", only_changed: bool = False,
        today: dt.date | None = None, log=print) -> dict:
    settings.ensure()
    desk = DESKS[state.upper()]
    store = Store(settings.db_path)
    cache = HttpCache(settings.cache_dir / "http")
    naive = NaiveClient(settings.naive_api_key, settings.naive_base_url, dry_run=settings.dry_run,
                        outbox=settings.data_dir / "naive_outbox.jsonl")
    run_id = f"{state.upper()}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    store.start_run(run_id, state.upper(), counties if isinstance(counties, str) else ",".join(counties))

    pairs = select(desk.discover(cache, year), counties)
    if only_changed:
        pairs = changed_only(settings, pairs)
    log(f"[{run_id}] {len(pairs)} county roll(s) to process")
    summary = {"run_id": run_id, "state": state.upper(), "counties": [], "errors": []}
    t0 = time.time()
    for no, pair in sorted(pairs.items(), key=lambda kv: kv[1]["NAL"].size):
        name = pair["NAL"].county
        t1 = time.time()
        try:
            payloads, stats = desk.run_county(settings, cache, pair, run_id, today)
            if avm:
                stats["avm"] = enrich(payloads, settings, store, run_id, naive, max_lookups=max_avm)
            stats["avm_carried_over"] = carry_over(payloads, store)
            stats["store"] = store.upsert_candidates(payloads, run_id)
            stats["seconds"] = round(time.time() - t1, 1)
            stats.pop("files", None)
            store.save_county_stats(run_id, state.upper(), no, stats)
            summary["counties"].append(stats)
            del payloads
            _mark_processed(settings, no, pair)
            t = stats["tiers"]
            log(f"  {name:<14} {stats['homes']:>8,} homes  strong {t.get('strong', 0):>6,}  possible {t.get('possible', 0):>5,}"
                f"  ~${stats['strong_savings_total']:>12,.0f}/yr  ({stats['seconds']}s)")
        except Exception as e:
            summary["errors"].append({"county": name, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]})
            log(f"  {name:<14} FAILED: {type(e).__name__}: {e}")

    out_dir = settings.out_dir / run_id
    summary["files"] = write_files(store.iter_payloads("last_seen_run=?", (run_id,)), out_dir)
    if handoff == "board":
        summary["handoff"] = post_cards(store, naive, settings.naive_board, settings.naive_qualify_agent,
                                        settings.handoff_max_cards, include_closed=settings.handoff_include_closed,
                                        where="last_seen_run=?", params=(run_id,), run_tag=run_id)
    tiers: dict[str, int] = {}
    for c in summary["counties"]:
        for k, v in c["tiers"].items():
            tiers[k] = tiers.get(k, 0) + v
    summary["totals"] = {"counties_ok": len(summary["counties"]), "counties_failed": len(summary["errors"]),
                         "homes": sum(c["homes"] for c in summary["counties"]), "tiers": tiers,
                         "strong_savings_total": round(sum(c["strong_savings_total"] for c in summary["counties"]), 2),
                         "outreach_owners": sum(c.get("outreach_owners", 0) for c in summary["counties"]),
                         "seconds": round(time.time() - t0, 1)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    status = "ok" if not summary["errors"] else ("partial" if summary["counties"] else "failed")
    ho = summary.get("handoff") or {}
    if ho.get("status") in ("blocked", "partial"):
        # A run that screened perfectly but failed to deliver its cards has NOT succeeded.
        status = "handoff_blocked" if status == "ok" else status
        summary["totals"]["handoff_status"] = ho.get("status")
        summary["totals"]["handoff_reason"] = ho.get("reason")
    store.finish_run(run_id, status, summary["totals"])
    summary["status"] = status
    return summary
