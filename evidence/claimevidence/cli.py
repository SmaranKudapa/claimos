from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="claimevidence", description="Claim OS Evidence desk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="build evidence for one appeal cycle from an input envelope")
    r.add_argument("--input", required=True, help="path to a claimos.evidence.input/1 JSON file, or - for stdin")
    r.add_argument("--out", default="evidence-out")
    r.add_argument("--data-dir", default=None, help="county data cache shared with Find (FIND_DATA_DIR)")
    r.add_argument("--summary", action="store_true", help="print a short summary instead of the full result")
    v = sub.add_parser("check-handoff", help="validate a result the way File will before using it")
    v.add_argument("result")
    sub.add_parser("rules", help="print the jurisdiction rules registry")
    b = sub.add_parser("build-input", help="assemble an input envelope from Find, Qualify and Sign-up records")
    b.add_argument("--case-id", required=True)
    b.add_argument("--find-jsonl", required=True, help="Find's published candidates.jsonl")
    b.add_argument("--county-code", help="Florida DOR county number, e.g. 13 for Bay")
    b.add_argument("--county", help="county name as the case records it, e.g. 'Bay County, Florida'")
    b.add_argument("--tax-year", type=int, required=True)
    b.add_argument("--parcel", required=True)
    b.add_argument("--qualification", help="JSON file with Qualify's decision record")
    b.add_argument("--authorization", help="JSON file with Sign up's authorization record")
    b.add_argument("--consent", help="JSON file with the recorded contact consent")
    s2 = sub.add_parser("step-result", help="convert a result into the coordinator's StepResult structured output")
    s2.add_argument("result")
    a = ap.parse_args(argv)
    if a.cmd == "rules":
        from .rules import RULES
        print(json.dumps(RULES, indent=1))
        return 0
    if a.cmd == "check-handoff":
        from .handoff import check_handoff
        res = check_handoff(json.loads(Path(a.result).read_text()))
        print(json.dumps(res, indent=1))
        return 0 if res["usable_by_file"] else 2
    if a.cmd == "build-input":
        from .adapter import build_input, find_record, resolve_county_code
        code = a.county_code or (resolve_county_code(a.county, a.tax_year) if a.county else None)
        if not code:
            print(json.dumps({"error": "county could not be resolved to exactly one Florida county code"}))
            return 2
        rec = find_record(a.find_jsonl, code, a.tax_year, a.parcel)
        if rec is None:
            print(json.dumps({"error": "no Find record for this county, year and parcel"}))
            return 2
        load = lambda p: json.loads(Path(p).read_text()) if p else None
        print(json.dumps(build_input(a.case_id, rec, load(a.qualification), load(a.authorization), load(a.consent)), indent=1))
        return 0
    if a.cmd == "step-result":
        from .stepresult import to_step_result
        res = json.loads(Path(a.result).read_text())
        md = Path(res["packet"]["path"]).read_text() if (res.get("packet") or {}).get("path") and Path(res["packet"]["path"]).exists() else None
        print(json.dumps(to_step_result(res, md)))
        return 0
    from .engine import Busy, run
    inp = json.loads(sys.stdin.read() if a.input == "-" else Path(a.input).read_text())
    try:
        res = run(inp, a.out, a.data_dir)
    except Busy as e:
        print(json.dumps({"processing_status": "busy", "detail": str(e)}))
        return 3
    if a.summary:
        c = res["conclusions"]
        print(json.dumps({"case_id": res["case_id"], "cycle_id": res["appeal"]["cycle_id"], "run_id": res["run"]["run_id"],
                          "processing_status": res["run"]["processing_status"], "intake": res["intake"]["status"],
                          "argument_support": c["argument_support"], "package_complete": c["package_complete"],
                          "filing_readiness": c["filing_readiness"], "proposed_just_value": (res.get("valuation") or {}).get("proposed_just_value"),
                          "packet": (res.get("packet") or {}).get("path"), "packet_hash": (res.get("packet") or {}).get("content_hash"),
                          "next_action": res["next_action"], "duplicate_of": res["run"].get("duplicate_of")}, indent=1))
    else:
        print(json.dumps(res, indent=1, default=str))
    return 0 if res["run"]["processing_status"] == "completed" else 1
