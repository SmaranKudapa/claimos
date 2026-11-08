from __future__ import annotations

RETRIEVED = "2026-11-07"

RULES: list[dict] = []


def _norm(county: str | None) -> str:
    return (county or "").strip().lower().replace(" county", "")


def rules_for(county: str | None, appeal_type: str | None) -> list[dict]:
    c = _norm(county)
    return [r for r in RULES if (r["jurisdiction"] == "FL" or _norm(r["jurisdiction"].split(":", 1)[-1]) == c)
            and (not r.get("appeal_types") or appeal_type in r["appeal_types"])]


DEADLINE_KEYS = ("petition_filing", "evidence_exchange_petitioner", "evidence_exchange_appraiser", "hearing_notice",
                 "hearing", "written_decision", "circuit_court")


def deadlines_for(county: str | None, year: int) -> dict:
    out = {}
    for k in DEADLINE_KEYS:
        spec = DEADLINE_SPECS.get(k, {})
        out[k] = {"date": None, "verified": False, "source": spec.get("source"), "rule": spec.get("rule"),
                  "trigger": spec.get("trigger"), "computation": spec.get("computation"), "basis": spec.get("basis")}
    known = COUNTY_DEADLINES.get((_norm(county), year), {})
    for k, v in known.items():
        out[k].update(v)
    return out


DEADLINE_SPECS: dict = {}
COUNTY_DEADLINES: dict = {}
