from datetime import date


RESULT_SCHEMA = "claimos.evidence.result/1"


def qualification_from_batch(batch, candidate):
    if not isinstance(batch, dict) or not isinstance(batch.get("cases"), list) or type(batch.get("replay")) is not bool:
        raise ValueError("Qualify must supply its original cases array and explicit replay flag.")
    rows = [r for r in batch["cases"] if isinstance(r, dict) and r.get("find_case_id") == candidate["case_id"]]
    if len(rows) != 1:
        raise ValueError("Expected exactly one Qualify decision matching Find's case ID.")
    row = rows[0]
    j = candidate["jurisdiction"]
    if row.get("jurisdictionId") != j["state"] + "-" + str(j["county_code"]):
        raise ValueError("Qualify jurisdiction does not match Find.")
    if row.get("status") != "QUALIFIED":
        raise ValueError("Only a QUALIFIED decision can enter the Evidence analysis path.")
    route = row.get("route") or {}
    if route.get("id") != "vab_petition" or route.get("form") != "DR-486":
        raise ValueError("Unsupported Qualify route; a reviewed adapter is required.")
    judged = date.fromisoformat(row["judgedAsOf"])
    real = date.fromisoformat(batch["realDate"])
    if judged.year != j["tax_year"]:
        raise ValueError("Qualify assessment year does not match Find.")
    replay = batch["replay"] or judged != real or any("replay" in str(n).lower() for n in row.get("translatorNotes", []))
    return {"case_id": candidate["case_id"], "tax_year": j["tax_year"], "decision": "qualified", "status": "replay_only" if replay else "eligible", "route": "vab_value_appeal", "replay": replay, "judged_as_of": judged.isoformat(), "source": {"real_date": real.isoformat(), "original": row}}


def evidence_holds(result, evidence, candidate):
    holds = []
    if not isinstance(result, dict) or result.get("schema") != RESULT_SCHEMA:
        return ["The original supported Evidence result is required alongside its handoff."]
    a = result.get("appeal") or {}
    j = candidate["jurisdiction"]
    if result.get("case_id") != candidate["case_id"] or a.get("tax_year") != j["tax_year"] or a.get("parcel_id") != candidate["property"]["parcel_id"] or str((a.get("jurisdiction") or {}).get("county_code")) != str(j.get("county_code")):
        holds.append("Evidence result identity does not match the case, parcel, county and year.")
    if result.get("synthetic") or evidence.get("status") == "synthetic_fixture":
        holds.append("Synthetic Evidence fixtures cannot authorize a real filing.")
    if result.get("replay"):
        holds.append("Evidence replay dates cannot establish current filing eligibility.")
    if (result.get("run") or {}).get("processing_status") != "completed":
        holds.append("The Evidence run has not completed successfully.")
    packet = result.get("packet") or {}
    source = evidence.get("source") or {}
    artifact = evidence.get("artifact") or {}
    sha = packet.get("sha256")
    if not sha or sha != artifact.get("sha256") or source.get("packet_sha256") != sha or source.get("packet_version") != packet.get("version"):
        holds.append("Evidence packet hash or version does not match its original result.")
    review = result.get("review") or {}
    if review.get("status") != "approved" or review.get("stale") or review.get("reviewed_packet_hash") != sha or "file_handoff" not in (review.get("approved_for") or []) or not review.get("reviewed_by") or not review.get("reviewed_at"):
        holds.append("A recorded human review must approve this exact Evidence packet for File.")
    rd = result.get("readiness") or {}
    if (result.get("validation") or {}).get("status") != "validated_against_configured_requirements" or rd.get("format_validation") != "validated_against_configured_requirements":
        holds.append("Evidence format validation has not passed.")
    if rd.get("analytical_sufficiency") != "supports_reduction" or rd.get("evidence_completeness") != "complete":
        holds.append("Evidence does not yet establish a complete packet supporting a reduction.")
    if not (result.get("authorization") or {}).get("valid_for_filing"):
        holds.append("Evidence records no valid authorization for filing.")
    return holds
