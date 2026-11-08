import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from taxfind.avm.enrich import enrich
from taxfind.avm.providers import Lookup, Mock, Provider, RedfinApify, ZillowApify, _match, money
from taxfind.config import Settings
from taxfind.engine.handoff import card_title, post_cards, write_files
from taxfind.engine.ingest import safe_extract
from taxfind.engine.naive import NaiveClient
from taxfind.engine.store import Store
from taxfind.engine.uploads import ParcelMatcher, map_headers, parse_and_match


class FakeBoard(NaiveClient):
    """A live client whose board acknowledges every card with a real id."""

    def __init__(self, ack=True, **kw):
        super().__init__("k_test", **kw)
        self.ack, self.calls = ack, []

    def _call(self, method, path, query=None, body=None, idem=None):
        self.calls.append({"method": method, "path": path, "body": body, "idem": idem})
        return {"id": f"crd_{len(self.calls):04d}"} if self.ack else {"ok": True}



def payload(parcel="P1", tier="strong", savings=900.0, address="100 PALM ST", zip_="33900", unit=None, use="single_family",
            jv=400000.0, level=0.85):
    return {"schema_version": 1, "case_id": f"FL-99-2026-{parcel}", "desk": "property_tax",
            "jurisdiction": {"state": "FL", "county": "Test", "county_code": "99", "tax_year": 2026, "roll_stage": "final"},
            "property": {"parcel_id": parcel, "address": address, "unit": unit, "city": "TESTVILLE", "zip": zip_, "use": use,
                         "sqft": 2000.0, "homestead": False},
            "values": {"just_value": jv, "assessed_value": jv, "taxable_value": jv, "land_value": 50000.0},
            "signals": {"neighbor_ratio": 1.3, "neighbor_count": 20, "sales_ratio": 1.25, "comp_count": 9,
                        "own_sale_ratio": None, "avm_ratio": None, "avm": None, "county_level": level},
            "estimate": {"defensible_value": 330000.0, "value_cut": 70000.0, "taxable_cut": 70000.0,
                         "annual_savings": savings, "millage": 0.015, "millage_source": "assumed"},
            "tier": tier, "avm_check": "not_checked",
            "owner": {"owner_id": "own_1", "name": "X", "type": "individual", "mailing_address": {}, "absentee": False,
                      "out_of_state": False, "parcels_in_county": 1, "flagged_parcels_in_run": 1, "portfolio_savings_in_run": savings},
            "evidence": {"neighbors": [], "sales": []},
            "filing_window": {"opens": "2027-08-15", "closes": "2027-09-09", "status": "upcoming", "basis": "estimate"},
            "source": {"roll_file": "u", "sales_file": "u", "run_id": "r", "found_at": "t"}}


# ---------------- ingest ----------------
def test_safe_extract_blocks_traversal(tmp_path):
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../../evil.csv", "x")
        zf.writestr("ok/data.csv", "a,b\n1,2\n")
        zf.writestr("run.sh", "rm -rf /")
    got = safe_extract(z, tmp_path / "out")
    assert [p.name for p in got] == ["evil.csv", "data.csv"]     # flattened into out/, script skipped
    assert all((tmp_path / "out") in p.parents for p in got)
    assert not (tmp_path.parent / "evil.csv").exists()


# ---------------- uploads ----------------
def roll_df():
    return pd.DataFrame({"PARCEL_ID": ["264521230000B2030", "264521230000B2050", "C1", "C2"],
                         "ALT_KEY": ["10234567", None, None, None],
                         "PHY_ADDR1": ["4012 SW 17TH AVE", "4016 SW 17TH AVE", "500 BEACH BLVD", "500 BEACH BLVD"],
                         "PHY_ADDR2": [None, None, "UNIT 101", "UNIT 102"],
                         "PHY_ZIPCD": ["33914", "33914", "33900", "33900"]})


def test_header_mapping():
    m = map_headers(["Folio", "Property Address", "Zip Code", "Owner Name", "E-mail"])
    assert m == {"parcel_id": "Folio", "address": "Property Address", "zip": "Zip Code", "owner": "Owner Name", "email": "E-mail"}


def test_matcher_methods():
    m = ParcelMatcher(roll_df())
    assert m.match(parcel_id="26-4521-23-0000B.2030")["method"] == "parcel_id"
    assert m.match(parcel_id="10234567")["parcel_id"] == "264521230000B2030"            # alt key
    assert m.match(address="4012 S.W. 17th Avenue", zip_code="33914")["method"] == "address+zip"
    assert m.match(address="4012 SW 17TH AVENU", zip_code="33914")["method"] == "fuzzy_in_zip"
    assert m.match(address="500 Beach Blvd Unit 102", zip_code="33900")["parcel_id"] == "C2"
    assert m.match(address="500 Beach Blvd", zip_code="33900")["method"] == "ambiguous"
    assert m.match(address="1 Nowhere Rd", zip_code="33900")["method"] == "unmatched"


def test_parse_csv_and_text(tmp_path):
    f = tmp_path / "leads.csv"
    f.write_text("Owner,Property Address,Zip\nJane,4016 SW 17th Ave,33914\nBob,9 Elsewhere Ln,33914\n")
    out = parse_and_match(f, roll_df())
    assert list(out.method) == ["address+zip", "unmatched"]
    t = tmp_path / "trim.txt"
    t.write_text("NOTICE OF PROPOSED PROPERTY TAXES\nParcel: 26-45-21-23-0000B.2050\nsome text\n")
    out = parse_and_match(t, roll_df())
    assert list(out.parcel_id) == ["264521230000B2050"]


def test_parse_xlsx(tmp_path):
    f = tmp_path / "leads.xlsx"
    pd.DataFrame({"Parcel Number": ["264521230000B2030"], "Address": [""]}).to_excel(f, index=False)
    assert parse_and_match(f, roll_df()).parcel_id.tolist() == ["264521230000B2030"]


# ---------------- avm ----------------
def test_money_parsing():
    assert money("$186,177 (+$16K since last sold)") == 186177
    assert money("$1.2M") == 1_200_000 and money(450000) == 450000 and money(None) is None and money(0) is None


def test_zillow_and_redfin_parsers():
    z = ZillowApify.parse({"zestimate": 412000, "livingArea": 1850, "yearBuilt": 1999, "hdpUrl": "/homedetails/x_zpid/",
                           "priceHistory": [{"event": "Sold", "price": 395000, "date": "2025-04-02"}]})
    assert z.value == 412000 and z.sqft == 1850 and z.last_sold_price == 395000 and z.url.startswith("https://www.zillow.com")
    r = RedfinApify.parse({"avmInfo": {"sectionPreviewText": "$186,177 (+$16K since last sold)"},
                           "addressSectionInfo": {"sqFt": {"value": 1171}, "beds": 3, "yearBuilt": 1958},
                           "mainHouseInfo": {"url": "/AL/Huntsville/x/home/1"}})
    assert r.value == 186177 and r.sqft == 1171 and r.url.startswith("https://www.redfin.com")


def test_match_rows_back_to_lookups():
    lks = [Lookup("100 PALM ST|33900|", "100 Palm St, Testville, FL 33900"),
           Lookup("500 BEACH BLVD|33900|101", "500 Beach Blvd #101, Testville, FL 33900", unit="101")]
    items = [{"streetAddress": "500 Beach Blvd Unit 102", "zipcode": "33900", "zestimate": 1},
             {"streetAddress": "500 Beach Blvd Unit 101", "zipcode": "33900", "zestimate": 2},
             {"address": {"streetAddress": "100 Palm St", "city": "Testville", "state": "FL", "zipcode": "33900"}, "zestimate": 3}]
    got = _match(items, lks)
    assert got["500 BEACH BLVD|33900|101"]["zestimate"] == 2 and got["100 PALM ST|33900|"]["zestimate"] == 3


class Fixed(Provider):
    name, cost_per_lookup = "fixed", 0.01

    def __init__(self, values):
        self.values, self.calls = values, 0

    def estimate(self, lookups):
        from taxfind.avm.providers import Estimate
        self.calls += len(lookups)
        return {lk.key: Estimate("fixed", self.values[lk.key.split("|")[0]]) for lk in lookups if lk.key.split("|")[0] in self.values}


def test_enrich_confirms_disputes_caches_and_budgets(tmp_path):
    s = Settings(); s.data_dir = tmp_path; s.ensure(); s.avm_budget_usd = 1.0
    store = Store(s.db_path)
    pl = [payload("A", address="1 A ST", jv=400000), payload("B", address="2 B ST", jv=400000),
          payload("C", address="3 C ST", use="condo"), payload("D", address="4 D ST", tier="none")]
    prov = Fixed({"1 A ST": 300000, "2 B ST": 600000})           # A: county 57% above AVM*level; B: below
    st = enrich(pl, s, store, "r1", NaiveClient(None), providers=[prov])
    by = {p["property"]["parcel_id"]: p for p in pl}
    assert by["A"]["avm_check"] == "confirmed" and by["A"]["tier"] == "strong"
    assert by["B"]["avm_check"] == "disputed" and by["B"]["tier"] == "review"
    assert by["C"]["avm_check"] == "no_unit" and by["D"]["avm_check"] == "not_checked"
    assert st["looked_up"] == 2 and prov.calls == 2
    pl2 = [payload("A", address="1 A ST")]
    st2 = enrich(pl2, s, store, "r2", NaiveClient(None), providers=[prov])
    assert st2["from_cache"] == 1 and prov.calls == 2              # cached, no new spend
    s.avm_budget_usd = 0.005
    st3 = enrich([payload("E", address="5 E ST")], s, store, "r3", NaiveClient(None), providers=[prov])
    assert st3.get("stopped_on_budget") and st3["looked_up"] == 0


def test_mock_provider_is_labelled():
    p = payload("A")
    est = Mock({"100 PALM ST|33900|": p}).estimate([Lookup("100 PALM ST|33900|", "q")])
    assert est["100 PALM ST|33900|"].provider == "mock"


# ---------------- handoff + naive ----------------
def test_files_and_cards_dry_run(tmp_path):
    pl = [payload("A", savings=1200), payload("B", tier="cap_absorbs", savings=0)]
    files = write_files(pl, tmp_path / "out")
    assert files["rows"] == 2 and (tmp_path / "out" / "candidates.csv").read_text().count("\n") == 3
    s = Store(tmp_path / "db.sqlite")
    s.upsert_candidates(pl, "r1")
    outbox = tmp_path / "outbox.jsonl"
    c = NaiveClient(None, outbox=outbox)
    # No API key: the board is never called. This must NOT be reported as a delivery.
    res = post_cards(s, c, board="agt_qualify", assignee=None, max_cards=10, run_tag="r1")
    assert res["status"] == "blocked" and res["blocked_by"] == "credentials"
    assert res["posted"] == 0 and res["delivered"] == 0 and res["live"] is False
    assert res["undelivered"] == 1
    kept = [json.loads(line) for line in Path(res["retry_file"]).read_text().splitlines()]
    assert [k["case_id"] for k in kept] == ["FL-99-2026-A"]
    # and nothing was marked handed off, so a later run with a key still has work to do
    assert s.db.execute("SELECT COUNT(*) FROM candidates WHERE handoff_ref IS NOT NULL").fetchone()[0] == 0
    assert "~$1,200/yr" in card_title(pl[0])


def test_cards_are_delivered_when_a_key_is_present(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    s.upsert_candidates([payload("A", savings=1200)], "r1")
    c = FakeBoard()
    res = post_cards(s, c, "agt_qualify", None, 10, run_tag="r1")
    assert res["status"] == "delivered" and res["delivered"] == 1 and res["errors"] == []
    assert c.calls[0]["path"] == "/v1/boards/agt_qualify/cards"
    assert c.calls[0]["body"]["key"] == "FL-99-2026-A"
    assert s.db.execute("SELECT handoff_ref FROM candidates").fetchone()[0].startswith("crd_")
    # idempotent: a second pass has nothing left to send
    assert post_cards(s, FakeBoard(), "agt_qualify", None, 10, run_tag="r1")["status"] == "empty"


def test_unacknowledged_card_is_not_counted_as_delivered(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    s.upsert_candidates([payload("A", savings=1200)], "r1")
    res = post_cards(s, FakeBoard(ack=False), "agt_qualify", None, 10, run_tag="r1")
    assert res["status"] == "blocked" and res["delivered"] == 0 and res["undelivered"] == 1
    assert s.db.execute("SELECT COUNT(*) FROM candidates WHERE handoff_ref IS NOT NULL").fetchone()[0] == 0


def test_no_board_configured_is_blocked_not_skipped(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    s.upsert_candidates([payload("A", savings=1200)], "r1")
    res = post_cards(s, FakeBoard(), None, None, 10)
    assert res["status"] == "blocked" and res["blocked_by"] == "config" and res["posted"] == 0


def test_store_upsert_is_idempotent(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    assert s.upsert_candidates([payload("A")], "r1") == {"new": 1, "updated": 0}
    assert s.upsert_candidates([payload("A", savings=5.0)], "r2") == {"new": 0, "updated": 1}
    assert s.candidates()[0]["estimate"]["annual_savings"] == 5.0


def test_naive_live_request_shape(monkeypatch):
    calls = []

    class R:
        status_code, content, headers = 200, b"{}", {}

        def json(self):
            return {"id": "card_1"}

    class S:
        def request(self, method, url, **kw):
            calls.append((method, url, kw))
            return R()

    c = NaiveClient("nv_test", "https://api.vetta.sh", session=S())
    c.create_card("agt_q", "t", "b", key="FL-1")
    m, url, kw = calls[0]
    assert m == "POST" and url == "https://api.vetta.sh/v1/boards/agt_q/cards"
    assert kw["headers"]["authorization"] == "Bearer nv_test" and kw["headers"]["idempotency-key"] == "card-FL-1"
    c.run_data_tool("tool_x", query={"address": "1 A St"})
    assert calls[1][2]["json"] == {"tool_id": "tool_x", "query": {"address": "1 A St"}}


def test_weak_county_cards_are_held(tmp_path):
    p_ok, p_weak = payload("A", savings=900), payload("B", savings=900)
    p_ok["jurisdiction"]["county_check"] = {"status": "validated"}
    p_weak["jurisdiction"]["county_check"] = {"status": "weak"}
    p_weak["jurisdiction"]["county"] = "Weakville"
    s = Store(tmp_path / "db.sqlite")
    s.upsert_candidates([p_ok, p_weak], "r1")
    res = post_cards(s, FakeBoard(), "agt_q", None, 10, run_tag="r1")
    assert res["delivered"] == 1 and res["held_weak_county"] == 1 and res["held_counties"] == ["Weakville"]


def test_matcher_rejects_wrong_house_number_direction_and_zip():
    roll = pd.DataFrame({"PARCEL_ID": ["A", "B", "C"], "ALT_KEY": ["1", "1", "12345678"],
                         "PHY_ADDR1": ["3535 NE 12TH CT", "2305 SE 8TH AVE", "1092 EISENHOWER BLVD"],
                         "PHY_ADDR2": [None, None, None], "PHY_ZIPCD": ["33909", "33990", "33901"]})
    m = ParcelMatcher(roll)
    assert m.match(address="3525 NE 12TH CT", zip_code="33909")["parcel_id"] is None          # other house number
    assert m.match(address="2305 SW 8TH AVE", zip_code="33990")["parcel_id"] is None          # other quadrant
    assert m.match(address="1025 EISENHOWER BLVD", zip_code="33901")["parcel_id"] is None
    assert m.match(address="3535 NE 12TH CT", zip_code="34135")["parcel_id"] is None          # conflicting zip
    assert m.match(parcel_id="1")["parcel_id"] is None                                        # short, shared alt key
    assert m.match(parcel_id="12345678")["parcel_id"] == "C"
    r = m.match(parcel_id="12345678", address="2305 SE 8TH AVE", zip_code="33990")             # id says C, address says B
    assert r["parcel_id"] == "B" and "id disagreed" in r["method"]


def test_matcher_trailing_unit_in_roll():
    roll = pd.DataFrame({"PARCEL_ID": ["U1", "U2"], "ALT_KEY": [None, None],
                         "PHY_ADDR1": ["1160 SCENIC GULF DR  A712", "1160 SCENIC GULF DR  A714"],
                         "PHY_ADDR2": [None, None], "PHY_ZIPCD": ["32550", "32550"]})
    m = ParcelMatcher(roll)
    assert m.match(address="1160 Scenic Gulf Dr Unit A714", zip_code="32550")["parcel_id"] == "U2"


def test_avm_match_rejects_wrong_zip_unit_prefix_and_reuse():
    lks = [Lookup("123 MAIN ST|33901|", "123 Main St, Fort Myers, FL 33901"),
           Lookup("100 LAKE|33901|", "100 Lake, Fort Myers, FL 33901"),
           Lookup("200 GULF DR|33901|1", "200 Gulf Dr #1, Fort Myers, FL 33901", unit="1"),
           Lookup("1500 GULF SHORE BLVD|34102|", "1500 Gulf Shore Blvd, Naples, FL 34102")]
    items = [{"streetAddress": "123 Main St", "zipcode": "34135", "zestimate": 1},          # other town
             {"streetAddress": "100 Lakeview Dr", "zipcode": "33901", "zestimate": 2},      # prefix only
             {"streetAddress": "200 Gulf Dr Bldg 1 Apt 1105", "zipcode": "33901", "zestimate": 3},
             {"streetAddress": "1500 Gulf Shore Blvd N", "zipcode": "34102", "zestimate": 4}]
    assert _match(items, lks) == {}
    twins = [Lookup("9 OAK ST|33901|", "9 Oak St, A, FL 33901"), Lookup("9 OAK ST|33901|", "9 Oak St, A, FL 33901")]
    assert len(_match([{"streetAddress": "9 Oak St", "zipcode": "33901", "zestimate": 5}], twins)) == 1


def test_avm_ratio_moves_today_value_back_to_jan1(tmp_path):
    s = Settings(); s.data_dir = tmp_path; s.ensure()
    p = payload("A", address="1 A ST", jv=400000)
    p["signals"]["level_factor_now"] = 1.10      # market fell 10% since Jan 1: today's value understates Jan 1
    prov = Fixed({"1 A ST": 400000 / 0.85 / 1.10 / 1.04})
    enrich([p], s, Store(s.db_path), "r", NaiveClient(None), providers=[prov])
    assert abs(p["signals"]["avm_ratio"] - 1.04) < 1e-6 and p["avm_check"] == "inconclusive"


def test_closed_window_cards_are_held_unless_asked(tmp_path):
    p = payload("A", savings=900)
    p["filing_window"]["status"] = "closed"
    s = Store(tmp_path / "db.sqlite")
    s.upsert_candidates([p], "r1")
    c = NaiveClient(None, outbox=tmp_path / "o.jsonl")
    assert post_cards(s, c, "agt_q", None, 10, run_tag="r1")["held_window_closed"] == 1
    assert post_cards(s, FakeBoard(), "agt_q", None, 10, include_closed=True, run_tag="r1")["delivered"] == 1


def test_disputed_result_survives_a_rerun_without_lookups(tmp_path):
    from taxfind.avm.enrich import carry_over
    s = Settings(); s.data_dir = tmp_path; s.ensure()
    st = Store(s.db_path)
    first = [payload("A", address="1 A ST", jv=400000)]
    enrich(first, s, st, "r1", NaiveClient(None), providers=[Fixed({"1 A ST": 600000})])
    st.upsert_candidates(first, "r1")
    assert first[0]["tier"] == "review"
    rerun = [payload("A", address="1 A ST", jv=400000)]               # fresh screen says strong, no lookup this time
    assert carry_over(rerun, st) == 1
    assert rerun[0]["avm_check"] == "disputed" and rerun[0]["tier"] == "review"


def test_matcher_handles_nullable_string_columns():
    """Real rolls load text as pandas' nullable string dtype, so missing values are pd.NA, not None."""
    r = roll_df().astype({c: "string" for c in ("PARCEL_ID", "ALT_KEY", "PHY_ADDR1", "PHY_ADDR2", "PHY_ZIPCD")})
    m = ParcelMatcher(r)
    assert m.match(address="4016 SW 17th Ave", zip_code="33914")["parcel_id"] == "264521230000B2050"
