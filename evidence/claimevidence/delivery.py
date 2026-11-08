from __future__ import annotations

DELIVERY_SCHEMA = "claimos.evidence.delivery/1"
EVENT_STATUSES = ("sent", "acknowledged")


def _d(id, purpose, recipient, content, due, method, copies, required, conditional=None, blockers=None, owner="operator", rule=None):
    return {"id": id, "purpose": purpose, "recipient": recipient, "content": content, "due": due, "method": method, "copies": copies,
            "required": required, "conditional_on": conditional, "blockers": blockers or [], "owner": owner, "rule": rule,
            "status": "not_sent", "events": []}


def build(forum: dict, deadlines: dict, packet: dict | None, review: dict, submission: dict, events: list[dict], synthetic: bool = False,
          extra_blockers: dict | None = None) -> dict:
    county = (forum.get("county") or {})
    cname = county.get("county") or "the county"
    pa = county.get("property_appraiser") or f"{cname} County Property Appraiser"
    clerk = county.get("vab_clerk") or f"{cname} County VAB clerk"
    ex = deadlines.get("evidence_exchange_petitioner") or {}
    up = deadlines.get("remote_evidence_upload") or {}
    pet = deadlines.get("petition_filing") or {}
    items = []
    pid = forum.get("proceeding_id")
    if pid == "fl_vab_value_petition":
        items.append(_d("petition_dr486", "Petition to the Value Adjustment Board on Form DR-486", clerk, "DR-486 petition and filing fee",
                        {"date": pet.get("date"), "verified": pet.get("verified"), "source": pet.get("source"), "status": pet.get("status")},
                        county.get("petition_methods") or "per the clerk's instructions", "one", "mandatory", owner="file",
                        rule="s. 194.011(3)"))
        items[-1]["status"] = "not_filed"
        items[-1]["note"] = "File prepares the petition and an operator submits it. A timely petition is never held back waiting for this packet."
        items.append(_d("exchange_property_appraiser", "Petitioner's evidence exchange", pa,
                        "Evidence list, witness summary and copies of all documents (this packet and every exhibit)",
                        {"date": ex.get("date"), "rule": "received at least 15 days before the hearing", "verified": ex.get("verified"),
                         "basis": ex.get("basis")},
                        county.get("exchange_methods") or "to be agreed with the property appraiser: mail, hand delivery, overnight, fax or email",
                        county.get("exchange_copies") or "one (not confirmed by the county)", "mandatory", rule="FL-EVX-01"))
        items.append(_d("hearing_copies", "Copies to present at an in-person hearing", "Special magistrate and property appraiser at the hearing",
                        "This packet and every exhibit", {"date": (deadlines.get("hearing") or {}).get("date"), "rule": "at the hearing"},
                        "in person", county.get("hearing_copies") or "unknown; the county sets the number (DR-481)", "mandatory",
                        conditional="appearing in person", rule="FL-ADM-02"))
        blockers = [f"add {k.replace('_', ' ')} to the cover page" for k in ("petition_number", "contact_phone") if not submission.get(k)]
        items.append(_d("remote_vab_upload", "Evidence for a remote hearing", clerk, "One PDF with the cover page and sequential page numbers",
                        {"date": up.get("date"), "time": up.get("time"), "rule": "9:00 a.m., at least two non-holiday workdays before the hearing"},
                        county.get("remote_upload_method") or "the clerk's upload system or email; not confirmed for this county", "one PDF", "mandatory",
                        conditional="appearing remotely", blockers=blockers, rule="FL-HRG-02"))
        if county.get("remote_hearings") is False:
            items[-1]["status"] = "not_applicable"
            items[-1]["note"] = "this county's board opted out of remote hearings for the year"
        items.append(_d("absent_petitioner_filing", "Evidence filed with the clerk when the petitioner will not attend", clerk,
                        "This packet and every exhibit", {"date": (deadlines.get("hearing") or {}).get("date"), "rule": "before the hearing"},
                        county.get("absent_filing_method") or "per the clerk's instructions", "two (DR-486); confirm against local procedures", "mandatory",
                        conditional="petitioner not attending", rule="FL-HRG-03"))
    elif pid == "fl_informal_conference":
        items.append(_d("informal_conference_copy", "Material for an informal conference", pa, "This summary and its exhibits", {"date": None,
                        "rule": "optional; does not extend the petition deadline"}, "per the property appraiser", "one", "optional", rule="FL-INF-01"))
    for it in items:
        it["blockers"] += (extra_blockers or {}).get(it["id"], [])
    sha = (packet or {}).get("sha256")
    if synthetic:
        for it in items:
            it["status"] = "blocked_synthetic"
            it["blockers"].append("synthetic test fixture: no delivery is permitted")
        events = []
        review = {}
    approved_for = set(review.get("approved_for") or []) if review.get("status") == "approved" and review.get("reviewed_packet_hash") == sha else set()
    applied = []
    for e in events or []:
        it = next((i for i in items if i["id"] == e.get("delivery_id")), None)
        ok = (it is not None and e.get("status") in EVENT_STATUSES and e.get("packet_sha256") == sha and e.get("by") and e.get("at")
              and e.get("evidence_ref") and (it["id"] in approved_for or it["owner"] == "file"))
        rec = {**e, "accepted": bool(ok)}
        if not ok:
            rec["reason"] = ("unknown delivery" if it is None else "the packet was not approved for this delivery" if it["id"] not in approved_for
                             else "event needs the matching packet SHA-256, who, when and a receipt or proof reference")
        else:
            it["events"].append(rec)
            it["status"] = e["status"]
        applied.append(rec)
    for it in items:
        it["approved"] = it["id"] in approved_for
    return {"schema": DELIVERY_SCHEMA, "proceeding": pid, "synthetic": synthetic, "packet": {"sha256": sha, "version": (packet or {}).get("version"),
            "path": (packet or {}).get("pdf_path")}, "approval": {"required": True, "bound_to_sha256": sha, "approved_for": sorted(approved_for)},
            "deliveries": items, "event_log": applied,
            "rule": "Status changes only from a recorded event with proof, for an approved packet. Generating or publishing the PDF never marks anything sent, exchanged, filed or accepted."}


PORTAL = {
    "failed": "We hit a problem gathering records. We will retry.",
    "blocked": "We need more information before we can prepare your evidence.",
    "insufficient_evidence": "The public sales do not give us enough to make a case yet.",
    "does_not_support": "The sales we found do not support a lower value.",
    "contradicted": "Your property's own recent sale supports the county's value.",
    "needs_documents": "We need a few documents from you.",
    "in_review": "Your evidence is prepared and waiting for our review.",
    "approved": "Your evidence is reviewed and approved for the next step.",
}


def readiness(processing: str, intake: dict, val: dict | None, generated: bool, validation: dict | None, review: dict, authorization: dict,
              tasks: list[dict], manifest: dict | None, package_complete: bool) -> dict:
    outcome = (val or {}).get("outcome")
    r = {
        "collection": "failed" if processing == "failed" else "blocked" if intake["status"] == "blocked" else "complete" if val else "not_started",
        "analytical_sufficiency": outcome or "not_analyzed",
        "evidence_completeness": "complete" if package_complete else "incomplete",
        "generation": "generated" if generated else "not_generated",
        "format_validation": (validation or {}).get("status") or "not_run",
        "human_review": "stale" if review.get("stale") else {"approved": "reviewed", "rejected": "rejected", "reviewed": "reviewed"}.get(review.get("status"), "not_reviewed"),
        "approval": "approved_for_the_specified_submission" if (manifest or {}).get("approval", {}).get("approved_for") else "not_approved",
        "approved_for": (manifest or {}).get("approval", {}).get("approved_for") or [],
        "authorization": authorization.get("state"),
        "delivery": {d["id"]: d["status"] for d in (manifest or {}).get("deliveries", [])},
    }
    if processing == "failed":
        key = "failed"
    elif intake["status"] == "blocked":
        key = "blocked"
    elif outcome in ("insufficient_evidence", "does_not_support", "contradicted"):
        key = outcome
    elif any(t["blocking"] for t in tasks):
        key = "needs_documents"
    elif r["approval"] == "approved_for_the_specified_submission":
        key = "approved"
    else:
        key = "in_review"
    r["portal_status"] = {"code": key, "text": PORTAL[key]}
    return r
