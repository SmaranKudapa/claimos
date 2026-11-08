from __future__ import annotations

import re
import statistics
from pathlib import Path

from .report import Doc, m
from .valuation import round_value

FORBIDDEN = [
    (r"\bappraisals?\b", "uses 'appraisal'; only a state-certified or licensed appraiser may issue one (s. 475.612)"),
    (r"\bappraised\b", "uses 'appraised'"),
    (r"\bcertified\b", "uses 'certified'"),
    (r"\blicensed\b", "uses 'licensed'"),
    (r"\bguarantee", "promises an outcome"),
    (r"\bwill (?:win|succeed|be granted|save)\b", "predicts an outcome"),
    (r"\b(?:filed|served|exchanged|accepted|submitted) (?:on|with|to)\b", "states a delivery that generation cannot establish"),
    (r"\bclearly\b|\bobviously\b|\bundeniabl", "overstated language"),
    (r"\bdelve|\brest assured\b|\bI hope\b|\bas an AI\b|\blanguage model\b", "chat-style filler"),
    (r"!", "exclamation mark"),
    (r"[\U0001F300-\U0001FAFF☀-➿]", "emoji or pictograph"),
]
PLACEHOLDERS = [r"\{\{", r"\}\}", r"\bTODO\b", r"\bTBD\b", r"lorem ipsum", r"\bnan\b", r"\bNaN\b", r"\bNone\b", r"\bundefined\b", r"\$-?nan"]
PRIVATE = [
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "email address"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "social security number pattern"),
    (r"\b(?:fil|agt|brd|dep|ses|org|evr)_[a-z0-9]{6,}", "internal system reference"),
    (r"\bev-[0-9a-f]{16}\b", "internal evidence id"),
    (r"\bsk_(?:live|test)_", "secret key"),
    (r"agentmail", "internal mailbox"),
    (r"\b(?:Find|Qualify|Sign up|Chase|Collect) (?:step|agent|desk|card)", "internal workflow name"),
    (r"\bP\(win\)|\bcontingency\b|\bcommission\b|\bour fee\b|\bannual savings\b", "commercial or internal estimate"),
]
PHONE = r"\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b"
MAX_PAGES, MAX_BYTES = 60, 20_000_000


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t)


def _check(out, cid, category, ok, detail, basis, severity="fail"):
    out.append({"id": cid, "category": category, "status": "pass" if ok else severity, "detail": detail, "basis": basis})


def pdf_text(path: Path) -> list[str]:
    from pypdf import PdfReader
    r = PdfReader(str(path))
    return [_norm(p.extract_text() or "") for p in r.pages]


def validate(doc: Doc, pdf: Path | None, render_info: dict | None, base: dict, col: dict, a: dict | None, val: dict, forum: dict,
             submission: dict, redactions: list[str], unresolved: list[str], cost_of_sale: dict | None) -> dict:
    out: list[dict] = []
    ap = base["appeal"]
    s = col["subject"]
    cv = val["county_values"]
    text = _norm(doc.text())
    pages = []
    if pdf and pdf.exists():
        pages = pdf_text(pdf)
    full = " ".join(pages) if pages else text
    _check(out, "V-GEN-PDF", "format", bool(pages), f"PDF rendered with {len(pages)} pages" if pages else "no PDF was rendered", "CO-FMT-01")
    first = pages[0] if pages else text[:4000]
    for label, needle in (("parcel", ap["parcel_id"]), ("tax year", f"Assessment year {ap['tax_year']}"), ("authority", (forum.get("authority") or "?").upper()),
                          ("address", str(s.get("PHY_ADDR1") or "?")), ("party", "Submitting party"),
                          ("valuation date", f"January 1, {ap['tax_year']}")):
        _check(out, f"V-ID-{label.replace(' ', '_').upper()}", "identity", needle in first, f"{label} on the identification page: {needle}",
               "FL-HRG-02 cover page" if label in ("parcel", "party") else "internal")
    pn = submission.get("petition_number")
    _check(out, "V-ID-PETITION", "identity", (pn in first) if pn else ("Pending (not yet assigned)" in first),
           f"petition number shown as {pn or 'pending'}; no number is invented", "FL-HRG-02")
    gaps = getattr(doc, "release_gaps", [])
    _check(out, "V-RELEASE", "identity", not gaps, "every identifier needed for release is present" if not gaps else
           "marked DRAFT, release blocked until: " + "; ".join(gaps), "template", "warn")
    _check(out, "V-VAL-JV", "values", m(cv["just_value"]) in full, f"county just value {m(cv['just_value'])} appears as on the roll", "internal")
    supports = val["outcome"] == "supports_reduction" and bool(a and a.get("selected"))
    if supports:
        _check(out, "V-VAL-REQ", "values", m(val["proposed_just_value"]) in first, f"requested value {m(val['proposed_just_value'])} on the identification page", "internal")
        sel = a["selected"]
        bad = []
        for i, c in enumerate(sel):
            ad = c["adjustments"]
            if sum(ad.values()) != c["net_adjustment"]:
                bad.append(f"sale {i + 1} adjustments do not sum to the net")
            if c["sale_price"] + c["net_adjustment"] != c["indicated_value"]:
                bad.append(f"sale {i + 1} price plus net does not equal the adjusted price")
            if abs(round(c["sale_price"] * (c["time_factor"] - 1)) - ad["time"]) > max(3, 0.0005 * c["sale_price"]):
                bad.append(f"sale {i + 1} time adjustment does not match its factor")
            if c["sale_month"] >= f"{ap['tax_year']}-01":
                bad.append(f"sale {i + 1} is not before the valuation date")
            if c.get("qualification_code") not in ("01", "02"):
                bad.append(f"sale {i + 1} is not county-qualified")
        _check(out, "V-CALC-COMPS", "calculation", not bad, "; ".join(bad) or f"{len(sel)} sales recomputed: adjustments, adjusted prices, dates and qualification",
               "FL-VAL-01, FL-ADM-04")
        eff = int(s.get("EFF_YR_BLT") or 0)
        flagged = sum(1 for c in sel if c.get("flags"))
        gmax = max(c["gross_adjustment_pct"] for c in sel)
        gap = max(abs((c.get("effective_year_built") or eff) - eff) for c in sel)
        weak = []
        if flagged * 2 >= len(sel):
            weak.append(f"{flagged} of {len(sel)} sales need large adjustments")
        if gmax > 0.30:
            weak.append(f"the largest gross adjustment is {gmax:.0%} of price")
        if gap > 10:
            weak.append(f"a sale is {gap} years apart in effective age, which is not adjusted for")
        _check(out, "V-COMPS-QUALITY", "calculation", not weak, "comparable sales are close to the subject" if not weak else
               "weak comparable set for a hearing: " + "; ".join(weak), "internal", "warn")
        med = statistics.median(c["indicated_value"] for c in sel)
        _check(out, "V-CALC-MEDIAN", "calculation", abs(med - val["market_value_indication"]) <= 1,
               f"median of adjusted prices {med:,.0f} vs reported {val['market_value_indication']:,}", "internal")
        jvi = val["just_value_indications"]
        if cost_of_sale:
            exp = round(val["market_value_indication"] * (1 - cost_of_sale["rate"]))
            got = (jvi.get("market_less_cost_of_sale") or {}).get("value")
            _check(out, "V-CALC-COS", "calculation", got is not None and abs(exp - got) <= 1,
                   f"cost of sale {cost_of_sale['rate']:.0%} from DR-493 applied once: {exp:,} vs {got}", "FL-VAL-05")
        else:
            _check(out, "V-CALC-COS", "calculation", False, "no verified DR-493 cost-of-sale rate is configured for this county and year; "
                   "the just value rests on the measured level alone", "FL-VAL-05", "warn")
        lvl = jvi.get("market_at_county_level")
        if lvl:
            exp_l = round(val["market_value_indication"] * val["county_level"])
            _check(out, "V-CALC-LEVEL", "calculation", abs(exp_l - lvl["value"]) <= 2,
                   f"measured-ratio conversion applied once: {exp_l:,} vs {lvl['value']:,}", "FL-VAL-05")
        unsupported = sorted({k for c in sel for k, amt in c["adjustments"].items()
                              if amt and not ((c.get("adjustment_detail") or {}).get(k) or {}).get("support")})
        _check(out, "V-ADJ-SUPPORT", "calculation", not unsupported, "every non-zero adjustment states its basis and support" if not unsupported else
               f"adjustments without a stated basis: {', '.join(unsupported)}", "internal")
        lat = val.get("later_sales") or {}
        _check(out, "V-LATER-CONFLICT", "calculation", not lat.get("conflict"),
               "sales after January 1 do not contradict the request" if not lat.get("conflict") else
               f"{lat['contrary']} of {lat['count']} similar sales after January 1 point to the county's value or higher", "FL-POST-01", "warn")
        prim = [v["value"] for v in jvi.values() if v.get("role") in ("statutory conversion", "alternative conversion")]
        exp = round_value(max(prim)) if prim else None
        above = val.get("cross_checks_above_request") or []
        _check(out, "V-CROSS-CHECK", "calculation", not above, "every cross-check is at or below the requested value" if not above else
               f"cross-checks point higher than the request: {', '.join(x.replace('_', ' ') for x in above)}", "internal", "warn")
        _check(out, "V-CALC-PROPOSED", "calculation", exp == val["proposed_just_value"] and val["effects"]["just_value_reduction"] == cv["just_value"] - exp,
               f"requested value is the highest indication rounded to $100 ({exp:,}); reduction {cv['just_value'] - exp:,}", "internal")
    _check(out, "V-EXH-REFS", "exhibits", not unresolved, "every exhibit reference resolves" if not unresolved else f"unresolved references: {unresolved}", "internal")
    if pages and render_info:
        miss = []
        for e in doc.exhibits:
            p = e.get("page")
            if not p or p > len(pages) or f"{e['id']}: {e['title'][:20]}" not in pages[p - 1]:
                miss.append(f"{e['id']} not found on page {p}")
        _check(out, "V-EXH-PAGES", "exhibits", not miss, "; ".join(miss) or f"{len(doc.exhibits)} exhibits found on the pages the index gives",
               "FL-EVX-01 evidence list")
        labels = [o["label"] for o in render_info.get("outline") or []]
        _check(out, "V-EXH-BOOKMARKS", "format", all(any(lbl.startswith(e["id"] + ":") for lbl in labels) for e in doc.exhibits),
               f"{len(labels)} bookmarks, one per section and exhibit", "CO-FMT-01")
        foot = [i + 1 for i, t in enumerate(pages) if f"Page {i + 1} of {len(pages)}" not in t]
        _check(out, "V-FMT-PAGENUM", "format", not foot, "every page numbered 'Page N of T'" if not foot else f"pages without a correct number: {foot}",
               "FL-HRG-02 sequential page numbers")
        _check(out, "V-FMT-SIZE", "format", len(pages) <= MAX_PAGES and render_info["bytes"] <= MAX_BYTES,
               f"{len(pages)} pages, {render_info['bytes']:,} bytes (internal limits {MAX_PAGES} pages, {MAX_BYTES:,} bytes; county limits unknown)", "CO-FMT-02")
        from pypdf import PdfReader
        r = PdfReader(str(pdf))
        sizes = {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages}
        _check(out, "V-FMT-LETTER", "format", sizes == {(612, 792)}, f"page sizes {sorted(sizes)}", "CO-FMT-01")
        thin = [i + 1 for i, t in enumerate(pages) if len(t) < 60]
        _check(out, "V-FMT-TEXT", "format", not thin, "text is selectable on every page" if not thin else f"pages with almost no text: {thin}", "internal")
        meta = r.metadata or {}
        _check(out, "V-FMT-META", "format", bool(meta.get("/Title")), f"document title '{meta.get('/Title')}'", "internal", "warn")
    for pat, why in FORBIDDEN:
        hit = re.search(pat, full, re.I if pat.startswith(r"\b") else 0)
        _check(out, "V-TEXT-CLAIMS", "language", not hit, why + (f": '{full[max(0, hit.start() - 30):hit.end() + 30]}'" if hit else ""), "FL-475-01, FL-SCOPE-01")
    hits = [p for p in PLACEHOLDERS if re.search(p, full)]
    _check(out, "V-TEXT-PLACEHOLDER", "language", not hits, "no template placeholders or missing values" if not hits else f"found {hits}", "internal")
    prep = "Claim OS software" in first and "Not reviewed at the time of generation" in first
    _check(out, "V-TEXT-PREPARER", "disclosure", prep, "preparer is software; no human review is claimed", "CO-AI-01")
    for pat, why in PRIVATE:
        hit = re.search(pat, full)
        _check(out, "V-PRIVACY", "privacy", not hit, f"no {why}" if not hit else f"{why} found: '{full[max(0, hit.start() - 20):hit.end() + 20]}'", "FL-CONF-01")
    phones = [p for p in re.findall(PHONE, full) if p != submission.get("contact_phone")]
    _check(out, "V-PRIVACY", "privacy", not phones, "no telephone numbers other than the supplied contact number" if not phones else f"telephone numbers found: {phones}", "FL-CONF-01")
    leaks = [r for r in redactions if r and (r in full or r in text)]
    _check(out, "V-REDACT", "privacy", not leaks, f"{len(redactions)} redactions removed from the text layer" if not leaks else f"redacted text still present: {len(leaks)} item(s)",
           "FL-CONF-01")
    limit = (forum.get("county") or {}).get("upload_limit_bytes")
    if limit and render_info:
        _check(out, "V-FMT-COUNTY-SIZE", "format", render_info["bytes"] <= limit, f"{render_info['bytes']:,} bytes against the county's {limit:,}-byte upload limit",
               "county local procedures")
    wit = [b for b in doc.blocks if b[0] == "table" and b[4] == "wit"]
    gaps = [r[0].split(",")[0] for b in wit for r in b[2] if "address to be added" in r[0]]
    _check(out, "V-WITNESS", "delivery", not gaps, "every witness has a name, address and subject" if not gaps else
           f"witness address missing for {', '.join(gaps)}; the exchange needs it (R. 12D-9.020)", "FL-EVX-08", "warn")
    cover_missing = [k for k in ("petition_number", "contact_phone") if not submission.get(k)]
    _check(out, "V-FMT-COVER", "delivery", not cover_missing,
           "cover page has petition number and telephone for a remote-hearing upload" if not cover_missing else
           f"before any remote-hearing upload add: {', '.join(cover_missing)}", "FL-HRG-02", "warn")
    if pages:
        heads = [b[1] for b in doc.blocks if b[0] == "h1"] + [f"{e['id']}: {e['title']}" for e in doc.exhibits]
        orphans = []
        for i, t in enumerate(pages):
            body = re.sub(r"(DRAFT - NOT FOR SUBMISSION \| )?Parcel \S+ \| \d{4} \| Page \d+ of \d+", "", t).strip()
            if any(body.endswith(h) for h in heads):
                orphans.append(i + 1)
        _check(out, "V-LAYOUT-ORPHAN", "presentation", not orphans, "no heading is stranded at the bottom of a page" if not orphans else
               f"heading stranded at the bottom of page(s) {orphans}", "CO-FMT-01")
        sparse = [i + 1 for i, t in enumerate(pages[:-1]) if len(t) < 500]
        _check(out, "V-LAYOUT-SPARSE", "presentation", not sparse, "no mostly empty pages before the last" if not sparse else
               f"mostly empty page(s): {sparse}", "CO-FMT-01", "warn")
    for c in out:
        c["kind"] = "presentation" if c["category"] in ("format", "presentation") else "substance"
    fails = [c for c in out if c["status"] == "fail"]
    warns = [c for c in out if c["status"] == "warn"]
    part = {k: "passed" if not [c for c in fails if c["kind"] == k] else "failed" for k in ("presentation", "substance")}
    return {"status": "validated_against_configured_requirements" if not fails else "failed", "failures": len(fails), "warnings": len(warns),
            "presentation": part["presentation"], "substance": part["substance"],
            "checks": out, "scope": "Checks Claim OS's configured requirements: presentation (layout, pagination, readability) and substance "
                                    "(identity, arithmetic, exhibits, language, privacy) must both pass. It does not establish that a board will accept "
                                    "or admit the evidence."}
