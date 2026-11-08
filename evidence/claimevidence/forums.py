from __future__ import annotations

PROCEEDINGS = {
    "fl_informal_conference": {
        "label": "Informal conference with the property appraiser",
        "authority_template": "{county} County Property Appraiser",
        "kind": "administrative_informal",
        "supported": "packet",
        "document": "Evidence summary for an informal review",
        "notes": "Not a filing. The appraiser may correct a value or recorded characteristics; a conference does not extend the petition deadline.",
    },
    "fl_vab_value_petition": {
        "label": "Value Adjustment Board petition (just value), hearing before a special magistrate or the board",
        "authority_template": "{county} County Value Adjustment Board",
        "kind": "administrative_quasi_judicial",
        "supported": "packet",
        "document": "Petitioner's evidence of value",
        "notes": "The petition itself is DR-486, prepared by File. This packet is the petitioner's evidence, exchanged with the property appraiser before the hearing.",
    },
    "fl_circuit_court_value": {
        "label": "Circuit court action contesting an assessment (Fla. Stat. 194.171)",
        "authority_template": "Circuit Court in and for {county} County",
        "kind": "judicial",
        "supported": "legal_review_only",
        "document": None,
        "notes": "A court proceeding with its own rules, pleadings and representation requirements. Claim OS does not generate court documents; route to a Florida attorney.",
    },
}

APPEAL_TO_PROCEEDING = {"vab_just_value": "fl_vab_value_petition", "informal_characteristics_correction": "fl_informal_conference",
                        "circuit_court_value": "fl_circuit_court_value"}

COUNTY_ADAPTERS = {
    "bay": {"county": "Bay", "county_code": "13", "vab_clerk": "Bay County Clerk of Court, Value Adjustment Board",
            "vab_url": "https://www.baycoclerk.com/clerk-services/value-adjustment-board/",
            "property_appraiser": "Bay County Property Appraiser", "property_appraiser_url": "https://www.baypa.net/",
            "file_adapter_supported": False,
            "local_procedures": "none published: the clerk's pages and the 2026 organizational packet say nothing about evidence delivery",
            "petition_methods": "JustAppraised portal via baycountyvab.com, in person or mail to 225 McKenzie Ave (joint petitions in person or mail)",
            "exchange_methods": None, "exchange_copies": None, "hearing_copies": None, "remote_hearings": True,
            "remote_upload_method": None, "upload_limit_bytes": None, "absent_filing_method": None,
            "checked": "2026-11-07", "sources": ["https://www.baycoclerk.com/clerk-services/value-adjustment-board/", "https://baycountyvab.com/"]},
    "hendry": {"county": "Hendry", "county_code": "36", "vab_clerk": "Hendry County Clerk of Court, Value Adjustment Board",
               "vab_url": "https://www.hendryclerk.org/value-adjustment-board/", "property_appraiser": "Hendry County Property Appraiser",
               "property_appraiser_url": "https://www.hendryprop.com/", "file_adapter_supported": True,
               "local_procedures": "none on evidence; the 2026 board opted out of remote hearings (Resolution No. 2, August 12, 2026)",
               "petition_methods": "mail (PO Box 1760, LaBelle 33975), courier (25 E. Hickpochee Ave), fax or email",
               "exchange_methods": None, "exchange_copies": None, "hearing_copies": None, "remote_hearings": False,
               "remote_upload_method": None, "upload_limit_bytes": None, "absent_filing_method": None,
               "checked": "2026-11-07", "sources": ["https://www.hendryclerk.org/value-adjustment-board/"]},
    "lee": {"county": "Lee", "county_code": "46", "vab_clerk": "Lee County Clerk of Court, Value Adjustment Board",
            "vab_url": "https://www.leeclerk.org/departments/value-adjustment-board/evidence-upload-1818",
            "property_appraiser": "Lee County Property Appraiser", "property_appraiser_url": "https://www.leepa.org/",
            "file_adapter_supported": True,
            "local_procedures": "Lee VAB Local Policies and Procedures, rev. 08/26/2026",
            "petition_methods": "online, in person or mail",
            "exchange_methods": "to the property appraiser at vabmail@leepa.org or 239-533-6100; uploading to the clerk is not the exchange",
            "exchange_copies": "one", "hearing_copies": "none on paper; each party shows its evidence from a laptop",
            "remote_hearings": True,
            "remote_upload_method": "Axia portal (Petitioners Evidence), PDF; email under 10 MB to InfoVAB@leeclerk.org if Axia fails",
            "upload_limit_bytes": 60_000_000,
            "absent_filing_method": "upload to Axia; otherwise County Records, 2115 Second St, 2nd floor, Fort Myers, at least 15 business days before",
            "checked": "2026-11-07",
            "sources": ["https://www.leeclerk.org/departments/value-adjustment-board/evidence-upload-1818",
                        "https://www.leeclerk.org/home/showpublisheddocument/17424/639264752250670000"]},
}


def forum(appeal_type: str | None, county: str | None) -> dict:
    pid = APPEAL_TO_PROCEEDING.get(appeal_type or "", None)
    c = (county or "").strip().lower().replace(" county", "")
    adapter = COUNTY_ADAPTERS.get(c) or {"county": county, "vab_clerk": f"{county} County Clerk of Court, Value Adjustment Board",
                                         "vab_url": None, "property_appraiser": f"{county} County Property Appraiser",
                                         "property_appraiser_url": None, "file_adapter_supported": False, "local_procedures": "unknown",
                                         "remote_hearings": None, "upload_limit_bytes": None}
    if not pid:
        return {"proceeding_id": None, "supported": "unsupported", "authority": None, "county": adapter, "label": None,
                "notes": f"appeal type {appeal_type!r} has no configured proceeding"}
    p = PROCEEDINGS[pid]
    return {"proceeding_id": pid, "label": p["label"], "kind": p["kind"], "supported": p["supported"], "document": p["document"],
            "authority": p["authority_template"].format(county=adapter["county"]), "notes": p["notes"], "county": adapter}
