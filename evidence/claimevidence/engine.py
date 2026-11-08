from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from . import __version__
from .comps import CompParams, analyze, assessment_peers, subject_sales
from .intake import run_intake
from .model import INPUT_SCHEMA, METHOD_VERSION, RESULT_SCHEMA, Item, SourceUnavailable, now, sha256_obj, sha256_text
from .delivery import build as build_delivery
from .delivery import readiness as build_readiness
from .filehandoff import write as write_file_handoff
from .packet import render_internal
from .records import as_int, as_str, load_county
from .render import to_html, to_markdown, to_pdf
from .report import build as build_report
from .requirements import build_matrix, homeowner_tasks
from .jurisdictions import resolve as resolve_jurisdiction
from .jurisdictions.florida import cost_of_sale, deadlines_for, rules_for
from .jurisdictions.florida import forum as forum_for
from .validate import validate
from .valuation import conclude

LOCK_STALE_SECONDS = 1200


class Busy(RuntimeError):
    pass


def _eid(cycle: str, kind: str, key: str) -> str:
    return "ev-" + sha256_text(f"{cycle}|{kind}|{key}")[:16]


def _lock(path: Path) -> str:
    owner = uuid.uuid4().hex
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"owner": owner, "at": time.time(), "pid": os.getpid()}).encode())
            os.close(fd)
            return owner
        except FileExistsError:
            try:
                held = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                held = {"at": 0}
            if time.time() - float(held.get("at", 0)) > LOCK_STALE_SECONDS:
                path.replace(path.with_suffix(f".stale-{int(time.time())}"))
                continue
            raise Busy(f"another Evidence worker holds {path.name} for this appeal cycle")
    raise Busy("could not acquire the appeal-cycle lock")


def _unlock(path: Path, owner: str) -> None:
    try:
        if json.loads(path.read_text()).get("owner") == owner:
            path.replace(path.with_suffix(f".released-{int(time.time() * 1000)}"))
    except (OSError, json.JSONDecodeError):
        pass


def _write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _subject_dict(s: pd.Series) -> dict:
    out = {}
    for k, v in s.items():
        if isinstance(v, (bool,)) or v is None:
            out[k] = v
        elif isinstance(v, str):
            out[k] = v
        else:
            try:
                out[k] = None if pd.isna(v) else (float(v) if not isinstance(v, (int,)) else v)
            except (TypeError, ValueError):
                out[k] = str(v)
    return out


def _deadlines(inp: dict, find: dict, county: str, year: int, today: dt.date) -> dict:
    d = deadlines_for(county, year, (inp.get("appeal") or {}).get("hearing_date"), today)
    fw = find.get("filing_window") or {}
    pet = d["petition_filing"]
    if not pet.get("date") and fw.get("closes"):
        pet.update({"date": fw.get("closes"), "verified": bool(fw.get("verified")), "source": fw.get("source"),
                    "basis": fw.get("basis") or pet.get("basis")})
    for k, v in (inp.get("deadlines") or {}).items():
        if k in d and isinstance(v, dict) and v.get("date") and v.get("source"):
            d[k].update({"date": v["date"], "source": v["source"], "verified": bool(v.get("verified")), "basis": v.get("basis", "supplied by coordinator")})
    for v in d.values():
        if v.get("date"):
            v["status"] = "passed" if v["date"] < today.isoformat() else "upcoming"
        else:
            v["status"] = "unknown"
    return d


def run(inp: dict, out_root: Path | str, data_dir: Path | str | None = None, today: dt.date | None = None,
        params: CompParams | None = None, as_of: dt.date | None = None) -> dict:
    if inp.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"input must declare schema {INPUT_SCHEMA}")
    params = params or CompParams()
    out_root = Path(out_root)
    started = now()
    today = today or dt.datetime.now(ZoneInfo("America/New_York")).date()
    intake = run_intake(inp, today)
    cycle = intake["cycle_id"] or f"invalid/{inp.get('case_id')}"
    key = sha256_obj({"input": inp, "method": METHOD_VERSION, "code": __version__, "params": params.__dict__,
                      "as_of": as_of.isoformat() if as_of else None})
    cdir = out_root / cycle.replace("/", "__")
    rdir = cdir / key[:16]
    done = rdir / "result.json"
    if done.exists():
        res = json.loads(done.read_text())
        res["run"]["duplicate_of"] = res["run"]["run_id"]
        return res
    lock = cdir / ".lock"
    owner = _lock(lock)
    try:
        return _run(inp, intake, cycle, key, cdir, rdir, data_dir, started, params, today, as_of)
    finally:
        _unlock(lock, owner)


def _run(inp, intake, cycle, key, cdir, rdir, data_dir, started, params, today, as_of=None):
    rdir.mkdir(parents=True, exist_ok=True)
    run_id = "evr_" + key[:12] + "_" + uuid.uuid4().hex[:6]
    find = inp.get("find") or {}
    appeal = inp.get("appeal") or {}
    juris = appeal.get("jurisdiction") or {}
    year = appeal.get("tax_year")
    county = (find.get("jurisdiction") or {}).get("county") or juris.get("county")
    errors, items = [], []
    base = {"schema": RESULT_SCHEMA, "case_id": inp.get("case_id"),
            "appeal": {"cycle_id": cycle, "tax_year": year, "appeal_type": appeal.get("appeal_type"),
                       "valuation_date": f"{year}-01-01" if isinstance(year, int) else None,
                       "jurisdiction": {"state": "FL", "county": county, "county_code": juris.get("county_code")},
                       "parcel_id": (inp.get("property") or {}).get("parcel_id")},
            "input_versions": {"input_hash": key, "find_case_id": find.get("case_id"), "find_schema_version": find.get("schema_version"),
                               "find_run_id": (find.get("source") or {}).get("run_id"),
                               "qualification_ref": (inp.get("qualification") or {}).get("ref"),
                               "authorization_ref": (inp.get("authorization") or {}).get("document_ref")},
            "intake": intake}
    jur = resolve_jurisdiction(juris.get("state"))
    base["jurisdiction_support"] = {k: jur.get(k) for k in ("status", "state", "ruleset", "reason")}
    if jur["status"] != "supported":
        fm = {"proceeding_id": None, "supported": "unsupported", "authority": None, "label": None, "kind": None, "notes": jur["reason"], "county": {}}
    else:
        fm = forum_for(appeal.get("appeal_type"), county)
    base["proceeding"] = {k: fm.get(k) for k in ("proceeding_id", "label", "kind", "supported", "authority", "notes")}
    base["proceeding"]["county_adapter"] = fm.get("county")
    on = appeal.get("hearing_date") or (as_of or today).isoformat()
    rules = rules_for(county, appeal.get("appeal_type"), fm.get("proceeding_id"), on) if jur["status"] == "supported" else []
    deadlines = _deadlines(inp, find, county, year, as_of or today) if isinstance(year, int) and jur["status"] == "supported" else {}
    if as_of:
        base["replay"] = {"as_of": as_of.isoformat(), "note": "deadlines are judged as of this date for a demonstration replay, not as of today"}
    ctx = {"forum": fm, "today": today, "find": find}
    if intake["status"] == "blocked":
        return _finish(base, run_id, started, "completed", errors, rules, deadlines, items, None, None, [], [], None, inp, intake, cdir, rdir, ctx)
    ckpt = rdir / "collected.json"
    if ckpt.exists():
        col = json.loads(ckpt.read_text())
    else:
        try:
            cd = load_county(str(juris.get("county_code")).zfill(2), year, data_dir)
        except SourceUnavailable as e:
            errors.append({"stage": "collection", "kind": "source_unavailable", "detail": str(e), "retryable": True})
            return _finish(base, run_id, started, "failed", errors, rules, deadlines, items, None, None, [], [], None, inp, intake, cdir, rdir, ctx)
        subj = cd.subject(base["appeal"]["parcel_id"])
        if subj is None:
            intake["status"] = "blocked"
            intake["blockers"].append({"code": "I15", "message": "Parcel is not a house or condo on the county roll for this year", "resolver": "qualify"})
            intake["route"] = "qualify"
            return _finish(base, run_id, started, "completed", errors, rules, deadlines, items, None, None, [], [], None, inp, intake, cdir, rdir, ctx)
        a = analyze(cd, subj, params)
        col = {"subject": _subject_dict(subj), "analysis": a, "own_sales": subject_sales(cd, subj, params),
               "peers": assessment_peers(cd, subj), "files": cd.files, "level": cd.level.get(subj.DOR_UC, 0.85),
               "county": cd.county, "roll_stage": cd.roll_stage, "collected_at": now()}
        _write(ckpt, json.dumps(col, default=str))
    subj = pd.Series(col["subject"])
    a = col["analysis"]
    cos = cost_of_sale(county, year, subj.get("DOR_UC"))
    ctx["cost_of_sale"] = cos
    val = conclude(subj, a, col["peers"], col["own_sales"], find, col["level"], cos)
    files = {f["kind"]: f for f in col["files"]}
    roll_src = {k: files["NAL"].get(k) for k in ("url", "sha256", "published", "retrieved_at", "roll_stage", "publisher")}
    sale_src = {k: files["SDF"].get(k) for k in ("url", "sha256", "published", "retrieved_at", "roll_stage", "publisher")}
    pid = base["appeal"]["parcel_id"]
    items.append(Item(_eid(cycle, "county_roll_record", pid), "county_roll_record", "County roll record for the subject parcel",
                      "official_public_record", {**roll_src, "record_key": f"PARCEL_ID={pid}"},
                      {k: col["subject"].get(k) for k in ("PHY_ADDR1", "PHY_CITY", "DOR_UC", "JV", "AV_SD", "AV_NSD", "TV_SD", "TV_NSD",
                                                         "LND_VAL", "SPEC_FEAT_VAL", "TOT_LVG_AREA", "EFF_YR_BLT", "ACT_YR_BLT", "NBRHD_ORIG")},
                      "extracted_from_official_file", ["subject identification", "county values under challenge"]).as_dict())
    for c in a.get("selected", []):
        k = f"{c['parcel_id']}|{c['sale_month']}|{c['record'].get('clerk_no') or c['record'].get('or_book')}"
        items.append(Item(_eid(cycle, "comparable_sale", k), "comparable_sale", f"Qualified sale: {c['address']} ({c['sale_month']})",
                          "official_public_record", {**sale_src, "record_key": f"PARCEL_ID={c['parcel_id']} sale {c['sale_month']}",
                                                     "deed_record": c["record"]},
                          {x: c.get(x) for x in ("sale_price", "sqft", "effective_year_built", "county_land_value", "qualification_code")},
                          "extracted_from_official_file", ["market value indication"],
                          ["characteristics are the county's recorded values; condition and interior quality are not in the public file"]).as_dict())
    items.append(Item(_eid(cycle, "subject_sale_history", pid), "subject_sale_history", "Recorded sales of the subject parcel",
                      "official_public_record", {**sale_src, "record_key": f"PARCEL_ID={pid}"}, {"sales": col["own_sales"]},
                      "extracted_from_official_file", ["contrary evidence disclosure"]).as_dict())
    items.append(Item(_eid(cycle, "assessment_peer_set", pid), "assessment_peer_set", "County values of similar homes in the same peer group",
                      "official_public_record", {**roll_src, "record_key": f"peer group {col['subject'].get('NBRHD_CD')}"},
                      {k: col["peers"].get(k) for k in ("peers", "median_value_per_sqft", "subject_value_per_sqft", "ratio")},
                      "derived_by_deterministic_code", ["assessment uniformity indication"]).as_dict())
    if find:
        items.append(Item(_eid(cycle, "upstream_screen", find.get("case_id", "")), "upstream_screen", "Find screening result (not evidence for the county)",
                          "claimos_find", {"run_id": (find.get("source") or {}).get("run_id"), "found_at": (find.get("source") or {}).get("found_at"),
                                           "roll_file": (find.get("source") or {}).get("roll_file")},
                          {"tier": find.get("tier"), "defensible_value": (find.get("estimate") or {}).get("defensible_value"),
                           "annual_savings": (find.get("estimate") or {}).get("annual_savings")},
                          "reverified" if not val["versus_find"]["material_change"] else "superseded_by_evidence_analysis",
                          ["routing only"], ["a screening estimate, never cited to the county"], county_facing=False).as_dict())
    for sub in inp.get("homeowner_submissions") or []:
        items.append(_submission_item(cycle, sub))
    matrix = build_matrix(appeal.get("appeal_type"), a, val, items, inp, intake, rules)
    tasks = homeowner_tasks(matrix, inp, deadlines, cycle)
    gen = _generate(base, col, a, val, items, fm, inp, intake, cdir, rdir, today, cos)
    gen["internal"] = render_internal(base, col, a, val, items, matrix, rules, deadlines, intake, tasks, inp)
    return _finish(base, run_id, started, "completed", errors, rules, deadlines, items, a, val, matrix, tasks, gen,
                   inp, intake, cdir, rdir, ctx)


def _petitioner(inp: dict, intake: dict) -> str:
    auth = inp.get("authorization") or {}
    if auth.get("status") == "signed" and auth.get("signer_name") and not intake.get("authorization_is_test") \
            and not any(b["code"] == "I11" for b in intake["blockers"]):
        return auth.get("owner_name") or auth["signer_name"]
    if ((inp.get("find") or {}).get("outreach") or {}).get("owner_suppressed"):
        return "Withheld until the owner's authorization is reviewed"
    return "Not yet confirmed"


def _generate(base, col, a, val, items, fm, inp, intake, cdir, rdir, today, cos) -> dict:
    sub = inp.get("submission") or {}
    redactions = [x for x in inp.get("redactions") or [] if isinstance(x, str) and x.strip()]
    petitioner = _petitioner(inp, intake)
    synthetic = bool(inp.get("synthetic"))
    refs = {"authorization": {k: (inp.get("authorization") or {}).get(k) for k in ("status", "instrument", "signed_at")}}
    draft = build_report(base, col, a, val, items, fm, {"number": 0, "fingerprint": "0" * 64}, "2000-01-01", petitioner, sub, synthetic, refs)
    draft.resolve()
    draft.redact(redactions)
    fingerprint = sha256_obj({"text": draft.text(), "code": __version__})
    vfile = cdir / "versions.json"
    versions = json.loads(vfile.read_text()) if vfile.exists() else {}
    if fingerprint not in versions:
        versions[fingerprint] = {"version": len(versions) + 1, "report_date": today.isoformat(), "first_run": rdir.name}
        _write(vfile, json.dumps(versions, indent=1))
    version = versions[fingerprint]["version"]
    report_date = versions[fingerprint]["report_date"]
    doc = build_report(base, col, a, val, items, fm, {"number": version, "fingerprint": fingerprint}, report_date, petitioner, sub, synthetic, refs)
    unresolved = doc.resolve()
    redacted = doc.redact(redactions)
    pdf, info = rdir / "packet.pdf", None
    try:
        info = to_pdf(doc, pdf, f"Version {version} / fingerprint {fingerprint[:12]}", doc.title, base["appeal"]["cycle_id"])
    except ImportError:
        pdf = None
    validation = validate(doc, pdf, info, base, col, a, val, fm, sub, redactions, unresolved, cos)
    md = to_markdown(doc)
    _write(rdir / "packet.md", md)
    _write(rdir / "packet.html", to_html(doc, doc.title))
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest() if pdf else sha256_text(md)
    return {"doc": doc, "pdf": pdf, "render": info, "validation": validation, "markdown": md, "sha256": sha, "version": version,
            "fingerprint": fingerprint, "redactions_applied": redacted, "submission": sub, "synthetic": synthetic, "report_date": report_date}


ALLOWED_UPLOADS = {"image/jpeg", "image/png", "image/heic", "application/pdf"}


def _submission_item(cycle: str, sub: dict) -> dict:
    lim, ver = [], "homeowner_statement_unverified"
    kind = sub.get("kind") or "statement"
    if kind != "statement":
        if sub.get("media_type") not in ALLOWED_UPLOADS:
            lim.append(f"file type {sub.get('media_type')!r} is not accepted; ask for JPEG, PNG, HEIC or PDF")
            ver = "rejected_file_type"
        if not sub.get("sha256") or not sub.get("file_ref"):
            lim.append("no stored file reference and checksum")
            ver = "rejected_missing_file"
        if sub.get("integrity") == "corrupt":
            lim.append("the stored file could not be opened")
            ver = "rejected_corrupt"
        if not sub.get("document_date"):
            lim.append("undated: cannot show the condition existed on 1 January")
        if ver == "homeowner_statement_unverified":
            ver = "homeowner_document_unverified"
    return Item(_eid(cycle, f"homeowner_{kind}", sub.get("id") or sha256_obj(sub)[:16]), f"homeowner_{kind}",
                sub.get("description") or f"Homeowner {kind}", "homeowner_upload" if kind != "statement" else "homeowner_statement",
                {"file_ref": sub.get("file_ref"), "sha256": sub.get("sha256"), "uploaded_at": sub.get("uploaded_at"),
                 "media_type": sub.get("media_type"), "local_path": sub.get("local_path") if ver == "homeowner_document_unverified" else None},
                {"document_date": sub.get("document_date"), "condition_date": sub.get("condition_date"), "statement": sub.get("statement_text"),
                 "asserts": sub.get("asserts"), "claimed": sub.get("claimed"), "include_in_packet": bool(sub.get("include_in_packet")),
                 "witness": sub.get("witness"), "witness_subject": sub.get("witness_subject"), "witness_address": sub.get("witness_address"),
                 "witness_phone": sub.get("witness_phone"), "supports": sub.get("supports")},
                ver, ["condition or characteristics claim"], lim + ["a homeowner statement is recorded as a statement until verified"],
                county_facing=ver in ("homeowner_document_unverified",)).as_dict()


def _auth_state(inp: dict, intake: dict) -> str:
    auth = inp.get("authorization") or {}
    if intake.get("authorization_is_test"):
        return "test_only"
    if any(b["code"] == "I11" for b in intake["blockers"]):
        return "invalid"
    if auth.get("status") == "signed":
        return "valid_for_filing"
    return "not_signed"


def _finish(base, run_id, started, processing, errors, rules, deadlines, items, a, val, matrix, tasks, gen,
            inp, intake, cdir, rdir, ctx, col=None):
    outcome = (val or {}).get("outcome") or "not_analyzed"
    required_missing = [r for r in matrix if r["required"] and r["status"] != "satisfied"]
    package_complete = processing == "completed" and intake["status"] == "accepted" and val is not None and not required_missing
    validation = (gen or {}).get("validation")
    reasons = []
    if processing != "completed":
        reasons.append("processing did not complete; this is not a finding on the merits")
    if intake["status"] != "accepted":
        reasons += [b["message"] for b in intake["blockers"]]
    reasons += [b["message"] for b in intake.get("file_blockers", [])]
    if required_missing:
        reasons += [f"required evidence missing: {r['requirement']}" for r in required_missing]
    if outcome != "supports_reduction":
        reasons.append(f"argument outcome is {outcome}")
    if validation and validation["status"] != "validated_against_configured_requirements":
        reasons.append("packet failed validation: " + "; ".join(c["detail"] for c in validation["checks"] if c["status"] == "fail")[:400])
    if gen and not gen.get("pdf"):
        reasons.append("no PDF was rendered")
    vf = (val or {}).get("versus_find") or {}
    if vf.get("material_change") and outcome == "supports_reduction":
        reasons.append(f"the supported value {vf.get('evidence_proposed_value'):,} differs materially from the value Qualify relied on "
                       f"({vf.get('find_defensible_value'):,}); Qualify must re-confirm the decision")
    pet = (deadlines or {}).get("petition_filing") or {}
    if pet.get("status") == "passed":
        reasons.append(f"petition deadline {pet.get('date')} has passed; a late petition needs a written good-cause request (R. 12D-9.015(14))")
    elif not pet.get("verified"):
        reasons.append("petition deadline is not verified from the county's own publication")
    if base.get("replay"):
        reasons.append(f"replay: deadlines judged as of {base['replay']['as_of']}, not today; never a basis for a real filing")
    ready = processing == "completed" and package_complete and outcome == "supports_reduction" and not reasons
    prior = inp.get("prior_review") or {}
    packet_hash = (gen or {}).get("sha256")
    review = {"human_review_required": True, "filing_approval_required": True, "status": "pending", "approved_for": [],
              "reviewed_packet_hash": None, "reviewed_by": None, "reviewed_at": None, "stale": False, "supersedes": None}
    if prior.get("packet_hash"):
        if prior["packet_hash"] == packet_hash and prior.get("reviewed_by"):
            review.update({"status": prior.get("status", "pending"), "reviewed_packet_hash": packet_hash,
                           "reviewed_by": prior.get("reviewed_by"), "reviewed_at": prior.get("reviewed_at"),
                           "approved_for": list(prior.get("approved_for") or []) if prior.get("status") == "approved" else []})
        elif prior["packet_hash"] != packet_hash:
            review.update({"stale": True, "supersedes": prior["packet_hash"],
                           "stale_reason": "the evidence changed after the last review; the earlier review does not cover this packet"})
    packet_meta = None
    fm = ctx["forum"]
    if gen:
        internal = gen["internal"] + "\n## Packet status\n\n" + ("DRAFT, release blocked until: " + "; ".join(gen["doc"].release_gaps) if gen["doc"].release_gaps
                                                                  else "Release identifiers present.") + "\n\nSections omitted:\n\n" + (
            "\n".join(f"- {o['section']}: {o['why']}" for o in gen["doc"].omitted) or "- none") + "\n\nTemplate defaults: " + (
            "; ".join(f"{k}: {v}" for k, v in ((gen.get("render") or {}).get("style") or {}).items())) + "\n" + "\n## Packet validation\n\n| Check | Status | Detail |\n|---|---|---|\n" + "\n".join(
            f"| {c['id']} | {c['status']} | {str(c['detail']).replace('|', '/')} |" for c in gen["validation"]["checks"]) + "\n"
        _write(rdir / "internal_review.md", internal)
        pdf = gen.get("pdf")
        packet_meta = {"version": gen["version"], "sha256": packet_hash, "content_hash": packet_hash, "fingerprint": gen["fingerprint"],
                       "format": "application/pdf" if pdf else "text/markdown", "pdf_path": str(pdf) if pdf else None,
                       "pages": (gen.get("render") or {}).get("pages"), "bytes": (gen.get("render") or {}).get("bytes"),
                       "path": str(pdf) if pdf else str(rdir / "packet.md"), "markdown_path": str(rdir / "packet.md"),
                       "html_path": str(rdir / "packet.html"), "internal_record_path": str(rdir / "internal_review.md"),
                       "internal_record_hash": sha256_text(internal), "title": gen["doc"].title,
                       "exhibits": [{k: e.get(k) for k in ("id", "title", "description", "date", "source", "supports", "page", "pages")} for e in gen["doc"].exhibits],
                       "redactions_applied": gen["redactions_applied"], "report_date": gen["report_date"], "synthetic": gen["synthetic"],
                       "draft": gen["doc"].draft, "release_gaps": gen["doc"].release_gaps, "omitted_sections": gen["doc"].omitted,
                       "county_facing": not gen["synthetic"], "contains_owner_contact_data": False}
    witness_gaps = [c["detail"] for c in (validation or {}).get("checks", []) if c["id"] == "V-WITNESS" and c["status"] != "pass"]
    rel = [f"packet is a draft until it has: {g}" for g in ((gen or {}).get("doc").release_gaps if gen else [])]
    manifest = None
    if fm.get("supported") == "packet":
        sub_d = dict((gen or {}).get("submission") or inp.get("submission") or {})
        sub_d.setdefault("hearing_format", (inp.get("appeal") or {}).get("hearing_format"))
        manifest = build_delivery(fm, deadlines or {}, packet_meta, review, sub_d,
                                  inp.get("delivery_events") or [], bool(inp.get("synthetic")),
                                  {"exchange_property_appraiser": witness_gaps + rel, "remote_vab_upload": rel, "hearing_copies": rel,
                                   "absent_petitioner_filing": rel})
    if manifest:
        _write(rdir / "delivery.json", json.dumps(manifest, indent=1, default=str))
    auth_state = _auth_state(inp, intake)
    rd = build_readiness(processing, intake, val, bool(gen), validation, review, {"state": auth_state}, tasks, manifest, package_complete)
    if processing == "failed":
        nxt = {"actor": "coordinator", "action": "retry_evidence", "reason": "; ".join(e["detail"] for e in errors)[:300]}
    elif intake["status"] == "blocked":
        nxt = {"actor": intake.get("route") or "operator", "action": "resolve_intake_blockers", "reason": reasons[0] if reasons else ""}
    elif fm.get("supported") == "legal_review_only":
        nxt = {"actor": "operator", "action": "refer_to_counsel", "reason": fm.get("notes")}
    elif outcome in ("does_not_support", "contradicted"):
        nxt = {"actor": "qualify", "action": "requalify", "reason": val["outcome_reason"]}
    elif outcome == "insufficient_evidence":
        nxt = {"actor": "operator", "action": "review_insufficient_evidence", "reason": val["outcome_reason"]}
    elif vf.get("material_change"):
        nxt = {"actor": "qualify", "action": "requalify", "reason": "the evidence analysis changed the value Qualify relied on; the original Qualify result is preserved"}
    elif tasks and any(t["blocking"] for t in tasks):
        nxt = {"actor": "homeowner", "action": "provide_requested_evidence", "reason": "required items are missing"}
    elif validation and validation["status"] != "validated_against_configured_requirements":
        nxt = {"actor": "operator", "action": "fix_packet_validation", "reason": reasons[0] if reasons else "validation failed"}
    elif ready:
        nxt = {"actor": "operator", "action": "review_packet_then_hand_to_file", "reason": "packet generated and validated; a person must review and approve this exact version"}
    else:
        nxt = {"actor": "operator", "action": "review_packet", "reason": reasons[0] if reasons else "review required"}
    res = {**base,
           "run": {"run_id": run_id, "started_at": started, "finished_at": now(), "processing_status": processing, "errors": errors,
                   "method_version": METHOD_VERSION, "code_version": __version__, "duplicate_of": None},
           "rules_applied": [{"id": r["id"], "status": r["status"], "source": r["source"], "section": r.get("section"),
                              "retrieved": r.get("retrieved")} for r in rules],
           "inventory": items,
           "analysis": a, "valuation": val,
           "requirements": matrix, "homeowner_tasks": tasks,
           "missing": [r["requirement"] for r in matrix if r["status"] != "satisfied"],
           "conclusions": {"package_complete": package_complete, "argument_support": outcome,
                           "filing_readiness": "ready_for_human_review" if ready else "not_ready", "not_ready_reasons": reasons},
           "deadlines": deadlines,
           "authorization": {"status": (inp.get("authorization") or {}).get("status"), "instrument": (inp.get("authorization") or {}).get("instrument"),
                             "document_ref": (inp.get("authorization") or {}).get("document_ref"), "state": auth_state,
                             "valid_for_filing": auth_state == "valid_for_filing"},
           "packet": packet_meta, "validation": validation, "readiness": rd,
           "delivery": {"path": str(rdir / "delivery.json"), "deliveries": {d["id"]: d["status"] for d in manifest["deliveries"]}} if manifest else None,
           "review": review, "next_action": nxt, "synthetic": bool(inp.get("synthetic"))}
    if gen:
        res["file_handoff"] = write_file_handoff(res, rdir, gen.get("pdf"), ctx.get("find") or {}, deadlines or {}, inp.get("verifications") or [])
    _write(rdir / "result.json", json.dumps(res, indent=1, default=str))
    _write(cdir / "current.json", json.dumps({"result": str(rdir / "result.json"), "packet_hash": packet_hash, "run_id": run_id,
                                              "at": now()}, indent=1))
    return res
