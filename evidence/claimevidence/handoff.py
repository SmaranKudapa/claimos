from __future__ import annotations

from .model import RESULT_SCHEMA


def check_handoff(res: dict, current_packet_hash: str | None = None) -> dict:
    problems = []
    if res.get("schema") != RESULT_SCHEMA:
        problems.append(f"unknown result schema {res.get('schema')!r}")
    run = res.get("run") or {}
    if run.get("processing_status") != "completed":
        problems.append(f"evidence run {run.get('processing_status')}; not a usable result")
    c = res.get("conclusions") or {}
    if c.get("filing_readiness") != "ready_for_human_review":
        problems.append("not ready: " + "; ".join(c.get("not_ready_reasons") or ["unspecified"]))
    p = res.get("packet") or {}
    if not p.get("content_hash"):
        problems.append("no packet")
    if current_packet_hash and p.get("content_hash") != current_packet_hash:
        problems.append("superseded: a newer packet exists for this appeal cycle")
    rv = res.get("review") or {}
    if rv.get("stale"):
        problems.append("the last review covered a different packet")
    reviewed = rv.get("status") == "approved" and rv.get("reviewed_packet_hash") == p.get("content_hash")
    if not reviewed:
        problems.append("no human review of this exact packet")
    if not (res.get("authorization") or {}).get("valid_for_filing"):
        problems.append("authorization is missing, invalid or test-only")
    return {"usable_by_file": not problems, "problems": problems, "cycle_id": (res.get("appeal") or {}).get("cycle_id"),
            "packet_hash": p.get("content_hash"), "packet_version": p.get("version"),
            "filing_approval_still_required": True}
