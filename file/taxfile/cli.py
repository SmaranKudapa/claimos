import argparse
import json
import sys
from pathlib import Path
from .core import prepare, fetch_form, record_receipt, record_notice, FORM_URL


def main():
    parser = argparse.ArgumentParser(prog="taxfile")
    commands = parser.add_subparsers(dest="command", required=True)
    draft = commands.add_parser("prepare")
    draft.add_argument("input")
    draft.add_argument("--out", default=".taxfile/cases")
    draft.add_argument("--template")
    receipt = commands.add_parser("record-receipt")
    receipt.add_argument("manifest")
    receipt.add_argument("receipt")
    receipt.add_argument("--confirmation", required=True)
    receipt.add_argument("--parcel", required=True)
    receipt.add_argument("--notice")
    receipt.add_argument("--response-due")
    notice = commands.add_parser("record-notice")
    notice.add_argument("manifest")
    notice.add_argument("notice")
    notice.add_argument("--response-due", required=True)
    bridge = commands.add_parser("evidence-input")
    bridge.add_argument("--candidate", required=True)
    bridge.add_argument("--qualify", required=True)
    bridge.add_argument("--out", required=True)
    ingest = commands.add_parser("evidence-handoff")
    ingest.add_argument("--candidate", required=True)
    ingest.add_argument("--qualify", required=True)
    ingest.add_argument("--result", required=True)
    ingest.add_argument("--evidence", required=True)
    ingest.add_argument("--context")
    ingest.add_argument("--out", required=True)
    chase = commands.add_parser("chase-card")
    chase.add_argument("manifest")
    chase.add_argument("--who", required=True)
    chase.add_argument("--email", required=True)
    chase.add_argument("--waiting-for", required=True)
    chase.add_argument("--request-ref", required=True)
    chase.add_argument("--every-days", type=int, default=3)
    chase.add_argument("--last-chased", default="never")
    commands.add_parser("status")
    args = parser.parse_args()
    try:
        if args.command == "chase-card":
            from .chase import card_from_file
            print(json.dumps(card_from_file(args.manifest, who=args.who, email=args.email, waiting_for=args.waiting_for, request_ref=args.request_ref, every_days=args.every_days, last_chased=args.last_chased), indent=2))
        elif args.command == "evidence-input":
            from .bridge import evidence_input
            payload = evidence_input(args.candidate, args.qualify)
            out = Path(args.out)
            if out.exists():
                raise ValueError("Use a new Evidence input path.")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, indent=2))
            print(json.dumps({"case_id": payload["case_id"], "replay": payload["upstream_replay"], "input": str(out)}))
        elif args.command == "evidence-handoff":
            from .bridge import evidence_handoff
            payload = evidence_handoff(args.candidate, args.qualify, args.result, args.evidence, args.out, args.context)
            print(json.dumps({"case_id": payload["candidate"]["case_id"], "replay": payload["replay"], "synthetic": payload["synthetic"], "handoff": args.out, "submitted": False}))
        elif args.command == "prepare":
            template = Path(args.template or ".taxfile/forms/dr486.pdf")
            if not args.template:
                fetch_form(template)
            manifest, out = prepare(args.input, args.out, template)
            print(json.dumps({"case_id": manifest["case_id"], "status": manifest["status"], "submitted": False, "holds": manifest["holds"], "directory": str(out), "manifest": str(out / "manifest.json"), "petition": manifest["petition"]}, indent=2))
        elif args.command == "record-receipt":
            print(json.dumps(record_receipt(args.manifest, args.receipt, args.confirmation, args.parcel, args.notice, args.response_due), indent=2))
        elif args.command == "record-notice":
            print(json.dumps(record_notice(args.manifest, args.notice, args.response_due), indent=2))
        else:
            print(json.dumps({"step": "file", "form": FORM_URL, "submission": "requires_authorized_operator_and_official_county_route", "automatic_outreach": False}))
    except (ValueError, KeyError, OSError, TypeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 1
    return 0
