import hashlib
import html
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen
from zoneinfo import ZoneInfo
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject, TextStringObject

FORM_URL = "https://floridarevenue.com/property/Documents/dr486.pdf"
ROUTES = {
    "lee": {"source_url": "https://www.leeclerk.org/departments/value-adjustment-board-vab/filing-a-petition", "methods": ["online", "mail", "in_person"]},
    "hendry": {"source_url": "https://www.hendryclerk.org/clerk-services/value-adjustment-board/", "methods": ["mail", "email", "fax"]},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def official_url(value, county):
    try:
        parsed = urlparse(value)
        hosts = {"floridarevenue.com", "www.floridarevenue.com"}
        hosts |= {"www.leeclerk.org", "leeclerk.org", "www.leepa.org", "leepa.org"} if county == "lee" else {"www.hendryclerk.org", "hendryclerk.org", "hendryprop.com", "www.hendryprop.com"}
        return parsed.scheme == "https" and parsed.hostname in hosts and not parsed.username and not parsed.password and parsed.port in (None, 443)
    except (ValueError, TypeError):
        return False


def load_handoff(path):
    raw = Path(path).read_text()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        blocks = re.findall(r"```json\s*([\s\S]*?)```", raw)
        if len(blocks) != 1:
            raise ValueError("Supply one JSON handoff or one board card containing a JSON block.")
        data = json.loads(blocks[0])
    if not isinstance(data, dict):
        raise ValueError("The handoff must be an object.")
    candidate = data.get("candidate", data)
    if not isinstance(candidate, dict) or candidate.get("schema_version") != 1 or candidate.get("desk") != "property_tax":
        raise ValueError("Expected Nick's FindCandidate schema version 1.")
    for key in ("case_id", "jurisdiction", "property", "owner", "source"):
        if not candidate.get(key):
            raise ValueError("Missing candidate field: " + key)
    if not isinstance(candidate["case_id"], str) or len(candidate["case_id"]) > 250:
        raise ValueError("Invalid stable case_id.")
    for key in ("jurisdiction", "property", "owner", "source"):
        if not isinstance(candidate[key], dict):
            raise ValueError("Invalid candidate object: " + key)
    year = candidate["jurisdiction"].get("tax_year")
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise ValueError("A valid assessment tax year is required.")
    if not candidate["property"].get("parcel_id") or not candidate["property"].get("address") or not candidate["owner"].get("name"):
        raise ValueError("Parcel, property address and owner-of-record name are required.")
    return data, candidate


def local_artifact(entry, root):
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise ValueError("A local artifact path and SHA-256 are required.")
    base = Path(root).resolve()
    path = (base / entry["path"]).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("Artifact must be a file inside the supplied case directory.")
    content = path.read_bytes()
    if not content or len(content) > 25_000_000 or digest(content) != entry.get("sha256"):
        raise ValueError("Artifact is empty, oversized, or has a mismatched SHA-256.")
    return {"path": str(path), "sha256": digest(content), "bytes": len(content)}


def assess(envelope, candidate, root, today=None):
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    cid = candidate["case_id"]
    jurisdiction = candidate["jurisdiction"]
    county = str(jurisdiction.get("county", "")).lower().removesuffix(" county").strip()
    holds, artifacts = [], []
    if jurisdiction.get("state") != "FL" or county not in ROUTES:
        holds.append("Unsupported jurisdiction: verify county filing instructions before preparing a submission.")
    if candidate.get("tier") not in ("strong", "possible"):
        holds.append("Find did not classify this case as strong or possible.")
    mailing = candidate["owner"].get("mailing_address")
    values = mailing.values() if isinstance(mailing, dict) else [mailing]
    if not any(isinstance(value, str) and value.strip() for value in values):
        holds.append("A mailing address for notices is required before operator review.")
    window = candidate.get("filing_window") or {}
    if not isinstance(window, dict):
        window = {}
    if window.get("status") == "closed":
        holds.append("Find marked the filing window closed. Demo include-closed overrides never authorize filing.")
    for label in ("qualification", "authorization", "evidence"):
        block = envelope.get(label)
        if not isinstance(block, dict) or block.get("case_id") != cid:
            holds.append(label + ": missing case-matched upstream handoff.")
            continue
        expected = {"qualification": "eligible", "authorization": "signed", "evidence": "complete"}[label]
        if block.get("status") != expected:
            holds.append(label + ": requires status " + expected + ".")
        if label == "qualification" and block.get("route") != "vab_value_appeal":
            holds.append("Qualify must confirm the supported vab_value_appeal route; other routes need a reviewed adapter.")
        if block.get("tax_year") != jurisdiction.get("tax_year"):
            holds.append(label + ": tax year does not match the candidate.")
        if label in ("authorization", "evidence"):
            try:
                artifacts.append({"kind": label, **local_artifact(block.get("artifact"), root)})
            except ValueError as error:
                holds.append(label + ": " + str(error))
        if label == "authorization" and not block.get("signer_name"):
            holds.append("authorization: the actual signer must be identified.")
    filing = envelope.get("filing", {})
    if not isinstance(filing, dict):
        filing = {}
    if filing.get("case_id") != cid or filing.get("tax_year") != jurisdiction.get("tax_year"):
        holds.append("Filing instructions must match this case and tax year.")
    if not official_url(filing.get("instructions_url"), county) or not official_url(filing.get("deadline_source_url"), county):
        holds.append("Official county/state instructions and deadline source URLs are required.")
    if filing.get("deadline_verified") is not True:
        holds.append("The actual petition deadline must be verified from the notice or clerk; Find's estimated date is insufficient.")
    try:
        deadline = date.fromisoformat(filing["deadline"])
        if deadline < today:
            holds.append("The verified filing deadline has passed; a separately reviewed late-filing procedure is required.")
    except (KeyError, TypeError, ValueError):
        holds.append("A valid verified filing deadline is required.")
    if filing.get("method") not in ROUTES.get(county, {}).get("methods", []):
        holds.append("Choose a filing method supported by the county's verified instructions.")
    if not isinstance(filing.get("fee_usd"), (int, float)) or isinstance(filing.get("fee_usd"), bool) or not math.isfinite(filing["fee_usd"]) or filing.get("fee_usd", -1) < 0 or filing.get("fee_verified") is not True:
        holds.append("The actual filing fee or documented exemption must be verified.")
    authorization = envelope.get("authorization") if isinstance(envelope.get("authorization"), dict) else {}
    if authorization.get("representation_mode") not in ("owner", "licensed_representative", "unlicensed_compensated", "unlicensed_uncompensated"):
        holds.append("The representation and signature route must be identified for DR-486.")
    if authorization.get("representation_mode") == "unlicensed_compensated" and authorization.get("authority_basis") not in ("taxpayer_signed_petition", "compliant_power_of_attorney"):
        holds.append("Compensated unlicensed representation requires the taxpayer-signed petition or an appropriately reviewed power of attorney.")
    if candidate["owner"].get("may_have_changed") and authorization.get("current_owner_verified") is not True:
        holds.append("Ownership may have changed after the roll; verify the current authorized owner.")
    return county, holds, artifacts


def fetch_form(path):
    with urlopen(FORM_URL, timeout=30) as response:
        if urlparse(response.geturl()).hostname not in ("floridarevenue.com", "www.floridarevenue.com"):
            raise ValueError("Official form redirected outside the verified state host.")
        content = response.read(2_000_001)
    if len(content) > 2_000_000 or not content.startswith(b"%PDF"):
        raise ValueError("Official form response is not a bounded PDF.")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(content)


def prepare(input_path, output_root, template):
    envelope, candidate = load_handoff(input_path)
    county, holds, artifacts = assess(envelope, candidate, Path(input_path).parent)
    key = digest(candidate["case_id"].encode())[:20]
    out = Path(output_root) / key
    out.mkdir(parents=True, exist_ok=True)
    prior = out / "manifest.json"
    if prior.exists() and json.loads(prior.read_text()).get("status") == "receipt_recorded":
        raise ValueError("A receipt already exists for this case; preserve it rather than preparing a duplicate filing.")
    reader = PdfReader(template)
    fields = reader.get_fields() or {}
    required = {"Tax Payer Name", "Mailing Address", "Parcel ID and Pyshical Address", "Real property Value", "Decrease"}
    if not required.issubset(fields):
        raise ValueError("The official form's field layout changed; review it before filling.")
    owner, prop = candidate["owner"], candidate["property"]
    mailing = owner.get("mailing_address", {})
    address = "\n".join(str(value) for value in mailing.values() if value) if isinstance(mailing, dict) else str(mailing)
    data = {"Tax Payer Name": str(owner.get("name", "")), "Mailing Address": address, "Parcel ID and Pyshical Address": str(prop.get("parcel_id", "")) + "\n" + str(prop.get("address", "")), "Real property Value": "/Yes", "Decrease": "/Yes"}
    if prop.get("use") == "single_family":
        data["Res 1-4 units"] = "/Yes"
    if isinstance(envelope.get("filing"), dict) and envelope["filing"].get("representative_name"):
        data["Representative"] = str(envelope["filing"]["representative_name"])
    writer = PdfWriter()
    writer.append(reader, pages=(0, min(2, len(reader.pages))))
    for annotation_ref in writer.pages[0].get("/Annots", []):
        annotation = annotation_ref.get_object()
        if annotation.get("/T") in data and annotation.get("/FT") == "/Tx":
            annotation[NameObject("/DA")] = TextStringObject("/Helv 0 Tf 0 g")
        if annotation.get("/T") in ("Mailing Address", "Parcel ID and Pyshical Address"):
            annotation[NameObject("/Ff")] = NumberObject(int(annotation.get("/Ff", 0)) | 4096)
    fitted = {name: (value, "/Helv", 0) if fields.get(name, {}).get("/FT") == "/Tx" else value for name, value in data.items()}
    writer.update_page_form_field_values(writer.pages[0], fitted, auto_regenerate=False)
    writer.add_metadata({"/Title": "DRAFT — " + candidate["case_id"], "/Subject": "Unsigned preparation copy; not filed"})
    for artifact in artifacts:
        source_path = Path(artifact["path"])
        destination = out / (artifact["kind"] + "-" + artifact["sha256"][:12] + source_path.suffix)
        destination.write_bytes(source_path.read_bytes())
        artifact["path"] = str(destination)
    pdf = out / "DRAFT-DR-486.pdf"
    writer.write(pdf)
    form_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    revision = re.search(r"R\.\s*(\d{2}/\d{2})", form_text)
    manifest = {"schema_version": 1, "step": "file", "case_id": candidate["case_id"], "status": "blocked" if holds else "ready_for_operator_review", "submitted": False, "jurisdiction": candidate["jurisdiction"], "property": prop, "holds": holds, "artifacts": artifacts, "petition": {"path": str(pdf), "sha256": digest(pdf.read_bytes()), "source_url": FORM_URL, "template_sha256": digest(Path(template).read_bytes()), "revision": revision.group(1) if revision else "unverified"}, "routing": ROUTES.get(county), "filing": envelope.get("filing", {}), "response_deadline": None, "input_sha256": digest(canonical(envelope)), "prepared_at": datetime.now(timezone.utc).isoformat()}
    if not revision:
        manifest["holds"].append("Official form revision could not be verified.")
        manifest["status"] = "blocked"
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (out / "petition-data.json").write_text(json.dumps(data, indent=2))
    items = "".join("<li>" + html.escape(item) + "</li>" for item in manifest["holds"])
    (out / "review.html").write_text('<!doctype html><meta charset="utf-8"><title>File · review</title><main style="font:16px system-ui;max-width:850px;margin:50px auto;line-height:1.7"><h1>File · ' + html.escape(candidate["case_id"]) + '</h1><p><strong>Unsigned preparation copy. Check the latest manifest and receipt ledger for filing status.</strong></p><p>Status: ' + manifest["status"] + '</p><ul>' + items + '</ul><p>Tax year: ' + html.escape(str(candidate["jurisdiction"].get("tax_year"))) + '</p><p><a href="DRAFT-DR-486.pdf">Open the filled draft</a></p><p>Signatures, clerk petition number and received date remain for the authorized parties.</p></main>')
    return manifest, out


def normalize_identifier(value):
    return re.sub(r"[^A-Za-z0-9]", "", str(value)).lower()


def notice_details(manifest_path, notice_path, response_due, receipt, case_id):
    if not notice_path or not response_due:
        raise ValueError("A notice and its explicit response date are both required.")
    manifest_path, notice_path = Path(manifest_path), Path(notice_path)
    if not notice_path.resolve().is_relative_to(manifest_path.parent.resolve()) or not notice_path.is_file():
        raise ValueError("Save the notice inside this case directory first.")
    content = notice_path.read_bytes()
    if not content or len(content) > 25_000_000:
        raise ValueError("Notice is empty or oversized.")
    body = "\n".join(page.extract_text() or "" for page in PdfReader(notice_path).pages) if content.startswith(b"%PDF") else content.decode("utf-8")
    normalized = normalize_identifier(body)
    references = [normalize_identifier(receipt[key]) for key in ("confirmation_id", "parcel_id")]
    if not any(reference and reference in normalized for reference in references):
        raise ValueError("Notice does not identify this case.")
    due = date.fromisoformat(response_due)
    choices = [due.isoformat(), due.strftime("%m/%d/%Y"), f"{due.month}/{due.day}/{due.year}", due.strftime("%B ") + str(due.day) + ", " + str(due.year)]
    if not any(re.search(r"(?<![0-9])" + re.escape(choice) + r"(?![0-9])", body, re.IGNORECASE) for choice in choices):
        raise ValueError("The supplied response deadline does not appear in the notice.")
    sha = digest(content)
    saved = manifest_path.parent / ("notice-" + sha[:16] + (".pdf" if content.startswith(b"%PDF") else ".txt"))
    return {"case_id": case_id, "status": "notice_recorded", "response_due": response_due, "timezone": "America/New_York", "path": str(saved), "sha256": sha, "recorded_at": datetime.now(timezone.utc).isoformat()}, content


def record_receipt(manifest_path, receipt_path, confirmation_id, parcel_id, notice_path=None, response_due=None):
    manifest_path, receipt_path = Path(manifest_path), Path(receipt_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") not in ("ready_for_operator_review", "receipt_recorded"):
        raise ValueError("Resolve filing holds before recording a submission receipt.")
    if not normalize_identifier(parcel_id) or normalize_identifier(parcel_id) != normalize_identifier(manifest["property"]["parcel_id"]):
        raise ValueError("Receipt parcel does not match this case.")
    if not normalize_identifier(confirmation_id) or not receipt_path.is_file():
        raise ValueError("A real receipt file and confirmation number are required.")
    if not receipt_path.resolve().is_relative_to(manifest_path.parent.resolve()):
        raise ValueError("Save the receipt inside this case directory first.")
    if bool(notice_path) != bool(response_due):
        raise ValueError("Supply both the notice artifact and its response date, or neither.")
    content = receipt_path.read_bytes()
    if not content or len(content) > 25_000_000:
        raise ValueError("Receipt is empty or oversized.")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(receipt_path).pages) if content.startswith(b"%PDF") else content.decode("utf-8")
    if normalize_identifier(confirmation_id) not in normalize_identifier(text) or normalize_identifier(parcel_id) not in normalize_identifier(text):
        raise ValueError("Receipt contents must identify both the confirmation number and parcel.")
    receipt_hash = digest(content)
    ledger_path = manifest_path.parent / "receipts.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text().splitlines()] if ledger_path.exists() else []
    notice, notice_content = None, None
    if response_due:
        notice, notice_content = notice_details(manifest_path, notice_path, response_due, {"confirmation_id": confirmation_id, "parcel_id": parcel_id}, manifest["case_id"])
    for row in ledger:
        if row["sha256"] == receipt_hash:
            if normalize_identifier(row["confirmation_id"]) != normalize_identifier(confirmation_id):
                raise ValueError("The saved receipt has a different confirmation number; review it instead of replacing it.")
            if notice:
                record_notice(manifest_path, notice_path, response_due)
            current = json.loads(manifest_path.read_text())
            return {**row, "response_due": current.get("response_deadline"), "notice": current.get("notice")}
    saved = manifest_path.parent / ("receipt-" + receipt_hash[:16] + (".pdf" if content.startswith(b"%PDF") else ".txt"))
    saved.write_bytes(content)
    if notice:
        Path(notice["path"]).write_bytes(notice_content)
        manifest["notice"] = notice
    deadline = response_due or manifest.get("response_deadline")
    row = {"case_id": manifest["case_id"], "status": "receipt_recorded", "confirmation_id": confirmation_id, "parcel_id": parcel_id, "path": str(saved), "sha256": receipt_hash, "recorded_at": datetime.now(timezone.utc).isoformat(), "response_due": deadline, "deadline_source_sha256": manifest.get("notice", {}).get("sha256"), "next_action": "verify_clerk_acceptance_and_fee_receipt" if deadline else "obtain_clerk_notice_and_response_deadline"}
    ledger.append(row)
    ledger_path.write_text("".join(json.dumps(item) + "\n" for item in ledger))
    manifest.update(status="receipt_recorded", receipt=row, response_deadline=deadline)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return {**row, "notice": manifest.get("notice")}


def record_notice(manifest_path, notice_path, response_due):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    receipt = manifest.get("receipt")
    if not isinstance(receipt, dict):
        raise ValueError("Record the case receipt before attaching its response notice.")
    notice, content = notice_details(manifest_path, notice_path, response_due, receipt, manifest["case_id"])
    Path(notice["path"]).write_bytes(content)
    receipt.update(response_due=response_due, deadline_source_sha256=notice["sha256"], next_action="verify_clerk_acceptance_and_fee_receipt")
    manifest.update(response_deadline=response_due, notice=notice, receipt=receipt)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return notice
