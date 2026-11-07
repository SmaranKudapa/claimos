"""Hand candidates to the Qualify desk: files (JSONL + CSV) always, Naive board cards when configured.

A card is idempotent on case_id, so re-running Find never double-posts a property; a changed
estimate updates the store, and Qualify reads the latest payload from the card body or the file.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .naive import NaiveClient
from .store import Store

CSV_COLS = [
    ("case_id", lambda p: p["case_id"]), ("tier", lambda p: p["tier"]), ("avm_check", lambda p: p.get("avm_check")),
    ("county", lambda p: p["jurisdiction"]["county"]), ("tax_year", lambda p: p["jurisdiction"]["tax_year"]),
    ("parcel_id", lambda p: p["property"]["parcel_id"]), ("address", lambda p: p["property"]["address"]),
    ("unit", lambda p: p["property"].get("unit")), ("city", lambda p: p["property"].get("city")),
    ("zip", lambda p: p["property"].get("zip")), ("use", lambda p: p["property"]["use"]),
    ("homestead", lambda p: p["property"]["homestead"]), ("just_value", lambda p: p["values"]["just_value"]),
    ("assessed_value", lambda p: p["values"]["assessed_value"]),
    ("defensible_value", lambda p: p["estimate"]["defensible_value"]),
    ("annual_savings", lambda p: p["estimate"]["annual_savings"]),
    ("neighbor_ratio", lambda p: p["signals"]["neighbor_ratio"]), ("sales_ratio", lambda p: p["signals"]["sales_ratio"]),
    ("avm_ratio", lambda p: p["signals"].get("avm_ratio")),
    ("avm_value", lambda p: (p["signals"].get("avm") or {}).get("value")),
    ("owner_id", lambda p: p["owner"]["owner_id"]), ("owner_name", lambda p: p["owner"]["name"]),
    ("owner_type", lambda p: p["owner"]["type"]), ("owner_flagged_parcels", lambda p: p["owner"]["flagged_parcels_in_run"]),
    ("filing_closes", lambda p: p["filing_window"]["closes"]), ("filing_status", lambda p: p["filing_window"]["status"]),
]


def write_files(payloads, out_dir: Path) -> dict:
    """Streams: `payloads` may be a generator straight from the store."""
    out_dir.mkdir(parents=True, exist_ok=True)
    jl, cs = out_dir / "candidates.jsonl", out_dir / "candidates.csv"
    n = 0
    with open(jl, "w") as fj, open(cs, "w", newline="") as fc:
        w = csv.writer(fc)
        w.writerow([c for c, _ in CSV_COLS])
        for p in payloads:
            fj.write(json.dumps({k: v for k, v in p.items() if not k.startswith("_")}, default=str) + "\n")
            w.writerow([f(p) for _, f in CSV_COLS])
            n += 1
    return {"jsonl": str(jl), "csv": str(cs), "rows": n}


def card_title(p: dict) -> str:
    pr, j = p["property"], p["jurisdiction"]
    unit = f" #{pr['unit']}" if pr.get("unit") else ""
    return (f"{j['state']} {j['county']} {j['tax_year']} · {pr['address']}{unit}, {pr.get('city') or ''}"
            f" · ~${p['estimate']['annual_savings']:,.0f}/yr · {p['tier']}")


def card_body(p: dict) -> str:
    s, e = p["signals"], p["estimate"]
    lines = [
        f"Find flagged this {p['property']['use'].replace('_', ' ')} as possibly over-assessed.",
        f"County value ${p['values']['just_value']:,.0f}; defensible ${e['defensible_value'] or 0:,.0f}; "
        f"est. savings ${e['annual_savings']:,.0f}/yr at {e['millage']:.2%}.",
        f"Neighbors ratio {s['neighbor_ratio'] or 0:.2f} ({s['neighbor_count']} homes); "
        f"sales ratio {s['sales_ratio'] or 0:.2f} ({s['comp_count']} sales); AVM check: {p.get('avm_check')}.",
        f"Owner: {p['owner']['type']}, {p['owner']['flagged_parcels_in_run']} flagged parcel(s) this run. "
        f"Filing window {p['filing_window']['status']} (closes ~{p['filing_window']['closes']}).",
        "", "```json",
        json.dumps({k: v for k, v in p.items() if k not in ("evidence",) and not k.startswith("_")}, default=str),
        "```",
    ]
    return "\n".join(lines)


def post_cards(store: Store, client: NaiveClient, board: str | None, assignee: str | None, max_cards: int,
               tiers=("strong", "possible"), include_closed: bool = False, where: str = "1=1", params: tuple = ()) -> dict:
    """Post the most valuable cases not yet handed off. Held: counties whose self-check is weak, and
    (unless include_closed) cases whose filing window has closed. Selection happens in SQL."""
    if not board:
        return {"posted": 0, "skipped": "NAIVE_QUALIFY_BOARD not set"}
    tier_sql = f"tier IN ({','.join('?' * len(tiers))})"
    weak = "COALESCE(json_extract(payload,'$.jurisdiction.county_check.status'),'') = 'weak'"
    closed = "COALESCE(json_extract(payload,'$.filing_window.status'),'') = 'closed'"
    base = f"({where}) AND {tier_sql}"
    count = lambda cond: store.db.execute(f"SELECT COUNT(*) FROM candidates WHERE {base} AND {cond}",  # noqa: E731
                                          (*params, *tiers)).fetchone()[0]
    held_weak = count(weak)
    held_closed = 0 if include_closed else count(f"NOT {weak} AND {closed}")
    held_counties = [r[0] for r in store.db.execute(
        f"SELECT DISTINCT json_extract(payload,'$.jurisdiction.county') FROM candidates WHERE {base} AND {weak}",
        (*params, *tiers))]
    elig = f"{base} AND handoff_ref IS NULL AND NOT {weak}" + ("" if include_closed else f" AND NOT {closed}")
    remaining = store.db.execute(f"SELECT COUNT(*) FROM candidates WHERE {elig}", (*params, *tiers)).fetchone()[0]
    todo = [p for _, p in zip(range(max_cards), store.iter_payloads(elig, (*params, *tiers)))]
    posted, errors = 0, []
    for p in todo:
        try:
            res = client.create_card(board, card_title(p), card_body(p), key=p["case_id"], assignee=assignee)
            if client.live:
                store.mark_handed_off(p["case_id"], res.get("id", ""))
            posted += 1
        except Exception as e:
            errors.append(f"{p['case_id']}: {str(e)[:160]}")
            if len(errors) >= 5:
                break
    return {"posted": posted, "live": client.live, "remaining": max(0, remaining - posted), "errors": errors,
            "held_weak_county": held_weak, "held_window_closed": held_closed, "held_counties": sorted(filter(None, held_counties))}
