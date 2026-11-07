"""SQLite store: runs, candidates (upserted by case_id), home-value cache, spend ledger.
One file, no server, safe to copy into an agent sandbox and back."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, state TEXT, scope TEXT,
  status TEXT, stats TEXT
);
CREATE TABLE IF NOT EXISTS candidates (
  case_id TEXT PRIMARY KEY, state TEXT, county_code TEXT, tax_year INTEGER, parcel_id TEXT,
  tier TEXT, avm_check TEXT, annual_savings REAL, owner_id TEXT, payload TEXT,
  first_seen_run TEXT, last_seen_run TEXT, updated_at TEXT, handed_off_at TEXT, handoff_ref TEXT
);
CREATE INDEX IF NOT EXISTS ix_cand_scope ON candidates(state, county_code, tax_year, tier);
CREATE TABLE IF NOT EXISTS avm_cache (
  cache_key TEXT, provider TEXT, fetched_at TEXT, payload TEXT, PRIMARY KEY (cache_key, provider)
);
CREATE TABLE IF NOT EXISTS county_stats (
  run_id TEXT, state TEXT, county_code TEXT, stats TEXT, PRIMARY KEY (run_id, county_code)
);
CREATE INDEX IF NOT EXISTS ix_cand_run ON candidates(last_seen_run);
CREATE TABLE IF NOT EXISTS spend (
  at TEXT, run_id TEXT, provider TEXT, usd REAL, lookups INTEGER, note TEXT
);
"""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # runs
    def start_run(self, run_id: str, state: str, scope: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?)",
                        (run_id, now(), None, state, scope, "running", "{}"))
        self.db.commit()

    def finish_run(self, run_id: str, status: str, stats: dict) -> None:
        self.db.execute("UPDATE runs SET finished_at=?, status=?, stats=? WHERE run_id=?",
                        (now(), status, json.dumps(stats, default=str), run_id))
        self.db.commit()

    def last_runs(self, n: int = 10) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (n,))]

    # candidates
    def upsert_candidates(self, payloads: list[dict], run_id: str) -> dict:
        new = updated = 0
        t = now()
        for p in payloads:
            row = self.db.execute("SELECT case_id FROM candidates WHERE case_id=?", (p["case_id"],)).fetchone()
            vals = (p["jurisdiction"]["state"], p["jurisdiction"]["county_code"], p["jurisdiction"]["tax_year"],
                    p["property"]["parcel_id"], p["tier"], p.get("avm_check"), p["estimate"]["annual_savings"],
                    p["owner"]["owner_id"], json.dumps(p, default=str))
            if row:
                self.db.execute("""UPDATE candidates SET state=?, county_code=?, tax_year=?, parcel_id=?, tier=?,
                    avm_check=?, annual_savings=?, owner_id=?, payload=?, last_seen_run=?, updated_at=? WHERE case_id=?""",
                                (*vals, run_id, t, p["case_id"]))
                updated += 1
            else:
                self.db.execute("""INSERT INTO candidates (state, county_code, tax_year, parcel_id, tier, avm_check,
                    annual_savings, owner_id, payload, case_id, first_seen_run, last_seen_run, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (*vals, p["case_id"], run_id, run_id, t))
                new += 1
        self.db.commit()
        return {"new": new, "updated": updated}

    def candidates(self, where: str = "1=1", params: tuple = (), order: str = "annual_savings DESC",
                   limit: int | None = None) -> list[dict]:
        sql = f"SELECT payload, handed_off_at, handoff_ref FROM candidates WHERE {where} ORDER BY {order}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        out = []
        for r in self.db.execute(sql, params):
            p = json.loads(r["payload"])
            p["_handoff"] = {"at": r["handed_off_at"], "ref": r["handoff_ref"]}
            out.append(p)
        return out

    def get(self, case_id: str) -> dict | None:
        r = self.db.execute("SELECT payload FROM candidates WHERE case_id=?", (case_id,)).fetchone()
        return json.loads(r["payload"]) if r else None

    def iter_payloads(self, where: str = "1=1", params: tuple = (), order: str = "annual_savings DESC"):
        """Stream payloads one at a time (a statewide run is hundreds of thousands of cases)."""
        cur = self.db.cursor()
        for r in cur.execute(f"SELECT payload, handed_off_at, handoff_ref FROM candidates WHERE {where} ORDER BY {order}", params):
            p = json.loads(r[0])
            p["_handoff"] = {"at": r[1], "ref": r[2]}
            yield p

    def save_county_stats(self, run_id: str, state: str, county_code: str, stats: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO county_stats VALUES (?,?,?,?)",
                        (run_id, state, county_code, json.dumps(stats, default=str)))
        self.db.commit()

    def county_stats(self, run_id: str) -> list[dict]:
        return [json.loads(r[0]) for r in self.db.execute("SELECT stats FROM county_stats WHERE run_id=?", (run_id,))]

    def mark_handed_off(self, case_id: str, ref: str) -> None:
        self.db.execute("UPDATE candidates SET handed_off_at=?, handoff_ref=? WHERE case_id=?", (now(), ref, case_id))
        self.db.commit()

    def save_payload(self, p: dict) -> None:
        self.db.execute("UPDATE candidates SET payload=?, avm_check=?, tier=?, updated_at=? WHERE case_id=?",
                        (json.dumps(p, default=str), p.get("avm_check"), p["tier"], now(), p["case_id"]))
        self.db.commit()

    # avm cache + spend
    def avm_get(self, key: str, provider: str, max_age_days: int) -> dict | None:
        r = self.db.execute("SELECT fetched_at, payload FROM avm_cache WHERE cache_key=? AND provider=?",
                            (key, provider)).fetchone()
        if not r:
            return None
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.strptime(r["fetched_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        return json.loads(r["payload"]) if age.days <= max_age_days else None

    def avm_put(self, key: str, provider: str, payload: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO avm_cache VALUES (?,?,?,?)", (key, provider, now(), json.dumps(payload, default=str)))
        self.db.commit()

    def add_spend(self, run_id: str, provider: str, usd: float, lookups: int, note: str = "") -> None:
        self.db.execute("INSERT INTO spend VALUES (?,?,?,?,?,?)", (now(), run_id, provider, usd, lookups, note))
        self.db.commit()

    def spend_total(self, run_id: str | None = None) -> float:
        if run_id:
            r = self.db.execute("SELECT COALESCE(SUM(usd),0) FROM spend WHERE run_id=?", (run_id,)).fetchone()
        else:
            r = self.db.execute("SELECT COALESCE(SUM(usd),0) FROM spend").fetchone()
        return float(r[0])
