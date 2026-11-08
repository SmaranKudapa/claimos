"""Hand candidates to the Qualify desk: files (JSONL + CSV) always, Naive board cards when configured.

Delivery rules (v2):
  * A card is idempotent on case_id, so re-running Find never double-posts a property.
  * Delivery is only counted when the board acknowledges it with a real card id. A dry-run id
    (no NAIVE_API_KEY) is NOT a delivery: the run reports status "blocked" and writes the
    undelivered payloads to a retry file. Find never reports silent success.
  * Ranking is portfolio-first: an owner with ten flagged parcels outranks a single better house,
    but a speculative estimate does not outrank a well-evidenced one (see rank_sql).
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
    ("savings_low", lambda p: (p["estimate"].get("annual_savings_range") or [None, None])[0]),
    ("savings_high", lambda p: (p["estimate"].get("annual_savings_range") or [None, None])[1]),
    ("evidence_quality", lambda p: (p.get("confidence") or {}).get("evidence_quality")),
    ("neighbor_ratio", lambda p: p["signals"]["neighbor_ratio"]), ("sales_ratio", lambda p: p["signals"]["sales_ratio"]),
    ("avm_ratio", lambda p: p["signals"].get("avm_ratio")),
    ("avm_value", lambda p: (p["signals"].get("avm") or {}).get("value")),
    ("owner_id", lambda p: p["owner"]["owner_id"]), ("owner_name", lambda p: p["owner"]["name"]),
    ("owner_type", lambda p: p["owner"]["type"]),
    ("portfolio_id", lambda p: (p.get("portfolio") or {}).get("portfolio_id")),
    ("owner_flagged_parcels", lambda p: p["owner"]["flagged_parcels_in_run"]),
    ("portfolio_savings", lambda p: (p.get("portfolio") or {}).get("savings_in_run")),
    ("identical_assessment_cluster", lambda p: (p.get("flags") or {}).get("identical_assessment_cluster")),
    ("filing_closes", lambda p: p["filing_window"]["closes"]),
    ("filing_status", lambda p: p["filing_window"]["status"]),
    ("filing_verified", lambda p: p["filing_window"].get("verified")),
    ("outreach_eligible", lambda p: (p.get("outreach") or {}).get("eligible")),
]

# Risk-adjusted value: what the opportunity is worth, discounted by how well it is evidenced.
# Ranking on value alone lets a large speculative estimate outrank a smaller, well-supported one;
# ranking on evidence alone buries the money. The product does neither. Portfolio value is used
# where an owner has several flagged parcels, so one owner worth $7,577 outranks one house
# worth $2,000. Ties fall back to raw value.
_VALUE = "COALESCE(json_extract(payload,'$.portfolio.savings_in_run'), annual_savings)"
_QUALITY = "COALESCE(json_extract(payload,'$.confidence.evidence_quality'), 0.1)"
RANK_SQL = f"({_VALUE} * {_QUALITY}) DESC, {_VALUE} DESC, annual_savings DESC"


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
    base = (f"{j['state']} {j['county']} {j['tax_year']} · {pr['address']}{unit}, {pr.get('city') or ''}"
            f" · ~${p['estimate']['annual_savings']:,.0f}/yr · {p['tier']}")
    pf = p.get("portfolio") or {}
    if (pf.get("flagged_parcels") or 0) > 1:
        # Owner name · 10 flagged parcels · estimated $7,577/year
        base = (f"{pf.get('owner_name') or p['owner']['name']} · {pf['flagged_parcels']} flagged parcels"
                f" · est. ${pf.get('savings_in_run') or 0:,.0f}/year — {base}")
    return base


# Fields a compact card carries. Everything Qualify needs to triage, nothing it can fetch later.
COMPACT_FIELDS = (
    ("case_id",), ("tier",), ("status",), ("jurisdiction", "county"), ("jurisdiction", "county_check", "status"),
    ("property", "parcel_id"), ("property", "address"), ("property", "unit"), ("property", "city"),
    ("property", "use"), ("property", "homestead"),
    ("values", "just_value"), ("values", "assessed_value"), ("values", "taxable_value"),
    ("estimate", "defensible_value"), ("estimate", "annual_savings"), ("estimate", "annual_savings_range"),
    ("confidence", "evidence_quality"), ("confidence", "evidence_label"),
    ("portfolio", "portfolio_id"), ("portfolio", "flagged_parcels"), ("portfolio", "savings_in_run"),
    ("flags", "identical_assessment_cluster"),
    ("owner", "name"), ("owner", "may_have_changed"),
    ("filing_window", "closes"), ("filing_window", "status"), ("filing_window", "verified"),
    ("outreach", "eligible"), ("outreach", "blocked_by"), ("outreach", "owner_suppressed"),
    ("source", "run_id"),
)


def compact_payload(p: dict) -> dict:
    out: dict = {"schema_version": p.get("schema_version")}
    for path in COMPACT_FIELDS:
        v = p
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
        if v is None:
            continue
        d = out
        for k in path[:-1]:
            d = d.setdefault(k, {})
        d[path[-1]] = v
    out["full_record"] = {"run_id": (p.get("source") or {}).get("run_id"), "file": "candidates.jsonl",
                          "key": "case_id",
                          "note": "The complete payload (evidence, assumptions, provenance) is in the run's "
                                  "candidates.jsonl, published by Find. Look it up by case_id."}
    return out


def card_body(p: dict, compact: bool = False) -> str:
    """Card text for the Qualify board.

    compact=False embeds the whole payload, which is right when the program posts cards over the API.
    compact=True keeps the same human summary but embeds only the triage fields plus a pointer to the
    full record. Use it when an agent posts cards with board_write: a full body is ~7.5 KB, and an agent
    has to read and re-type every byte, so 200 full cards is ~1.5 MB of text and can exhaust it.
    """
    s, e = p["signals"], p["estimate"]
    conf = p.get("confidence") or {}
    rng = e.get("annual_savings_range") or [None, None]
    pf = p.get("portfolio") or {}
    lines = [
        f"Find flagged this {p['property']['use'].replace('_', ' ')} as possibly over-assessed.",
        p.get("explanation") or "",
        f"County value ${p['values']['just_value']:,.0f}; defensible ${e['defensible_value'] or 0:,.0f}; "
        f"est. savings ${e['annual_savings']:,.0f}/yr"
        + (f" (range ${rng[0]:,.0f}–${rng[1]:,.0f})" if rng[0] is not None else "")
        + f" at an assumed {e['millage']:.2%}.",
        f"Neighbors ratio {s['neighbor_ratio'] or 0:.2f} ({s['neighbor_count']} homes); "
        f"sales ratio {s['sales_ratio'] or 0:.2f} ({s['comp_count']} sales); AVM check: {p.get('avm_check')}.",
        f"Evidence quality {conf.get('evidence_quality', 0):.2f} ({conf.get('evidence_label', 'unrated')}); "
        f"county self-check: {p['jurisdiction'].get('county_check', {}).get('status')}.",
    ]
    if (pf.get("flagged_parcels") or 0) > 1:
        lines.append(f"Portfolio {pf.get('portfolio_id')}: {pf['flagged_parcels']} flagged of "
                     f"{pf.get('parcels_in_county')} owned in county, est. ${pf.get('savings_in_run') or 0:,.0f}/yr total.")
    if (p.get("flags") or {}).get("identical_assessment_cluster"):
        lines.append(f"NOTE: {p['flags']['identical_assessment_cluster']} parcels share this owner, this peer group "
                     f"and an identical county value. Separate properties assessed identically, not duplicates.")
    if p.get("warnings"):
        lines.append("Warnings: " + "; ".join(p["warnings"]))
    if p.get("needs_verification"):
        lines.append("Qualify must verify: " + "; ".join(p["needs_verification"]))
    lines += [
        f"Filing window {p['filing_window']['status']} (closes ~{p['filing_window']['closes']}, "
        f"verified={p['filing_window'].get('verified')}).",
        "", "```json",
        json.dumps(compact_payload(p) if compact else
                   {k: v for k, v in p.items() if k not in ("evidence",) and not k.startswith("_")}, default=str),
        "```",
    ]
    return "\n".join(x for x in lines if x)


def _retry_file(store: Store, run_tag: str) -> Path:
    d = Path(store.path).parent / "undelivered"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{run_tag}.jsonl"


def post_cards(store: Store, client: NaiveClient, board: str | None, assignee: str | None, max_cards: int,
               tiers=("strong", "possible"), include_closed: bool = False, where: str = "1=1", params: tuple = (),
               run_tag: str = "backlog") -> dict:
    """Post the most valuable cases not yet handed off, portfolio-first.

    Held back: counties whose self-check is weak, and (unless include_closed) cases whose filing
    window has closed. Selection happens in SQL.

    Returns a dict whose `status` is one of:
      delivered  every eligible card in this batch was acknowledged by the board
      partial    some were acknowledged, some failed (see `errors`)
      blocked    nothing was delivered because of missing config or credentials
      empty      nothing was eligible to send
    """
    if not board:
        return {"status": "blocked", "blocked_by": "config", "posted": 0, "delivered": 0, "live": client.live,
                "reason": "NAIVE_QUALIFY_BOARD is not set, so there is no destination board. No cards were delivered."}

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
    held = {"held_weak_county": held_weak, "held_window_closed": held_closed,
            "held_counties": sorted(filter(None, held_counties))}

    # Credentials missing: do not pretend. Preserve the batch so it can be retried verbatim.
    if not client.live:
        todo = [p for _, p in zip(range(max_cards), store.iter_payloads(elig, (*params, *tiers), order=RANK_SQL))]
        path = _retry_file(store, run_tag)
        with open(path, "w") as fh:
            for p in todo:
                fh.write(json.dumps({k: v for k, v in p.items() if not k.startswith("_")}, default=str) + "\n")
        return {"status": "blocked", "blocked_by": "credentials", "posted": 0, "delivered": 0, "live": False,
                "undelivered": len(todo), "retry_file": str(path), "remaining": remaining,
                "reason": ("NAIVE_API_KEY is not set, so the board was never called and NO cards were delivered. "
                           f"{len(todo)} payload(s) were written to {path} and can be retried once a key is in place "
                           "(taxfind handoff)."), **held}

    todo = [p for _, p in zip(range(max_cards), store.iter_payloads(elig, (*params, *tiers), order=RANK_SQL))]
    if not todo:
        return {"status": "empty", "posted": 0, "delivered": 0, "live": True, "remaining": remaining,
                "reason": "No eligible cases were waiting to be handed off.", **held}

    delivered, errors, undelivered = 0, [], []
    for p in todo:
        try:
            res = client.create_card(board, card_title(p), card_body(p), key=p["case_id"], assignee=assignee)
            ref = str((res or {}).get("id") or "")
            card = (res or {}).get("card") or {}
            ref = ref or str(card.get("id") or "")
            if not ref or ref.startswith("dry_"):
                raise RuntimeError(f"board did not acknowledge the card (no usable id in response: {str(res)[:120]})")
            store.mark_handed_off(p["case_id"], ref)
            delivered += 1
        except Exception as e:
            undelivered.append(p)
            errors.append(f"{p['case_id']}: {str(e)[:160]}")
            if len(errors) >= 5:
                break

    out = {"posted": delivered, "delivered": delivered, "live": True,
           "attempted": len(todo), "remaining": max(0, remaining - delivered), "errors": errors, **held}
    if undelivered:
        path = _retry_file(store, run_tag)
        with open(path, "w") as fh:
            for p in undelivered:
                fh.write(json.dumps({k: v for k, v in p.items() if not k.startswith("_")}, default=str) + "\n")
        out["undelivered"] = len(undelivered)
        out["retry_file"] = str(path)
        out["status"] = "partial" if delivered else "blocked"
        out.setdefault("blocked_by", "delivery_errors")
        out["reason"] = f"{len(undelivered)} card(s) were not acknowledged by the board; preserved at {path}."
    else:
        out["status"] = "delivered"
    return out
