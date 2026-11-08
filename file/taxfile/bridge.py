import copy
import json
from pathlib import Path
from .core import digest, load_handoff, local_artifact
from .handoff import RESULT_SCHEMA, qualification_from_batch


def load_json(path):
    return json.loads(Path(path).read_text())


def evidence_input(candidate_path, qualify_path):
    _, candidate = load_handoff(candidate_path)
    qualification = qualification_from_batch(load_json(qualify_path), candidate)
    j = candidate["jurisdiction"]
    return {"schema": "claimos.evidence.input/1", "case_id": candidate["case_id"], "appeal": {"tax_year": j["tax_year"], "appeal_type": "vab_just_value", "jurisdiction": {"state": j["state"], "county": j["county"], "county_code": j["county_code"]}}, "property": {"parcel_id": candidate["property"]["parcel_id"], "address": candidate["property"]["address"]}, "find": candidate, "qualification": qualification, "authorization": {}, "consent": {}, "homeowner_submissions": [], "entry_policy": "full", "upstream_replay": qualification["replay"]}


def evidence_handoff(candidate_path, qualify_path, result_path, evidence_path, out, context_path=None):
    _, candidate = load_handoff(candidate_path)
    qualification = qualification_from_batch(load_json(qualify_path), candidate)
    result, evidence = load_json(result_path), copy.deepcopy(load_json(evidence_path))
    if not isinstance(result, dict) or not isinstance(evidence, dict):
        raise ValueError("Evidence result and handoff must be objects.")
    if result.get("schema") != RESULT_SCHEMA:
        raise ValueError("Unknown Evidence result schema.")
    if result.get("case_id") != candidate["case_id"] or evidence.get("case_id") != candidate["case_id"] or evidence.get("tax_year") != candidate["jurisdiction"]["tax_year"]:
        raise ValueError("Evidence handoff does not match the candidate case and year.")
    root = Path(evidence_path).parent
    entries = [(evidence, "artifact", "evidence-packet")]
    for i, row in enumerate(evidence.get("verifications") or []):
        if row.get("status") == "verified":
            entries.append((row, "artifact", "verification-" + str(i + 1)))
    checked = [(owner, key, label, local_artifact(owner.get(key), root)) for owner, key, label in entries]
    packet_hash = checked[0][3]["sha256"]
    if packet_hash != (result.get("packet") or {}).get("sha256"):
        raise ValueError("Evidence PDF bytes do not match the result's packet hash.")
    context = copy.deepcopy(load_json(context_path)) if context_path else {}
    if not isinstance(context, dict):
        raise ValueError("Filing context must be an object.")
    authority = context.get("authorization") or {}
    if isinstance(authority, dict) and authority.get("artifact"):
        checked.append((authority, "artifact", "authorization", local_artifact(authority["artifact"], Path(context_path).parent)))
    destination = Path(out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError("Use a new handoff output path; existing case inputs are never overwritten.")
    for owner, key, label, item in checked:
        original = Path(item["path"])
        target = destination.parent / (label + "-" + item["sha256"][:16] + original.suffix)
        target.write_bytes(original.read_bytes())
        owner[key] = {"path": target.name, "sha256": item["sha256"]}
    payload = {"candidate": candidate, "qualification": qualification, "authorization": authority, "filing": context.get("filing", {}), "evidence": evidence, "evidence_result": result, "replay": bool(qualification["replay"] or result.get("replay")), "synthetic": bool(result.get("synthetic")), "source_artifacts": {"qualify_sha256": digest(Path(qualify_path).read_bytes()), "evidence_result_sha256": digest(Path(result_path).read_bytes()), "evidence_handoff_sha256": digest(Path(evidence_path).read_bytes())}}
    destination.write_text(json.dumps(payload, indent=2))
    return payload
