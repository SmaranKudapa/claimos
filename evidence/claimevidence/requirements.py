from __future__ import annotations

from .model import sha256_text

HOMEOWNER = "homeowner"


def _row(rid, claim, requirement, assertion, required, source, expected, refs, status, resolver, missing=None, verification=None,
         property_types=("single_family", "condo")):
    return {"id": rid, "claim": claim, "requirement": requirement, "assertion_supported": assertion, "required": required,
            "source": source, "property_types": list(property_types), "expected_evidence": expected, "evidence_refs": refs,
            "missing": missing, "verification": verification, "status": status,
            "blocks_readiness": required and status != "satisfied", "resolver": None if status == "satisfied" else resolver}


def _refs(items, kind):
    return [i["evidence_id"] for i in items if i["kind"] == kind]


def build_matrix(appeal_type, a, val, items, inp, intake, rules) -> list[dict]:
    rows = []
    rid = {r["topic"]: r["id"] for r in rules}
    roll = _refs(items, "county_roll_record")
    comps = _refs(items, "comparable_sale")
    rows.append(_row("MV-01", "market_value", "Subject parcel identified with its county values for the tax year",
                     "The county's just value for this parcel and year is the value under challenge", True,
                     rid.get("valuation_date", "ClaimOS method"), "county roll record", roll,
                     "satisfied" if roll else "missing", "evidence", verification="extracted_from_official_file"))
    n = len(a.get("selected", [])) if a else 0
    rel = (a or {}).get("reliability")
    rows.append(_row("MV-02", "market_value", "At least three suitable qualified sales before the valuation date, from the county's recorded sales",
                     "Comparable homes sold for less, after adjustment, than the county's value implies", True,
                     rid.get("comparable_sales", "ClaimOS method"), "qualified sales with deed references", comps,
                     "satisfied" if n >= 3 and rel != "insufficient" else "missing", "operator",
                     None if n >= 3 and rel != "insufficient" else (a or {}).get("reliability_reason")))
    rows.append(_row("MV-03", "market_value", "Each sale moved to the 1 January valuation date by a documented method",
                     "Sale prices are comparable to a 1 January value", True, rid.get("valuation_date", "ClaimOS method"),
                     "county time index", comps, "satisfied" if n else "missing", "operator"))
    rows.append(_row("MV-04", "market_value", "Every adjustment stated with its basis; unadjusted differences disclosed",
                     "The indicated value is reproducible", True, "ClaimOS method", "adjustment grid", comps,
                     "satisfied" if (a or {}).get("indication") else "missing", "operator"))
    rows.append(_row("MV-05", "market_value", "Market value converted to the just value basis the county uses",
                     "The requested just value is on the same basis as the county's", True,
                     rid.get("just_value_standard", "ClaimOS method"), "county level measurement", roll,
                     "satisfied" if val and val.get("county_level") else "missing", "operator"))
    rows.append(_row("MV-06", "market_value", "Contrary evidence disclosed: the subject's own sales, sales after 1 January, and nearby excluded sales",
                     "The analysis does not select only favourable sales", True, "ClaimOS method",
                     "subject sale history and exclusion log", _refs(items, "subject_sale_history"),
                     "satisfied" if _refs(items, "subject_sale_history") else "missing", "operator"))
    subs = inp.get("homeowner_submissions") or []
    chars = [s for s in subs if s.get("asserts") == "characteristics_confirmed"]
    rows.append(_row("MV-07", "market_value", "Owner confirms the county's recorded living area and features are correct",
                     "The comparison uses the right property description", False, "ClaimOS method",
                     "owner statement", [], "satisfied" if chars else "missing", HOMEOWNER,
                     None if chars else "no confirmation from the owner yet",
                     verification="homeowner_statement_unverified" if chars else None))
    prc = [i for i in items if i["kind"] == "property_record_card"]
    rows.append(_row("MV-08", "market_value", "Property record card from the property appraiser",
                     "Shows the characteristics the county used", False, rid.get("property_record_card", "ClaimOS method"),
                     "property appraiser record card", [i["evidence_id"] for i in prc], "satisfied" if prc else "missing", "operator",
                     None if prc else "not yet retrieved from the property appraiser"))
    hist = [i for i in items if i["kind"] == "property_record_card" and (i.get("facts") or {}).get("sale_history")]
    rows.append(_row("MV-10", "market_value", "The subject's earlier sales checked on the property appraiser's record",
                     "A recent purchase of the subject is direct evidence of its value and must be disclosed", False, "ClaimOS method",
                     "property appraiser sale history", [i["evidence_id"] for i in hist], "satisfied" if hist else "missing", "operator",
                     None if hist else "the Department of Revenue sales file covers only this roll's sales window; check the property appraiser's record"))
    photos = [i for i in items if i["kind"] == "homeowner_photo" and i["verification"] == "homeowner_document_unverified"]
    rows.append(_row("MV-09", "market_value", "Current exterior photographs of the subject",
                     "Shows the property described is the property valued", False, rid.get("photographs", "ClaimOS method"),
                     "dated photographs", [i["evidence_id"] for i in photos], "satisfied" if photos else "missing", HOMEOWNER,
                     None if photos else "no photographs yet"))
    condition = [s for s in subs if s.get("asserts") == "condition"]
    if condition:
        dated = [i for i in items if i["kind"] in ("homeowner_photo", "homeowner_repair_estimate") and (i["facts"] or {}).get("document_date")
                 and i["verification"] == "homeowner_document_unverified"]
        rows.append(_row("CN-01", "condition", "Dated photographs or documents showing the condition existed on 1 January",
                         "The property's condition lowers its value below the comparables", True, rid.get("valuation_date", "ClaimOS method"),
                         "dated photographs, inspection or repair estimate", [i["evidence_id"] for i in dated],
                         "satisfied" if dated else "missing", HOMEOWNER, None if dated else "condition is asserted but not documented",
                         verification="homeowner_document_unverified" if dated else None))
        est = [i for i in items if i["kind"] == "homeowner_repair_estimate"]
        rows.append(_row("CN-02", "condition", "Contractor repair estimate", "Quantifies the cost to cure", False, "ClaimOS method",
                         "written estimate", [i["evidence_id"] for i in est], "satisfied" if est else "missing", HOMEOWNER))
    disc = [s for s in subs if s.get("asserts") == "characteristics_error"]
    if disc:
        rows.append(_row("CH-01", "characteristics", "Documentation of the recorded characteristic that is wrong (survey, plans, permits, photographs)",
                         "The county valued features the property does not have", True, rid.get("characteristics_correction", "ClaimOS method"),
                         "survey, plans, permit record or photographs", [], "missing", "operator",
                         "a characteristics error is usually corrected with the property appraiser directly; route for review"))
    return rows


TASK_TEXT = {
    "MV-07": ("Confirm your home's details", "Please confirm the living area, number of buildings, pool and other features the county has on record.",
              "The comparison is only as good as the property description it starts from.", ["typed confirmation", "PDF", "JPEG/PNG photo of a document"]),
    "MV-09": ("Upload exterior photographs", "Upload two to four current photographs of the front and sides of the home, with the date taken.",
              "Photographs show the property being valued and are commonly submitted with evidence.", ["JPEG", "PNG", "HEIC", "PDF"]),
    "CN-01": ("Document the condition you described", "Upload dated photographs, an inspection report or a repair estimate showing the condition, and confirm it existed on 1 January.",
              "Property is valued as of 1 January; condition evidence must show the problem existed on that date.", ["JPEG", "PNG", "HEIC", "PDF"]),
    "CN-02": ("Upload a repair estimate", "Upload a written contractor estimate for the repairs you described.",
              "An estimate quantifies how the condition affects value.", ["PDF", "JPEG", "PNG"]),
}


def homeowner_tasks(matrix, inp, deadlines, cycle) -> list[dict]:
    consent = bool((inp.get("consent") or {}).get("channels"))
    suppressed = bool(((inp.get("find") or {}).get("outreach") or {}).get("owner_suppressed"))
    ex = (deadlines or {}).get("evidence_exchange_petitioner") or {}
    out = []
    for r in matrix:
        if r["resolver"] != HOMEOWNER or r["status"] == "satisfied" or r["id"] not in TASK_TEXT:
            continue
        title, what, why, formats = TASK_TEXT[r["id"]]
        out.append({"task_id": "task-" + sha256_text(f"{cycle}|{r['id']}")[:12], "case_id": inp.get("case_id"), "cycle_id": cycle,
                    "requirement_id": r["id"], "title": title, "what": what, "why": why, "acceptable_formats": formats,
                    "deadline": {"date": ex.get("date"), "basis": ex.get("basis") or "before the evidence exchange deadline, which is set once a hearing is scheduled"},
                    "blocking": r["required"], "status": "open",
                    "delivery": "internal_only" if (suppressed or not consent) else "portal_task",
                    "delivery_reason": "owner name suppressed in the public roll" if suppressed else (None if consent else "no recorded contact consent")})
    return out
