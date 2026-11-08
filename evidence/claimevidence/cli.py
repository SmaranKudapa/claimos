from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

APPROVAL = re.compile(r"APPROVE EVIDENCE\s+([0-9a-f]{64})\s+FOR\s+([a-z_, ]+?)\s+BY\s+(.+?)\s*$", re.I | re.M)
REJECTION = re.compile(r"REJECT EVIDENCE\s+([0-9a-f]{64})\s+BY\s+(.+?)\s*:\s*(.+?)\s*$", re.I | re.M)


def approvals(text: str, sha: str | None = None) -> dict | None:
    found = None
    for mo in APPROVAL.finditer(text or ""):
        if sha and mo.group(1).lower() != sha:
            continue
        found = {"packet_hash": mo.group(1).lower(), "status": "approved", "reviewed_by": mo.group(3).strip(),
                 "reviewed_at": dt.date.today().isoformat(), "approved_for": [x.strip().lower() for x in mo.group(2).split(",") if x.strip()]}
    for mo in REJECTION.finditer(text or ""):
        if found and mo.group(1).lower() == found["packet_hash"]:
            found = {"packet_hash": found["packet_hash"], "status": "rejected", "reviewed_by": mo.group(2).strip(),
                     "reviewed_at": dt.date.today().isoformat(), "approved_for": [], "notes": mo.group(3).strip()}
    return found


def card_note(res: dict, published: dict | None = None) -> dict:
    c = res["conclusions"]
    rd = res.get("readiness") or {}
    p = res.get("packet") or {}
    fh = res.get("file_handoff") or {}
    v = res.get("valuation") or {}
    replay = " (replay)" if res.get("replay") else ""
    sha = p.get("sha256")
    approved = set(rd.get("approved_for") or [])
    if res.get("synthetic"):
        word, status = "EVIDENCE TEST FIXTURE", "blocked"
    elif res["run"]["processing_status"] != "completed":
        word, status = "EVIDENCE RETRY", "blocked"
    elif res["intake"]["status"] == "blocked":
        word, status = "EVIDENCE BLOCKED", "blocked"
    elif c["argument_support"] in ("insufficient_evidence", "does_not_support", "contradicted"):
        word, status = "EVIDENCE " + c["argument_support"].replace("_", " ").upper(), "blocked"
    elif rd.get("format_validation") != "validated_against_configured_requirements":
        word, status = "EVIDENCE VALIDATION FAILED", "blocked"
    elif rd.get("human_review") == "rejected":
        word, status = "EVIDENCE REJECTED BY REVIEWER", "blocked"
    elif "file_handoff" not in approved:
        word, status = "EVIDENCE READY FOR REVIEW", "blocked"
    elif rd.get("authorization") != "valid_for_filing":
        word, status = "EVIDENCE APPROVED, AWAITING SIGNATURE", "blocked"
    elif fh.get("status") == "complete" and not res.get("replay"):
        word, status = "EVIDENCE COMPLETE", "done"
    else:
        word, status = "EVIDENCE APPROVED, NOT COMPLETE", "blocked"
    parts = [word + replay, f"{res['appeal']['cycle_id']}"]
    if v.get("proposed_just_value"):
        parts.append(f"requested just value ${v['proposed_just_value']:,} vs county ${v['county_values']['just_value']:,}")
    elif v.get("outcome_reason"):
        parts.append(v["outcome_reason"])
    if sha:
        parts.append(f"packet v{p.get('version')} sha256 {sha}")
    parts.append(f"validation {rd.get('format_validation')}; review {rd.get('human_review')}; authorization {rd.get('authorization')}")
    parts.append("nothing sent, exchanged or filed")
    lines = [" · ".join(parts)]
    if published:
        lines.append("Files: " + ", ".join(f"{k} {val}" for k, val in published.items()))
    reasons = c.get("not_ready_reasons") or []
    if reasons:
        lines.append("Open items: " + "; ".join(reasons)[:900])
    if word == "EVIDENCE READY FOR REVIEW" and sha:
        lines.append(f"To approve, a reviewer adds the line: APPROVE EVIDENCE {sha} FOR file_handoff BY <name>  (or REJECT EVIDENCE {sha} BY <name>: <reason>) and assigns the card back to evidence.")
    handoff = {"step": "evidence", "case_id": res["case_id"], "cycle_id": res["appeal"]["cycle_id"], "status": word.lower().replace(" ", "_").replace(",", ""),
               "packet_sha256": sha, "packet_version": p.get("version"), "evidence_status": fh.get("status"),
               "unverified_checks": fh.get("unverified_checks"), "readiness": {k: rd.get(k) for k in ("generation", "format_validation", "human_review", "approval", "authorization")},
               "next_action": res.get("next_action"), "files": published or {}, "replay": bool(res.get("replay"))}
    lines.append("```json\n" + json.dumps(handoff, separators=(",", ":"), default=str) + "\n```")
    return {"status": status, "note": "\n".join(lines)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="claimevidence", description="Claim OS Evidence desk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="build evidence for one appeal cycle from an input envelope")
    r.add_argument("--input", required=True, help="path to a claimos.evidence.input/1 JSON file, or - for stdin")
    r.add_argument("--out", default="evidence-out")
    r.add_argument("--data-dir", default=None, help="county data cache shared with Find (FIND_DATA_DIR)")
    r.add_argument("--as-of", default=None, help="replay: judge deadlines as of this date (YYYY-MM-DD); never for real filings")
    r.add_argument("--summary", action="store_true", help="print a short summary instead of the full result")
    v = sub.add_parser("check-handoff", help="validate a result the way File will before using it")
    v.add_argument("result")
    rl = sub.add_parser("rules", help="print the jurisdiction rules registry")
    rl.add_argument("--matrix", action="store_true", help="print the requirements matrix as Markdown")
    b = sub.add_parser("build-input", help="assemble an input envelope from Find, Qualify and Sign-up records")
    b.add_argument("--case-id", required=True)
    b.add_argument("--find-jsonl", help="Find's published candidates.jsonl")
    b.add_argument("--county-code", help="Florida DOR county number, e.g. 13 for Bay")
    b.add_argument("--county", help="county name as the case records it, e.g. 'Bay County, Florida'")
    b.add_argument("--tax-year", type=int, required=True)
    b.add_argument("--parcel", required=True)
    b.add_argument("--qualification", help="JSON file with Qualify's decision record")
    b.add_argument("--authorization", help="JSON file with Sign up's authorization record")
    b.add_argument("--consent", help="JSON file with the recorded contact consent")
    b.add_argument("--prior-review", help="JSON file with the reviewer's decision for an earlier packet")
    b.add_argument("--submission", help="JSON file with petition_number, contact_phone")
    b.add_argument("--hearing-date", help="hearing date from the clerk's notice (YYYY-MM-DD)")
    b.add_argument("--entry-policy", choices=("full", "free_check"), default="full")
    b.add_argument("--synthetic", action="store_true", help="label the case as a synthetic test fixture")
    s2 = sub.add_parser("step-result", help="convert a result into the coordinator's StepResult structured output")
    s2.add_argument("result")
    cn = sub.add_parser("card-note", help="print the board card status and note for a result")
    cn.add_argument("result")
    cn.add_argument("--published", help="JSON object of published file titles to file ids")
    apv = sub.add_parser("approvals", help="read a reviewer's approval line for a packet from card text")
    apv.add_argument("--card", required=True, help="file holding the card's text and notes")
    apv.add_argument("--sha256", help="only accept an approval for this packet")
    ra = sub.add_parser("resolve-address", help="match a street address to one parcel on the county roll")
    ra.add_argument("--address", required=True)
    ra.add_argument("--county-code", required=True)
    ra.add_argument("--tax-year", type=int, required=True)
    ra.add_argument("--data-dir", default=None)
    a = ap.parse_args(argv)
    load = lambda p: (json.loads(p) if p.lstrip().startswith("{") else json.loads(Path(p).read_text())) if p else None
    if a.cmd == "rules":
        from .rules import RULES, matrix_markdown
        print(matrix_markdown() if a.matrix else json.dumps(RULES, indent=1))
        return 0
    if a.cmd == "check-handoff":
        from .handoff import check_handoff
        res = check_handoff(json.loads(Path(a.result).read_text()))
        print(json.dumps(res, indent=1))
        return 0 if res["usable_by_file"] else 2
    if a.cmd == "approvals":
        found = approvals(Path(a.card).read_text(), (a.sha256 or "").lower() or None)
        print(json.dumps(found or {}))
        return 0 if found else 2
    if a.cmd == "card-note":
        print(json.dumps(card_note(json.loads(Path(a.result).read_text()), load(a.published))))
        return 0
    if a.cmd == "resolve-address":
        from .records import load_county, resolve_address
        cd = load_county(str(a.county_code).zfill(2), a.tax_year, a.data_dir)
        print(json.dumps(resolve_address(cd, a.address), default=str))
        return 0
    if a.cmd == "build-input":
        from .adapter import build_input, county_name, find_record, resolve_county_code
        code = a.county_code or (resolve_county_code(a.county, a.tax_year) if a.county else None)
        if not code:
            print(json.dumps({"error": "county could not be resolved to exactly one Florida county code"}))
            return 2
        rec = find_record(a.find_jsonl, code, a.tax_year, a.parcel) if a.find_jsonl else None
        if rec is None and a.entry_policy != "free_check":
            print(json.dumps({"error": "no Find record for this county, year and parcel"}))
            return 2
        inp = build_input(a.case_id, rec, load(a.qualification), load(a.authorization), load(a.consent), prior_review=load(a.prior_review),
                          county_code=str(code).zfill(2), county=county_name(code), tax_year=a.tax_year, parcel_id=a.parcel)
        inp["entry_policy"] = a.entry_policy
        if a.submission:
            inp["submission"] = load(a.submission)
        if a.hearing_date:
            inp["appeal"]["hearing_date"] = a.hearing_date
        if a.synthetic:
            inp["synthetic"] = True
        print(json.dumps(inp, indent=1))
        return 0
    if a.cmd == "step-result":
        from .stepresult import to_step_result
        res = json.loads(Path(a.result).read_text())
        mp = (res.get("packet") or {}).get("markdown_path")
        md = Path(mp).read_text() if mp and Path(mp).exists() else None
        print(json.dumps(to_step_result(res, md)))
        return 0
    from .engine import Busy, run
    inp = json.loads(sys.stdin.read() if a.input == "-" else Path(a.input).read_text())
    try:
        res = run(inp, a.out, a.data_dir, as_of=dt.date.fromisoformat(a.as_of) if a.as_of else None)
    except Busy as e:
        print(json.dumps({"processing_status": "busy", "detail": str(e)}))
        return 3
    if a.summary:
        c = res["conclusions"]
        p = res.get("packet") or {}
        print(json.dumps({"case_id": res["case_id"], "cycle_id": res["appeal"]["cycle_id"], "run_id": res["run"]["run_id"],
                          "processing_status": res["run"]["processing_status"], "intake": res["intake"]["status"],
                          "argument_support": c["argument_support"], "package_complete": c["package_complete"],
                          "filing_readiness": c["filing_readiness"], "proposed_just_value": (res.get("valuation") or {}).get("proposed_just_value"),
                          "packet_pdf": p.get("pdf_path"), "packet_sha256": p.get("sha256"), "packet_version": p.get("version"),
                          "result": str(Path(p["pdf_path"]).parent / "result.json") if p.get("pdf_path") else None,
                          "readiness": res.get("readiness"), "file_handoff": res.get("file_handoff"),
                          "next_action": res["next_action"], "duplicate_of": res["run"].get("duplicate_of")}, indent=1, default=str))
    else:
        print(json.dumps(res, indent=1, default=str))
    return 0 if res["run"]["processing_status"] == "completed" else 1
