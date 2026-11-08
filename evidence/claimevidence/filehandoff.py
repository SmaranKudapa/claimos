from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .model import RESULT_SCHEMA, canonical

FILE_SCHEMA = "claimos.evidence.file_handoff/1"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _artifact(root: Path, name: str, payload: dict) -> dict:
    p = root / name
    p.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    return {"path": name, "sha256": _sha(p)}


def _resolve(check: str, res: dict, deadlines: dict, root: Path, pdf_art: dict | None, n: int, operator: list[dict]) -> dict:
    for o in operator:
        if o.get("check") == check and o.get("status") == "verified" and o.get("by") and o.get("artifact"):
            return {"check": check, "status": "verified", "by": o["by"], "at": o.get("at"), "artifact": o["artifact"], "method": "operator_recorded"}
    low = check.lower()
    a = res.get("analysis") or {}
    v = res.get("valuation") or {}
    pet = deadlines.get("petition_filing") or {}
    if "petition deadline" in low and pet.get("verified") and pet.get("source"):
        art = _artifact(root, f"verification-{n}.json", {"check": check, "result": f"petition deadline {pet['date']}", "source": pet["source"],
                                                          "basis": pet.get("basis"), "checked": pet.get("checked"), "status_on_run": pet.get("status")})
        return {"check": check, "status": "verified", "by": "Evidence rules configuration", "artifact": art, "method": "configured_official_source",
                "note": "the deadline has passed" if pet.get("status") == "passed" else None}
    if ("county self-check" in low or "few comparable sales" in low) and v.get("outcome") == "supports_reduction" and pdf_art \
            and a.get("reliability") in ("good", "acceptable") and len(a.get("selected") or []) >= 5:
        art = _artifact(root, f"verification-{n}.json", {"check": check, "result": "independent sales comparison supports the value",
                                                          "comparables": len(a["selected"]), "cod": a.get("dispersion_cod"),
                                                          "reliability": a.get("reliability"), "packet": pdf_art})
        return {"check": check, "status": "verified", "by": "Evidence sales comparison", "artifact": art, "method": "independent_analysis"}
    why = ("needs the parcel's billed millage" if "millage" in low else
           "needs the property record card and a condition review" if "record card" in low or "condition" in low else
           "needs a person to confirm" if "person" in low or "owner" in low or "peers" in low else
           "not established by the evidence analysis")
    return {"check": check, "status": "unverified", "reason": why}


def write(res: dict, rdir: Path, pdf: Path | None, find: dict, deadlines: dict, operator_verifications: list[dict]) -> dict:
    root = rdir / "file-handoff"
    root.mkdir(exist_ok=True)
    pdf_art = None
    if pdf and pdf.exists():
        shutil.copyfile(pdf, root / "evidence-packet.pdf")
        pdf_art = {"path": "evidence-packet.pdf", "sha256": _sha(root / "evidence-packet.pdf")}
    checks = list((find or {}).get("needs_verification") or [])
    ver = [_resolve(c, res, deadlines, root, pdf_art, i + 1, operator_verifications or []) for i, c in enumerate(checks)]
    rd = res.get("readiness") or {}
    reviewed = rd.get("human_review") == "reviewed" and "file_handoff" in (rd.get("approved_for") or [])
    complete = bool(pdf_art) and rd.get("format_validation") == "validated_against_configured_requirements" \
        and rd.get("analytical_sufficiency") == "supports_reduction" and rd.get("evidence_completeness") == "complete" and reviewed
    reasons = []
    if not pdf_art:
        reasons.append("no PDF packet")
    if rd.get("format_validation") != "validated_against_configured_requirements":
        reasons.append("format validation has not passed")
    if rd.get("analytical_sufficiency") != "supports_reduction":
        reasons.append(f"analysis outcome is {rd.get('analytical_sufficiency')}")
    if rd.get("evidence_completeness") != "complete":
        reasons.append("required evidence is missing")
    if not reviewed:
        reasons.append("a person has not reviewed and approved this exact packet for File")
    if res.get("synthetic"):
        complete = False
        reasons.insert(0, "synthetic test fixture; never a File input")
    unresolved = [v["check"] for v in ver if v["status"] != "verified"]
    ev = {"case_id": (find or {}).get("case_id") or res.get("case_id"), "tax_year": res["appeal"]["tax_year"],
          "status": "synthetic_fixture" if res.get("synthetic") else "complete" if complete else "incomplete", "artifact": pdf_art, "verifications": ver,
          "unverified_checks": unresolved, "not_complete_because": reasons,
          "source": {"schema": RESULT_SCHEMA, "run_id": res["run"]["run_id"], "cycle_id": res["appeal"]["cycle_id"],
                     "packet_version": (res.get("packet") or {}).get("version"), "packet_sha256": (res.get("packet") or {}).get("sha256")},
          "readiness": rd}
    (root / "evidence.json").write_text(json.dumps(ev, indent=1, default=str))
    (root / "evidence-result.json").write_text(canonical({k: res.get(k) for k in ("schema", "case_id", "appeal", "conclusions", "valuation", "readiness", "review", "packet")}))
    return {"dir": str(root), "evidence_json": str(root / "evidence.json"), "status": ev["status"], "unverified_checks": unresolved,
            "file_schema": FILE_SCHEMA}
