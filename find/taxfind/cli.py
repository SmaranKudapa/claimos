"""Command line. `taxfind --help` for everything; the agent on Naive calls `taxfind watch --once`."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

from .config import Settings


def _settings(a) -> Settings:
    s = Settings()
    if getattr(a, "data_dir", None):
        s.data_dir = Path(a.data_dir).resolve()
    if getattr(a, "dry_run", False):
        s.dry_run = True
    if getattr(a, "avm_providers", None):
        s.avm_providers = a.avm_providers.split(",")
    if getattr(a, "avm_budget", None) is not None:
        s.avm_budget_usd = a.avm_budget
    if getattr(a, "include_closed", False):
        s.handoff_include_closed = True
    return s.ensure()


def cmd_sources(a) -> int:
    from .desks.property_tax import florida
    from .engine.ingest import HttpCache
    s = _settings(a)
    pairs = florida.discover(HttpCache(s.cache_dir / "http"), a.year)
    rows = sorted(pairs.values(), key=lambda p: p["NAL"].county)
    for p in rows:
        n = p["NAL"]
        print(f"{n.county_no}  {n.county:<14} {n.year} {n.stage:<11} roll {n.size/1e6:6.1f} MB  sales {p['SDF'].size/1e6:5.1f} MB  posted {n.modified[:10]}")
    print(f"{len(rows)} counties")
    return 0


def _counties(v: str):
    return "all" if v.strip().lower() == "all" else [c.strip() for c in v.split(",") if c.strip()]


def cmd_run(a) -> int:
    from .pipeline import run
    s = _settings(a)
    today = dt.date.fromisoformat(a.today) if a.today else None
    summary = run(s, a.state, _counties(a.counties), a.year, avm=not a.no_avm, max_avm=a.max_avm,
                  handoff=a.handoff, only_changed=a.only_changed, today=today)
    t = summary["totals"]
    print(json.dumps({"run_id": summary["run_id"], "totals": t, "files": summary["files"],
                      "handoff": summary.get("handoff"), "errors": [e["county"] + ": " + e["error"] for e in summary["errors"]]},
                     indent=1, default=str))
    return 0 if not summary["errors"] else (2 if summary["counties"] else 1)


def cmd_watch(a) -> int:
    """Autonomous mode: re-check the state's portal, run only counties whose files changed, hand off."""
    from .pipeline import run
    s = _settings(a)
    handoff = a.handoff or ("board" if s.naive_board else "file")
    while True:
        summary = run(s, a.state, "all", None, avm=not a.no_avm, max_avm=a.max_avm, handoff=handoff, only_changed=True)
        print(json.dumps({"run_id": summary["run_id"], "totals": summary["totals"], "handoff": summary.get("handoff")}, default=str))
        if a.once:
            return 0 if not summary["errors"] else 2
        time.sleep(a.interval_min * 60)


def cmd_upload(a) -> int:
    from .desks.property_tax import florida
    from .desks.property_tax.florida.source import load_pair
    from .desks.property_tax.screen import screen
    from .engine.ingest import HttpCache
    from .engine.uploads import parse_and_match
    from .pipeline import select
    s = _settings(a)
    cache = HttpCache(s.cache_dir / "http")
    pairs = select(florida.discover(cache, a.year), [a.county])
    if not pairs:
        print(f"no roll found for county {a.county}", file=sys.stderr)
        return 1
    pair = next(iter(pairs.values()))
    work = s.cache_dir / "fl"
    work.mkdir(parents=True, exist_ok=True)
    nal, sdf, _ = load_pair(cache, pair, work)
    matched = parse_and_match(Path(a.file), nal)
    cols = ["PARCEL_ID", "PHY_ADDR1", "PHY_CITY", "tier", "scored", "est_savings", "JV", "defensible_value",
            "neighbor_ratio", "sales_ratio"]
    import pandas as pd
    from .engine.store import Store
    nal_f = pair["NAL"]
    shot = s.data_dir / "screens" / f"FL_{nal_f.county_no}_{nal_f.year}.parquet"
    if shot.exists() and not a.rescreen:
        # county already screened: every home's tier is saved; flagged homes have full detail in the store
        sc = pd.read_parquet(shot).set_index("PARCEL_ID")
        st = Store(s.db_path)
        stored = {p["property"]["parcel_id"]: p for p in st.candidates("state='FL' AND county_code=? AND tax_year=?",
                                                                     (nal_f.county_no, nal_f.year))}
        rows = []
        for pid in matched.parcel_id.dropna().unique():
            n = nal.loc[nal.PARCEL_ID == pid].iloc[0]
            p = stored.get(pid)
            hit = pid in sc.index
            rows.append({"PARCEL_ID": pid, "PHY_ADDR1": n.PHY_ADDR1, "PHY_CITY": n.PHY_CITY,
                         "tier": p["tier"] if p else (sc.at[pid, "tier"] if hit else None),
                         "scored": bool(sc.at[pid, "scored"]) if hit else False,
                         "est_savings": p["estimate"]["annual_savings"] if p else 0.0, "JV": n.JV,
                         "defensible_value": p["estimate"]["defensible_value"] if p else None,
                         "neighbor_ratio": p["signals"]["neighbor_ratio"] if p else None,
                         "sales_ratio": p["signals"]["sales_ratio"] if p else None})
        r = pd.DataFrame(rows, columns=cols)
    else:
        r, _ = screen(nal, sdf, pair["NAL"].year, s.screen)
        r["scored"] = r.peer_ppsf.notna() & r.comp_ppsf.notna()
    out = matched.merge(r[cols], left_on="parcel_id", right_on="PARCEL_ID", how="left")
    out["result"] = out.apply(lambda x: ("no parcel match" if not isinstance(x.parcel_id, str) else
                                         "not a house/condo we screen" if not isinstance(x.tier, str) else
                                         "likely over-assessed" if x.tier in ("strong", "possible") else
                                         "needs a human look" if x.tier in ("review", "new_build") else
                                         "over-assessed, but the cap or exemptions absorb it" if x.tier == "cap_absorbs" else
                                         "no case found" if x.scored is True else
                                         "not scored (too few similar homes or sales nearby)"), axis=1)
    dest = Path(a.out or (Path(a.file).with_suffix("").as_posix() + "_matched.csv"))
    out.drop(columns=["PARCEL_ID"]).to_csv(dest, index=False)
    print(out.result.value_counts().to_string())
    print(f"wrote {dest}")
    return 0


def cmd_export(a) -> int:
    from .engine.handoff import write_files
    from .engine.store import Store
    s = _settings(a)
    st = Store(s.db_path)
    if a.tiers.strip() == "all":
        q, params = "1=1", ()
    else:
        tiers = tuple(t.strip() for t in a.tiers.split(","))
        q = f"tier IN ({','.join('?' * len(tiers))})"
        params = tiers
    if a.run:
        q += " AND last_seen_run=?"
        params += (a.run,)
    rows = st.iter_payloads(q, params)
    if a.limit:
        import itertools
        rows = itertools.islice(rows, a.limit)
    print(json.dumps(write_files(rows, Path(a.out)), indent=1))
    return 0


def cmd_handoff(a) -> int:
    """Post the backlog: eligible cases from any run that have not been handed off yet."""
    from .engine.handoff import post_cards
    from .engine.naive import NaiveClient
    from .engine.store import Store
    s = _settings(a)
    st = Store(s.db_path)
    c = NaiveClient(s.naive_api_key, s.naive_base_url, dry_run=s.dry_run, outbox=s.data_dir / "naive_outbox.jsonl")
    where, params = ("county_code=?", (a.county_code,)) if a.county_code else ("1=1", ())
    print(json.dumps(post_cards(st, c, s.naive_board, s.naive_qualify_agent, a.max or s.handoff_max_cards,
                                include_closed=s.handoff_include_closed, where=where, params=params), indent=1))
    return 0


def cmd_status(a) -> int:
    from .engine.store import Store
    s = _settings(a)
    st = Store(s.db_path)
    for r in st.last_runs(a.n):
        print(f"{r['run_id']}  {r['status']:<8} {r['scope']:<20} {r['stats']}")
    print(f"AVM spend to date: ${st.spend_total():.2f}")
    return 0


def cmd_naive_tools(a) -> int:
    from .engine.naive import NaiveClient
    s = _settings(a)
    c = NaiveClient(s.naive_api_key, s.naive_base_url)
    if not c.live:
        print("NAIVE_API_KEY is not set", file=sys.stderr)
        return 1
    if a.tool:
        print(json.dumps(c.data_tool(a.tool), indent=1))
        return 0
    for t in c.search_data_tools(a.query, a.domain or None, a.limit):
        print(f"{t['id']:<40} {t['price']['text']:<22} {t['name']} — {t['description'][:90]}")
    return 0


def cmd_calendar(a) -> int:
    from .desks.property_tax.jurisdictions import calendar
    print(calendar(("live", "next", "partner", "later") if a.all else ("live", "next", "partner")))
    return 0


def cmd_schema(a) -> int:
    from .schema import CANDIDATE_JSON_SCHEMA
    print(json.dumps(CANDIDATE_JSON_SCHEMA, indent=1))
    return 0


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env support (KEY=VALUE lines); real environment variables win."""
    import os
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        if v and k.strip() not in os.environ:
            os.environ[k.strip()] = v


def main(argv=None) -> int:
    _load_dotenv()
    ap = argparse.ArgumentParser(prog="taxfind", description="Find step: detect over-assessed homes from public rolls.")
    ap.add_argument("--data-dir", help="where cache, database and outputs live (default ./data or FIND_DATA_DIR)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sources", help="list county rolls available from the state")
    p.add_argument("--state", default="FL"); p.add_argument("--year", type=int)
    p.set_defaults(fn=cmd_sources)

    def common(p):
        p.add_argument("--state", default="FL")
        p.add_argument("--no-avm", action="store_true", help="skip the Zillow/Redfin/Naive second opinion")
        p.add_argument("--max-avm", type=int, help="max homes to look up per county (default FIND_AVM_MAX_LOOKUPS)")
        p.add_argument("--avm-providers", help="comma list, in order: naive,apify_zillow,apify_redfin,mock")
        p.add_argument("--avm-budget", type=float, help="USD cap for lookups per run")
        p.add_argument("--dry-run", action="store_true", help="record Naive calls to data/naive_outbox.jsonl instead of sending")
        p.add_argument("--include-closed", action="store_true",
                       help="post cards even when the filing window has closed (demos; normally held)")

    p = sub.add_parser("run", help="one Find cycle over some or all counties")
    common(p)
    p.add_argument("--counties", default="all", help="comma list of names or DOR numbers, or 'all'")
    p.add_argument("--year", type=int)
    p.add_argument("--handoff", choices=["file", "board", "none"], default="file")
    p.add_argument("--only-changed", action="store_true")
    p.add_argument("--today", help="pretend date (YYYY-MM-DD) for filing-window status")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("watch", help="autonomous: rerun whenever a county posts new files")
    common(p)
    p.add_argument("--once", action="store_true", help="one pass then exit (for cron / Naive deployments)")
    p.add_argument("--interval-min", type=int, default=360)
    p.add_argument("--handoff", choices=["file", "board", "none"])
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("upload", help="match an uploaded list or document to parcels and say who has a case")
    p.add_argument("file"); p.add_argument("--county", required=True); p.add_argument("--year", type=int)
    p.add_argument("--out")
    p.add_argument("--rescreen", action="store_true", help="screen the county again instead of using stored results")
    p.set_defaults(fn=cmd_upload)

    p = sub.add_parser("export", help="write candidates from the database to JSONL + CSV")
    p.add_argument("--run"); p.add_argument("--tiers", default="strong,possible"); p.add_argument("--limit", type=int)
    p.add_argument("--out", default="./export")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("handoff", help="post not-yet-handed-off cases to the Qualify board (backlog)")
    p.add_argument("--max", type=int); p.add_argument("--county-code", help="DOR county number, e.g. 46")
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--include-closed", action="store_true")
    p.set_defaults(fn=cmd_handoff)

    p = sub.add_parser("status", help="recent runs and spend")
    p.add_argument("-n", type=int, default=10)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("naive-tools", help="search the Naive data catalogue (pick the home-value tool)")
    p.add_argument("--query", default="home value estimate by address"); p.add_argument("--domain", default="real_estate")
    p.add_argument("--limit", type=int, default=20); p.add_argument("--tool", help="show one tool's input schema")
    p.set_defaults(fn=cmd_naive_tools)

    p = sub.add_parser("calendar", help="which jurisdictions have a filing window open in which month")
    p.add_argument("--all", action="store_true", help="include 'later' jurisdictions")
    p.set_defaults(fn=cmd_calendar)

    p = sub.add_parser("schema", help="print the Find -> Qualify JSON schema")
    p.set_defaults(fn=cmd_schema)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
