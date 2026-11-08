from __future__ import annotations

import json
from urllib.parse import urlparse

MAX_SUMMARY, MAX_SOURCES, MAX_ARTIFACTS, MAX_MARKDOWN = 6000, 30, 8, 40000


def _https(u) -> bool:
    try:
        p = urlparse(str(u))
        return p.scheme == "https" and bool(p.netloc) and not p.username and not p.password
    except ValueError:
        return False


def decision(res: dict) -> str:
    if res.get("synthetic"):
        return "blocked"
    if res["run"]["processing_status"] != "completed" or res["intake"]["status"] == "blocked":
        return "blocked"
    return "ready" if res["conclusions"]["filing_readiness"] == "ready_for_human_review" else "review"


def compact(res: dict) -> dict:
    keep = ("schema", "case_id", "appeal", "proceeding", "input_versions", "conclusions", "deadlines", "authorization", "review", "next_action",
            "missing", "homeowner_tasks", "rules_applied", "readiness", "delivery", "file_handoff")
    out = {k: res.get(k) for k in keep}
    out["run"] = {k: res["run"].get(k) for k in ("run_id", "processing_status", "errors", "method_version", "code_version", "finished_at")}
    out["intake"] = {"status": res["intake"]["status"], "blockers": res["intake"]["blockers"], "file_blockers": res["intake"].get("file_blockers")}
    v = res.get("valuation") or {}
    out["valuation"] = {k: v.get(k) for k in ("outcome", "outcome_reason", "county_values", "market_value_indication", "county_level",
                                              "proposed_just_value", "effects", "versus_find")}
    a = res.get("analysis") or {}
    out["analysis"] = {k: a.get(k) for k in ("indication", "reliability", "reliability_reason", "dispersion_cod", "candidates_considered",
                                             "candidates_usable", "location_tier_used", "sensitivity")}
    out["analysis"]["comparables"] = [{k: c.get(k) for k in ("parcel_id", "sale_month", "sale_price", "indicated_value", "record", "flags")}
                                      for c in a.get("selected") or []]
    out["requirements"] = [{k: r[k] for k in ("id", "requirement", "required", "status", "resolver", "blocks_readiness")} for r in res.get("requirements") or []]
    out["inventory"] = [{k: i[k] for k in ("evidence_id", "kind", "verification", "county_facing")} for i in res.get("inventory") or []]
    p = res.get("packet") or {}
    out["packet"] = {k: p.get(k) for k in ("version", "sha256", "content_hash", "fingerprint", "format", "pages", "county_facing", "internal_record_hash")}
    out["packet"]["exhibits"] = [{k: e.get(k) for k in ("id", "title", "page")} for e in p.get("exhibits") or []]
    va = res.get("validation") or {}
    out["validation"] = {"status": va.get("status"), "failures": va.get("failures"), "warnings": va.get("warnings"),
                         "failed": [c["id"] + ": " + str(c["detail"]) for c in va.get("checks") or [] if c["status"] == "fail"][:10]}
    return out


def to_step_result(res: dict, packet_md: str | None) -> dict:
    c = res["conclusions"]
    v = res.get("valuation") or {}
    parts = [f"Evidence for {res['appeal']['cycle_id']}: {c['argument_support'].replace('_', ' ')}."]
    if v.get("proposed_just_value"):
        parts.append(f"Supported just value {v['proposed_just_value']:,} against the county's {v['county_values']['just_value']:,}.")
    rd = res.get("readiness") or {}
    parts.append(f"Package complete: {c['package_complete']}. Filing readiness: {c['filing_readiness']}.")
    if rd:
        parts.append(f"Packet {rd.get('generation')}; validation {rd.get('format_validation')}; review {rd.get('human_review')}; "
                     f"approval {rd.get('approval')}; authorization {rd.get('authorization')}. Nothing has been sent, exchanged or filed.")
    if c.get("not_ready_reasons"):
        parts.append("Not ready because: " + "; ".join(c["not_ready_reasons"]) + ".")
    parts.append(f"Next: {res['next_action']['actor']} — {res['next_action']['action']}. Human review and filing approval remain required.")
    summary = " ".join(parts)[:MAX_SUMMARY]
    sources = []
    for i in res.get("inventory") or []:
        u = (i.get("source") or {}).get("url")
        if u and _https(u) and u not in sources:
            sources.append(u)
    for r in res.get("rules_applied") or []:
        u = r.get("source")
        if u and _https(u) and u not in sources:
            sources.append(u)
    artifacts = []
    p = res.get("packet") or {}
    if packet_md:
        md = packet_md if len(packet_md) <= MAX_MARKDOWN else packet_md[:MAX_MARKDOWN - 200] + "\n\n_Packet truncated for the case record; the full packet is in the published file._\n"
        artifacts.append({"title": f"Evidence packet v{p.get('version')} · {str(p.get('content_hash'))[:12]}", "markdown": md})
    blob = json.dumps(compact(res), default=str, separators=(",", ":"))
    if len(blob) > MAX_MARKDOWN - 20:
        blob = json.dumps({k: compact(res)[k] for k in ("schema", "case_id", "appeal", "conclusions", "next_action", "packet", "review", "run")},
                          default=str, separators=(",", ":"))
    artifacts.append({"title": "Evidence result · claimos.evidence.result/1", "markdown": "```json\n" + blob + "\n```"})
    return {"case_id": res["case_id"], "step": "evidence", "decision": decision(res), "summary": summary,
            "sources": sources[:MAX_SOURCES], "artifacts": artifacts[:MAX_ARTIFACTS], "tool_requests": [], "email_drafts": []}
