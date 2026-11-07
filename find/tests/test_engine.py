import pandas as pd
import pytest

from taxfind.engine.normalize import (address_key, norm_name_series, norm_parcel, norm_street, norm_street_series,
                                      norm_zip, owner_type, owner_type_series, split_people, unit_from_legal, unit_of)
from taxfind.engine.people import attach_owners, portfolio_rollup


@pytest.mark.parametrize("raw,want", [
    ("4012 S.W. 17th Avenue, Unit 2", "4012 SW 17TH AVE"),
    ("23711 Eddystone Rd #8204", "23711 EDDYSTONE RD"),
    ("123 north main street apt 4b", "123 N MAIN ST"),
    (None, ""), (float("nan"), ""), ("", ""),
])
def test_norm_street(raw, want):
    assert norm_street(raw) == want


def test_vectorized_matches_scalar():
    s = pd.Series(["4012 S.W. 17th Avenue, Unit 2", None, "9 Sunset Harbor LN #5", "PO BOX 1835"])
    assert list(norm_street_series(s)) == [norm_street(v) for v in s]
    n = pd.Series(["SMITH JOHN & MARY", "ACME HOLDINGS LLC", "CITY OF CAPE CORAL", "DOE JANE TR", "", None])
    assert list(owner_type_series(n)) == [owner_type(v) for v in n]


def test_units_and_ids():
    assert unit_of("500 BEACH BLVD #104") == "104"
    assert unit_of("5 MAIN ST APT. 4B") == "4B"
    assert unit_from_legal("VILLA GRANDE CONDO UNIT 1105 BLDG 11") == "1105"
    assert norm_parcel("26-45-21-23-0000B.2030") == "264521230000B2030"
    assert norm_zip("33914-1234") == "33914" and norm_zip(None) == ""
    assert address_key("4012 SW 17th Ave", "33914") == "4012 SW 17TH AVE|33914"


@pytest.mark.parametrize("name,kind", [
    ("TR HOLDINGS LLC", "company"), ("SMITH JOHN TR", "trust"), ("ESTATE OF JONES", "estate"),
    ("US BANK NA TRUSTEE", "bank"), ("SMITH JOHN & MARY", "individual"), ("CAPE CORAL CITY OF", "government"),
    ("SEASIDE CONDO ASSN", "association"),
])
def test_owner_type(name, kind):
    assert owner_type(name) == kind


def test_split_people():
    assert split_people("SMITH JOHN & MARY") == ["SMITH JOHN", "SMITH MARY"]


def test_attach_owners_groups_portfolio_and_units(roll):
    nal, _ = roll
    o = attach_owners(nal)
    inv = o[o.OWN_NAME == "BIG INVESTOR LLC"]
    assert inv.owner_id.nunique() == 1 and (inv.parcels_in_county == 2).all()
    assert inv.absentee.all() and inv.out_of_state.all() and (inv.owner_type == "company").all()
    locals_ = o[o.OWN_NAME == "OWNER10 JOHN"]
    assert not locals_.absentee.any()
    condos = o[o.DOR_UC == "004"].sort_values("PARCEL_ID")
    assert list(condos.unit.head(3)) == ["100", "101", "102"]
    assert (condos.unit_source == "mailing_address").all()
    # shared "PH 1" in the legal description must not become a unit
    assert not (o.unit_source == "legal_description").any()


def test_portfolio_rollup(roll):
    nal, _ = roll
    o = attach_owners(nal).head(5).assign(est_savings=[100.0, 200, 0, 0, 0])
    r = portfolio_rollup(o)
    assert r.loc[r.PARCEL_ID == "P00000", "flagged_parcels_in_run"].item() == 2
    assert r.loc[r.PARCEL_ID == "P00001", "portfolio_savings_in_run"].item() == 300


@pytest.mark.parametrize("raw,street,unit", [
    ("1160 SCENIC GULF DR  A712", "1160 SCENIC GULF DR", "A712"),     # Walton: unit after two spaces
    ("17462 FRONT BEACH RD  53 A", "17462 FRONT BEACH RD", "53 A"),    # Bay
    ("500 BEACH BLVD #104", "500 BEACH BLVD", "104"),
    ("5000 COUNTY ROAD 30A", "5000 COUNTY ROAD 30A", ""),             # a road, not unit 30A
    ("123 HIGHWAY 98", "123 HIGHWAY 98", ""),
])
def test_split_unit(raw, street, unit):
    from taxfind.engine.normalize import split_unit
    assert split_unit(raw) == (street, unit)


def test_mailing_unit_not_copied_to_every_unit_an_owner_holds(roll):
    nal, _ = roll
    i = nal.PARCEL_ID.isin(["C00001", "C00002"])          # one owner, two units, one mailing address #101
    nal.loc[i, "OWN_NAME"] = "SAME OWNER"
    nal.loc[i, "OWN_ADDR1"] = "500 BEACH BLVD #101"
    o = attach_owners(nal).set_index("PARCEL_ID")
    assert o.loc["C00001", "unit"] == "" and o.loc["C00002", "unit"] == ""
    assert o.loc["C00003", "unit"] == "103"


def test_full_state_names_are_not_out_of_state(roll):
    nal, _ = roll
    nal.loc[nal.PARCEL_ID == "P00010", "OWN_STATE"] = "FLORIDA"
    assert not attach_owners(nal).set_index("PARCEL_ID").loc["P00010", "out_of_state"]
