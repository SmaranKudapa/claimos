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
            "file_adapter_supported": False, "local_procedures": "pending"},
    "hendry": {"county": "Hendry", "county_code": "36", "vab_clerk": "Hendry County Clerk of Court, Value Adjustment Board",
               "vab_url": None, "property_appraiser": "Hendry County Property Appraiser", "property_appraiser_url": None,
               "file_adapter_supported": True, "local_procedures": "pending"},
    "lee": {"county": "Lee", "county_code": "46", "vab_clerk": "Lee County Clerk of Court, Value Adjustment Board",
            "vab_url": None, "property_appraiser": "Lee County Property Appraiser", "property_appraiser_url": "https://www.leepa.org/",
            "file_adapter_supported": True, "local_procedures": "pending"},
}


def forum(appeal_type: str | None, county: str | None) -> dict:
    pid = APPEAL_TO_PROCEEDING.get(appeal_type or "", None)
    c = (county or "").strip().lower().replace(" county", "")
    adapter = COUNTY_ADAPTERS.get(c) or {"county": county, "vab_clerk": f"{county} County Clerk of Court, Value Adjustment Board",
                                         "vab_url": None, "property_appraiser": f"{county} County Property Appraiser",
                                         "property_appraiser_url": None, "file_adapter_supported": False, "local_procedures": "unknown"}
    if not pid:
        return {"proceeding_id": None, "supported": "unsupported", "authority": None, "county": adapter, "label": None,
                "notes": f"appeal type {appeal_type!r} has no configured proceeding"}
    p = PROCEEDINGS[pid]
    return {"proceeding_id": pid, "label": p["label"], "kind": p["kind"], "supported": p["supported"], "document": p["document"],
            "authority": p["authority_template"].format(county=adapter["county"]), "notes": p["notes"], "county": adapter}
