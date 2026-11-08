"""Tests for the v2 Find -> Qualify contract: suppression, per-county deadlines, portfolios,
identical-assessment clusters, uncertainty, and evidence-quality ranking."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from taxfind.desks.property_tax.florida import filing_window
from taxfind.engine.handoff import RANK_SQL, card_title
from taxfind.engine.people import attach_owners
from taxfind.engine.store import Store


def _roll(names):
    n = len(names)
    return pd.DataFrame({
        "PARCEL_ID": [f"P{i:04d}" for i in range(n)], "OWN_NAME": names,
        "OWN_ADDR1": ["1 MAIN ST"] * n, "OWN_CITY": ["LABELLE"] * n,
        "OWN_STATE": ["FL"] * n, "OWN_ZIPCD": ["33935"] * n,
        "PHY_ADDR1": [f"{i} OAK ST" for i in range(n)], "PHY_ZIPCD": ["33935"] * n,
        "DOR_UC": ["001"] * n,
    })


@pytest.mark.parametrize("name", ["", "   ", "CONFIDENTIAL", "Exempt", "N/A", "WITHHELD", "Not Available"])
def test_unreadable_owner_name_is_suppressed_fail_closed(name):
    out = attach_owners(_roll([name, "QUINN BRIAN"]))
    assert bool(out.owner_suppressed.iloc[0]) is True
    assert "119.071" in out.owner_suppression_reason.iloc[0]
    assert bool(out.owner_suppressed.iloc[1]) is False
    assert out.owner_suppression_reason.iloc[1] == ""


def test_a_real_owner_name_is_not_suppressed():
    out = attach_owners(_roll(["PROGRESS RESIDENTIAL BORROWER 1 LLC", "SMITH JOHN & MARY"]))
    assert out.owner_suppressed.tolist() == [False, False]


def test_verified_county_deadlines_differ_from_each_other_and_from_the_estimate():
    today = dt.date(2026, 6, 1)
    vol = filing_window(2026, today, county="Volusia")
    bro = filing_window(2026, today, county="Broward")
    est = filing_window(2026, today, county="Hendry")
    # counties really do differ: a statewide constant would be wrong for at least one of them
    assert vol["closes"] != bro["closes"]
    assert vol["verified"] is True and vol["source"]
    assert bro["verified"] is True and bro["source"]
    # an unlisted county falls back to an estimate and says so
    assert est["verified"] is False and est["source"] is None
    assert "UNVERIFIED" in est["basis"]
    assert est["closes"] not in (vol["closes"], bro["closes"])


def test_filing_window_status_tracks_the_verified_date():
    assert filing_window(2026, dt.date(2026, 9, 10), county="Volusia")["status"] == "open"
    assert filing_window(2026, dt.date(2026, 9, 12), county="Volusia")["status"] == "closed"
    # Broward is a week later, so the same day is still open there
    assert filing_window(2026, dt.date(2026, 9, 12), county="Broward")["status"] == "open"


def _payload(case, savings, portfolio=None, quality=0.5, parcels=1, name="OWNER A"):
    return {
        "schema_version": 2, "case_id": case, "desk": "property_tax", "status": "candidate", "tier": "strong",
        "jurisdiction": {"state": "FL", "county": "Hendry", "county_code": "36", "tax_year": 2026,
                         "roll_stage": "final", "county_check": {"status": "validated"}},
        "property": {"parcel_id": case, "address": "1 OAK ST", "city": "LABELLE", "use": "single_family",
                     "homestead": False},
        "values": {"just_value": 300000.0, "assessed_value": 300000.0, "taxable_value": 300000.0},
        "signals": {"neighbor_ratio": 1.2, "neighbor_count": 30, "sales_ratio": 1.2, "comp_count": 10},
        "estimate": {"defensible_value": 250000.0, "annual_savings": savings,
                     "annual_savings_range": [round(savings * 0.73), round(savings * 1.47)], "millage": 0.015},
        "confidence": {"evidence_quality": quality, "evidence_label": "moderate"},
        "owner": {"owner_id": "own_x", "name": name, "type": "individual", "flagged_parcels_in_run": parcels,
                  "portfolio_savings_in_run": portfolio if portfolio is not None else savings},
        "portfolio": {"portfolio_id": "own_x", "owner_name": name, "flagged_parcels": parcels,
                      "savings_in_run": portfolio if portfolio is not None else savings,
                      "parcels_in_county": parcels},
        "filing_window": {"closes": "2026-09-09", "status": "closed", "verified": False},
        "source": {"run_id": "r1"},
    }


def test_card_title_carries_the_portfolio_when_an_owner_has_several(tmp_path):
    single = card_title(_payload("FL-36-2026-A", 900))
    assert "flagged parcels" not in single

    many = card_title(_payload("FL-36-2026-B", 758, portfolio=7577, parcels=10, name="QUINN BRIAN"))
    assert "QUINN BRIAN · 10 flagged parcels · est. $7,577/year" in many
    # the individual property is still identifiable, so Qualify can work the case on its own
    assert "1 OAK ST" in many and "FL Hendry 2026" in many


def test_ranking_puts_portfolios_first_then_evidence_over_a_bigger_guess(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    s.upsert_candidates([
        _payload("FL-36-2026-SMALL-GOOD", 600, quality=0.9),   # small but well evidenced
        _payload("FL-36-2026-BIG-THIN", 2000, quality=0.2),    # big but thin
        _payload("FL-36-2026-PORTFOLIO", 758, portfolio=7577, parcels=10, quality=0.5),
    ], "r1")
    order = [p["case_id"] for p in s.iter_payloads(order=RANK_SQL)]
    assert order[0] == "FL-36-2026-PORTFOLIO", "an owner worth $7,577 should outrank a single $2,000 case"
    assert order.index("FL-36-2026-SMALL-GOOD") < order.index("FL-36-2026-BIG-THIN"), \
        "a well-evidenced $600 case should outrank a thin $2,000 one"


def test_savings_are_a_range_not_a_promise():
    p = _payload("FL-36-2026-A", 1000)
    lo, hi = p["estimate"]["annual_savings_range"]
    assert lo < p["estimate"]["annual_savings"] < hi
