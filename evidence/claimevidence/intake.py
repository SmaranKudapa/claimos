from __future__ import annotations

import datetime as dt

from .model import APPEAL_TYPES, INPUT_SCHEMA, SUPPORTED_APPEAL_TYPES

QUALIFIED_DECISIONS = {"pursue", "qualified", "ready"}
COMPENSATED_INSTRUMENTS = {
    "power_of_attorney_dr486poa": "Power of attorney on DR-486POA (Fla. Stat. 194.034(1)(b))",
    "power_of_attorney_ch709": "Power of attorney conforming to Fla. Stat. ch. 709 part II (194.034(1)(b))",
    "licensed_representative": "Florida attorney, licensed appraiser or broker, or CPA retained by the taxpayer (194.034(1)(a))",
}
UNCOMPENSATED_ONLY = {"written_authorization_dr486a"}
TEST_INSTRUMENT = "internal_test"


def _check(cid, label, ok, detail, blocks="none", resolver=None, severity=None):
    status = severity or ("pass" if ok else "fail")
    return {"id": cid, "check": label, "status": status, "detail": detail, "blocks": "none" if status == "pass" else blocks,
            "resolver": None if status == "pass" else resolver}


def cycle_id(state: str, county_code: str, tax_year: int, parcel_id: str, appeal_type: str) -> str:
    return f"{state}-{county_code}-{tax_year}-{parcel_id}/{appeal_type}"


def run_intake(inp: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    checks = []
    checks.append(_check("I01", "Input envelope version", inp.get("schema") == INPUT_SCHEMA,
                         f"expected {INPUT_SCHEMA}, got {inp.get('schema')}", "evidence", "operator"))
    case_id = inp.get("case_id")
    checks.append(_check("I02", "Shared case ID", bool(case_id), "case_id is required to write back to the shared record",
                         "evidence", "coordinator"))
    appeal = inp.get("appeal") or {}
    juris = appeal.get("jurisdiction") or {}
    year, atype = appeal.get("tax_year"), appeal.get("appeal_type")
    checks.append(_check("I03", "Assessment year", isinstance(year, int), f"tax_year={year!r}", "evidence", "coordinator"))
    if atype not in APPEAL_TYPES:
        checks.append(_check("I04", "Appeal type", False, f"unknown appeal type {atype!r}", "evidence", "operator"))
    elif atype not in SUPPORTED_APPEAL_TYPES:
        checks.append(_check("I04", "Appeal type", False, f"{APPEAL_TYPES[atype]} is not supported by Evidence yet; route for manual preparation",
                             "evidence", "operator"))
    else:
        checks.append(_check("I04", "Appeal type", True, APPEAL_TYPES[atype]))
    checks.append(_check("I05", "Jurisdiction", juris.get("state") == "FL" and bool(juris.get("county_code")),
                         f"state={juris.get('state')!r} county_code={juris.get('county_code')!r}; Evidence supports Florida only",
                         "evidence", "operator"))
    prop = inp.get("property") or {}
    find = inp.get("find") or {}
    fprop, fj = find.get("property") or {}, find.get("jurisdiction") or {}
    parcel = prop.get("parcel_id")
    checks.append(_check("I06", "Parcel identity", bool(parcel) and parcel == fprop.get("parcel_id"),
                         f"case parcel {parcel!r} vs Find parcel {fprop.get('parcel_id')!r}", "evidence", "coordinator"))
    expected = f"FL-{juris.get('county_code')}-{year}-{parcel}"
    checks.append(_check("I07", "One property, one assessment year", find.get("case_id") == expected and fj.get("tax_year") == year
                         and str(fj.get("county_code")) == str(juris.get("county_code")),
                         f"Find case {find.get('case_id')!r} must equal {expected!r} so another year or parcel is never mixed in",
                         "evidence", "coordinator"))
    checks.append(_check("I08", "Find record version", (find.get("schema_version") or 0) >= 2 and find.get("tier") in ("strong", "possible"),
                         f"schema_version={find.get('schema_version')} tier={find.get('tier')}", "evidence", "coordinator"))
    cc = (fj.get("county_check") or {}).get("status")
    checks.append(_check("I09", "County screen validated", cc == "validated",
                         f"Find's county self-check is {cc!r}; Evidence re-derives value from comparable sales either way",
                         severity="pass" if cc == "validated" else "warn"))
    q = inp.get("qualification") or {}
    q_ok = q.get("decision") in QUALIFIED_DECISIONS and q.get("case_id") in (None, case_id) and q.get("tax_year") in (None, year)
    checks.append(_check("I10", "Qualification decision", q_ok,
                         f"decision={q.get('decision')!r} ref={q.get('ref')!r}; Qualify must decide to pursue this parcel and year",
                         "evidence", "qualify"))
    a = inp.get("authorization") or {}
    inst, status = a.get("instrument"), a.get("status")
    if status == "signed" and inst in COMPENSATED_INSTRUMENTS:
        problems = []
        if parcel not in (a.get("parcel_ids") or []):
            problems.append("the parcel is not listed on the authorization")
        if a.get("tax_year") != year:
            problems.append(f"the authorization is for tax year {a.get('tax_year')!r}, not {year}")
        if not a.get("document_ref") or not a.get("document_sha256"):
            problems.append("no stored signed document reference and checksum")
        if not a.get("signed_at") or not a.get("signer_name"):
            problems.append("signer or signing date missing")
        checks.append(_check("I11", "Authorization to represent", not problems,
                             "; ".join(problems) or COMPENSATED_INSTRUMENTS[inst], "evidence", "signup"))
    elif status == "signed" and inst in UNCOMPENSATED_ONLY:
        checks.append(_check("I11", "Authorization to represent", False,
                             "DR-486A written authorization is only available to uncompensated representatives (194.034(1)(c)); a fee-based engagement needs a power of attorney",
                             "evidence", "signup"))
    elif status == TEST_INSTRUMENT or inst == TEST_INSTRUMENT:
        checks.append(_check("I11", "Authorization to represent", False,
                             "internal test authorization: evidence may be prepared for testing, but this case can never be filed",
                             "file", "signup", severity="warn"))
    else:
        checks.append(_check("I11", "Authorization to represent", False,
                             f"no valid signed authorization (status={status!r}, instrument={inst!r})", "evidence", "signup"))
    owner = find.get("owner") or {}
    if owner.get("may_have_changed"):
        checks.append(_check("I12", "Current owner", False,
                             f"a deed was recorded after 1 January ({owner.get('deed_since_roll')}); confirm the signer still owns the parcel",
                             "file", "operator", severity="warn"))
    if (find.get("outreach") or {}).get("owner_suppressed"):
        checks.append(_check("I13", "Confidential owner", False,
                             "owner name is suppressed in the public roll; no homeowner requests may be generated from roll data",
                             "file", "operator", severity="warn"))
    consent = inp.get("consent") or {}
    checks.append(_check("I14", "Recorded contact consent", bool(consent.get("channels")),
                         f"channels={consent.get('channels')!r}; without consent, homeowner requests stay internal and are not delivered",
                         severity="pass" if consent.get("channels") else "warn"))
    blocking = [c for c in checks if c["status"] == "fail" and c["blocks"] == "evidence"]
    route = None
    if blocking:
        order = ["coordinator", "operator", "qualify", "signup"]
        route = sorted({c["resolver"] for c in blocking}, key=lambda r: order.index(r) if r in order else 9)[0]
    return {"status": "blocked" if blocking else "accepted", "checks": checks,
            "blockers": [{"code": c["id"], "message": f'{c["check"]}: {c["detail"]}', "resolver": c["resolver"]} for c in blocking],
            "file_blockers": [{"code": c["id"], "message": f'{c["check"]}: {c["detail"]}', "resolver": c["resolver"]}
                              for c in checks if c["status"] in ("fail", "warn") and c["blocks"] == "file"],
            "route": route,
            "cycle_id": cycle_id("FL", str(juris.get("county_code")), year, parcel, atype) if (year and parcel and atype) else None,
            "authorization_is_test": status == TEST_INSTRUMENT or inst == TEST_INSTRUMENT}
