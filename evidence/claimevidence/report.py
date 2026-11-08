from __future__ import annotations

import datetime as dt
import re
import statistics

USE = {"001": "single-family residence", "004": "condominium unit"}
FIELD_LABEL = {"TOT_LVG_AREA": "Living area (sq ft)", "ACT_YR_BLT": "Actual year built", "EFF_YR_BLT": "Effective year built",
               "NO_BULDNG": "Buildings", "LND_SQFOOT": "Land area (sq ft)"}


def m(v):
    return "-" if v is None else f"${v:,.0f}"


def n(v):
    return "-" if v is None else f"{v:,.0f}"


def y(v):
    return "-" if v is None else f"{int(v)}"


def signed(v):
    return "-" if v is None else (f"+${v:,.0f}" if v >= 0 else f"-${-v:,.0f}")


def words(k: int) -> str:
    return ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"][k] if 0 <= k <= 10 else f"{k:,}"


def date_long(iso: str | None) -> str:
    if not iso:
        return "-"
    d = dt.date.fromisoformat(str(iso)[:10])
    return f"{d:%B} {d.day}, {d.year}"


def month_long(ym: str | None) -> str:
    if not ym:
        return "-"
    d = dt.date.fromisoformat(f"{ym}-01")
    return f"{d:%B %Y}"


def date_short(iso: str | None) -> str:
    if not iso:
        return "Date not established"
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{d:%b} {d.day}, {d.year}"


def mon(ym: str | None) -> str:
    if not ym:
        return "-"
    d = dt.date.fromisoformat(f"{str(ym)[:7]}-01")
    return f"{d:%b} {d.year}"


def source_line(f: dict) -> str:
    return (f"Florida Department of Revenue, {f.get('kind')} file for the {f.get('roll_stage') or ''} roll, published "
            f"{date_short(f.get('published'))}, retrieved {date_short(f.get('retrieved_at'))}, SHA-256 {str(f.get('sha256') or '')[:16]}")


LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class Doc:
    def __init__(self, title: str, case_label: str):
        self.title = title
        self.case_label = case_label
        self.blocks: list[tuple] = []
        self.exhibits: list[dict] = []
        self.draft = False
        self.release_gaps: list[str] = []
        self.omitted: list[dict] = []
        self.report_date = None

    def add(self, *b):
        self.blocks.append(b)

    def omit(self, section: str, why: str):
        self.omitted.append({"section": section, "why": why})

    @staticmethod
    def ref(key: str) -> str:
        return "{{ex:%s}}" % key

    def exhibit(self, key: str, title: str, description: str, date: str, source: str, supports: str):
        n = len(self.exhibits)
        eid = f"Exhibit {LETTERS[n] if n < 26 else 'Z' + str(n - 25)}"
        iso = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", str(date or "")))
        self.exhibits.append({"key": key, "id": eid, "title": title, "description": description, "date": date_short(date) if iso else date,
                              "date_iso": str(date)[:10] if iso else None, "source": source,
                              "supports": supports, "page": None, "pages": None})
        self.add("exhibit", key, eid, title)

    def resolve(self) -> list[str]:
        ids = {e["key"]: e["id"] for e in self.exhibits}
        missing = set()

        def sub(text):
            def rep(mo):
                k = mo.group(1)
                if k not in ids:
                    missing.add(k)
                    return mo.group(0)
                return ids[k]
            return re.sub(r"\{\{ex:([a-z0-9_]+)\}\}", rep, text)

        def walk(x):
            if isinstance(x, str):
                return sub(x)
            if isinstance(x, list):
                return [walk(v) for v in x]
            if isinstance(x, tuple):
                return tuple(walk(v) for v in x)
            return x

        self.blocks = [walk(b) for b in self.blocks]
        return sorted(missing)

    def redact(self, secrets: list[str]) -> int:
        count = 0
        secrets = sorted({x for x in secrets or [] if isinstance(x, str) and x.strip()}, key=len, reverse=True)

        def walk(x):
            nonlocal count
            if isinstance(x, str):
                for sec in secrets:
                    if sec in x:
                        count += x.count(sec)
                        x = x.replace(sec, "[redacted]")
                return x
            if isinstance(x, list):
                return [walk(v) for v in x]
            if isinstance(x, tuple):
                return tuple(walk(v) for v in x)
            return x

        self.blocks = [walk(b) for b in self.blocks]
        for e in self.exhibits:
            for k in ("title", "description", "source", "supports"):
                e[k] = walk(e[k])
        return count

    def text(self) -> str:
        out = []

        def walk(x):
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    walk(v)
        walk(self.blocks)
        walk([[e[k] for k in ("id", "title", "description", "date", "source", "supports")] for e in self.exhibits])
        return "\n".join(out)


def rng(vals, fmt) -> str:
    vals = [v for v in vals if v is not None]
    if not vals:
        return "-"
    lo, hi = min(vals), max(vals)
    return fmt(lo) if lo == hi else f"{fmt(lo)} to {fmt(hi)}"


def release_gaps(petitioner: str, submission: dict, supports: bool) -> list[str]:
    out = []
    if not supports:
        out.append("a supported requested value")
    if petitioner.startswith(("Not yet", "Withheld", "Pending")):
        out.append("verified petitioner name (signed authorization)")
    if not submission.get("petition_number"):
        out.append("petition number")
    if not submission.get("contact_phone"):
        out.append("contact telephone")
    if not submission.get("submitting_party"):
        out.append("submitting party name and role")
    return out



def homeowner_view(items: list[dict]) -> list[dict]:
    out = []
    for i in items:
        if not i["kind"].startswith("homeowner_"):
            continue
        f = i.get("facts") or {}
        s = i.get("source") or {}
        out.append({"evidence_id": i["evidence_id"], "kind": i["kind"].removeprefix("homeowner_"), "label": i["title"],
                    "document_date": f.get("document_date"), "condition_date": f.get("condition_date"), "statement": f.get("statement"),
                    "claimed": f.get("claimed") or {}, "sha256": s.get("sha256"), "image_path": s.get("local_path"),
                    "county_facing": bool(i.get("county_facing")), "include_statement": bool(f.get("include_in_packet")),
                    "witness": f.get("witness"), "witness_subject": f.get("witness_subject"), "witness_address": f.get("witness_address"),
                    "witness_phone": f.get("witness_phone"), "supports": f.get("supports")})
    return out


def build(base: dict, col: dict, a: dict | None, val: dict, items: list[dict], forum: dict, version: dict, generated_on: str,
          petitioner: str, submission: dict, synthetic: bool = False, refs: dict | None = None) -> Doc:
    s = col["subject"]
    ap = base["appeal"]
    year = ap["tax_year"]
    files = {f["kind"]: f for f in col["files"]}
    cv = val["county_values"]
    sel = (a or {}).get("selected") or []
    supports = val["outcome"] == "supports_reduction" and bool(sel)
    use = USE.get(str(s.get("DOR_UC") or "").zfill(3), "property")
    owner = homeowner_view(items)
    refs = refs or {}
    R = Doc.ref
    zipc = str(s.get("PHY_ZIPCD") or "").split(".")[0]
    addr = ", ".join(x for x in (s.get("PHY_ADDR1"), s.get("PHY_CITY")) if x) + (f", FL {zipc}" if zipc else ", FL")
    authority = forum.get("authority") or "the receiving authority"
    county = (forum.get("county") or {}).get("county") or "the"
    jvi = val.get("just_value_indications") or {}
    later = val.get("later_sales") or {}
    bridge = val.get("bridge") or {}
    cos = val.get("cost_of_sale")
    recon = (a or {}).get("reconciliation") or {}
    witnesses = [o for o in owner if o.get("witness")]
    vdate = date_long(f"{year}-01-01")
    title = "Petitioner's evidence submission" if supports else "Evidence review, not for submission"
    d = Doc(("TEST FIXTURE, NOT FOR SUBMISSION. " if synthetic else "") + title, f"Parcel {ap['parcel_id']} | {year}")
    d.report_date = generated_on
    gaps = release_gaps(petitioner, submission, supports)
    d.release_gaps = gaps
    d.draft = bool(gaps) or synthetic

    if synthetic:
        d.add("draft", "TEST FIXTURE, NOT FOR SUBMISSION. Built from test records; it must never be sent to a county.")
    if d.draft and not synthetic:
        d.add("draft", "DRAFT \u2014 NOT FOR SUBMISSION. Missing before release: " + "; ".join(gaps) + ".")
    quasi = forum.get("kind") == "administrative_quasi_judicial"
    if supports:
        d.add("court", f"{'BEFORE' if quasi else 'TO'} THE {authority.upper()}")
        d.add("title", "PETITIONER'S EVIDENCE SUBMISSION")
        d.add("title", f"{year} PROPERTY VALUE PETITION")
    else:
        d.add("court", authority.upper())
        d.add("title", "EVIDENCE REVIEW \u2014 NOT FOR SUBMISSION")
        d.add("title", f"{year} PROPERTY VALUE REVIEW")
    wit_contact = "; ".join(w["witness"] + (f", {w['witness_phone']}" if w.get("witness_phone") else ", telephone pending") for w in witnesses)
    meta = [("Petitioner", petitioner),
            ("Property address", addr),
            ("Parcel/folio number", ap["parcel_id"]),
            ("Petition number", submission.get("petition_number") or "Pending (not yet assigned)"),
            ("Assessment year", str(year)),
            ("Valuation date", vdate),
            ("Submitting party", submission.get("submitting_party") or "Petitioner (name and role pending)"),
            ("Contact telephone", submission.get("contact_phone") or "Pending"),
            ("Witness contact information", wit_contact or "No witnesses identified"),
            ("Value challenged", f"{year} just value of {m(cv['just_value'])}"),
            ("Value requested", f"Just value of {m(val['proposed_just_value'])}" if supports else "No value is requested. The evidence does not support one."),
            ("Report date and version", f"{date_long(generated_on)}; version {version['number']}, content fingerprint {version['fingerprint'][:12]}")]
    d.add("meta", meta)
    d.add("note", "Prepared by Claim OS software from the public records listed in the evidence index; the text and figures are produced by fixed "
                  "code, not written by hand. Not reviewed at the time of generation: review and approval are recorded separately against this "
                  "version. No appraiser, real estate broker or attorney prepared or reviewed it.")
    d.add("pagebreak")

    d.add("h1", "1. Statement of the case and requested determination")
    d.add("h2", "Property and issue")
    d.add("p", f"This submission concerns the {year} valuation of {addr}, parcel {ap['parcel_id']}, as of {vdate}. The county's {year} roll "
               f"reports a just value of {m(cv['just_value'])} ({R('roll')}). " + ("The petitioner contends that this figure exceeds the property's just value. "
               if supports else "The question reviewed is whether this figure exceeds the property's just value. ") + "Florida law equates just value with "
               "market value and requires the net proceeds of sale, after the usual costs of sale, to be considered (Section 4).")
    if supports:
        prices = [c["sale_price"] for c in sel]
        same_size = all(abs(c["size_diff_pct"]) < 0.10 for c in sel)
        near_age = all(c["effective_age_gap"] is not None and abs(c["effective_age_gap"]) <= 3 for c in sel)
        where = "in the subject's county neighborhood" if all(c["location"].startswith("same county neighborhood") for c in sel) else "in the subject's market area"
        traits = [where] + (["within 10% of its living area"] if same_size else []) + (["within three years of its effective year built"] if near_age else [])
        d.add("h2", "Principal evidence")
        d.add("p", f"The analysis relies on {words(len(sel))} qualified sales recorded by the county before January 1, {year}, at "
                   f"{rng(prices, m)} ({R('sales')}). The sales are " + ", ".join(traits) + ". Material differences are addressed in "
                   f"Section 5, with calculations in {R('adjustments')}. The county's own values for these sold homes and for similar homes "
                   f"are used as cross-checks ({R('sales')}, {R('peers')}).")
        d.add("h2", "Supported conclusion")
        conv = []
        if "market_less_cost_of_sale" in jvi:
            conv.append(f"{m(jvi['market_less_cost_of_sale']['value'])} after the county's {cos['rate']:.0%} cost-of-sale figure")
        conv.append(f"{m(jvi['market_at_county_level']['value'])} at the county's measured ratio of just value to sale price")
        d.add("p", f"The median adjusted sale indicates a market value of {m(val['market_value_indication'])}. Converted to just value, that is "
                   + " or ".join(conv) + f". The analysis supports a just value of {m(val['proposed_just_value'])}, the higher conversion rounded "
                   "to the nearest $100 (Section 6).")
        quals = []
        k = sum(1 for c in sel if c.get("new_construction"))
        if k:
            quals.append(f"{words(k)} of the {words(len(sel))} sales are new construction, and builder incentives or upgrades are not in public records")
        quals.append("the subject's interior condition and quality were not inspected and are not in the county's public data")
        if any(abs(c["time_factor"] - 1) > 0.03 for c in sel):
            quals.append("the time adjustment rests on a county-wide price index")
        d.add("h2", "Material qualification")
        d.add("p", "The conclusion is qualified because " + "; ".join(quals) + ". Section 7 assesses these points and the contrary evidence.")
        d.add("h2", "Requested determination")
        d.add("p", f"The petitioner asks the board to set the {year} just value at {m(val['proposed_just_value'])}. Assessed and taxable values "
                   "follow from that just value under any exemptions and caps; they are not argued separately.")
    else:
        d.add("h2", "Result")
        d.add("p", f"The evidence gathered does not support a requested value. Reason: {val['outcome_reason']}. No value is requested, and the "
                   "case returns for review.")
    auth = refs.get("authorization") or {}
    d.add("h2", "Related filings")
    d.add("table", ["Document", "Status", "Where it is"],
          [["Petition to the Value Adjustment Board (Form DR-486)",
            f"Petition {submission['petition_number']}" if submission.get("petition_number") else "Not yet filed",
            "Filed separately with the clerk; the clerk assigns the petition number"],
           ["Authorization to represent the owner (Form DR-486POA or written authorization)",
            "Signed; held in the case record" if auth.get("status") == "signed" else "Not yet signed",
            "Goes with the petition, not with this evidence"]],
          [3.0, 1.8, 2.7], "refs")

    d.add("h1", "2. Evidence index")
    d.add("index")

    d.add("h1", "3. Subject property facts and disputed issues")
    contrary = {}
    for o in owner:
        for field, claimed in (o.get("claimed") or {}).items():
            contrary.setdefault(field, []).append((o, claimed))

    def con(field):
        return "; ".join(f"Owner states {n(c) if isinstance(c, (int, float)) else c} (not verified)" for _, c in contrary.get(field, [])) or "No contrary information"

    facts = [["Property type", f"{use[:1].upper() + use[1:]} (use code {s.get('DOR_UC')})", "No contrary information", R("roll")],
             ["Living area (sq ft)", n(s.get("TOT_LVG_AREA")), con("TOT_LVG_AREA"), R("roll")],
             ["Lot size (sq ft)", n(s.get("LND_SQFOOT")) if s.get("LND_SQFOOT") else "Not stated on the roll", con("LND_SQFOOT"), R("roll")],
             ["Year built, actual / effective", f"{y(s.get('ACT_YR_BLT'))} / {y(s.get('EFF_YR_BLT'))}", con("ACT_YR_BLT"), R("roll")],
             ["Land value", m(s.get("LND_VAL")), "No contrary information", R("roll")],
             ["Special features (improvements other than the main building)", m(s.get("SPEC_FEAT_VAL")), "No contrary information", R("roll")],
             ["Condition and interior quality", "Not in the county's public data", "Not evaluated", "Not available"],
             ["Just value", m(cv["just_value"]), "Disputed: see Section 6", R("roll")],
             ["Assessed value, school / non-school", f"{m(cv['assessed_value_school'])} / {m(cv['assessed_value_non_school'])}", "Follows just value", R("roll")],
             ["Taxable value, school / non-school", f"{m(cv['taxable_value_school'])} / {m(cv['taxable_value_non_school'])}", "Follows just value", R("roll")],
             ["Homestead exemption", "Yes" if cv.get("homestead") else "No", "No contrary information", R("roll")]]
    d.add("table", ["Characteristic", "Official record", "Verified contrary information, if any", "Source"], facts, [2.2, 1.9, 1.9, 0.9], "facts")
    disputed = [(f, v) for f, v in contrary.items()]
    if disputed:
        for field, claims in disputed:
            label = FIELD_LABEL.get(field, field)
            for o, claimed in claims:
                rec = s.get(field)
                d.add("h2", label)
                d.add("p", f"The county records {n(rec) if isinstance(rec, (int, float)) else rec}. The owner states "
                           f"{n(claimed) if isinstance(claimed, (int, float)) else claimed}; that statement has not been independently verified. "
                           f"The difference matters because {label.lower()} enters the comparison directly. The analysis uses the county's figure "
                           "until a measurement, permit or survey confirms the owner's.")
    else:
        d.add("p", "No fact in the county's record is disputed in this submission. Condition and interior quality are not in the county's "
                   "public data and were not inspected.")
    if cv.get("homestead"):
        d.add("p", "The property has a homestead exemption. Its assessed value is capped below just value, so a lower just value changes the "
                   "assessed value only if it falls below the capped amount.")

    d.add("h1", "4. Valuation framework")
    fw = [f"Real property is valued as of January 1 of the tax year. § 192.042(1), Fla. Stat. (2025). The sales here are moved to {vdate}.",
          "Just value means market value; the property appraiser must consider, among other factors, the present cash value and the net proceeds "
          "of sale after the usual costs of sale. § 193.011(1), (8), Fla. Stat. (2025). The analysis estimates market value from sales and "
          "converts it to just value (Section 6).",
          "The board reviews whether the property appraiser's just value is supported; the petitioner must show by a preponderance of the "
          "evidence that it does not represent just value. Fla. Admin. Code R. 12D-9.027(2)(b)1.; § 194.301, Fla. Stat. (2026).",
          "The board may consider assessments among comparable properties within homogeneous areas or neighborhoods. § 194.034(5), Fla. Stat. "
          "(2026). The county's own values for similar homes are offered as a cross-check."]
    if cos:
        fw.append(f"The {county} County Property Appraiser reports on Department of Revenue Form DR-493 for the {year} roll a {cos['rate']:.0%} "
                  "adjustment to recorded sale prices for this property class. That form and the Department's 2026 VAB training, which advises "
                  "applying the figure once to unadjusted sales, are guidance rather than statute.")
    if later.get("count"):
        fw.append("No statute or rule addresses sales after January 1. A 2008 Department of Revenue bulletin (PTO 08-02) treats them as a check on "
                  "the January 1 value alongside earlier sales; they are used that way here (Section 7).")
    fw.append("Selection and adjustment follow common residential valuation practice, for example IAAO and Fannie Mae guidance on "
              "comparable-sale adjustments. That guidance is a methodological benchmark, not Florida law.")
    d.add("bullets", fw)

    if supports:
        d.add("h1", "5. Comparable sales analysis")
        d.add("h2", "5.1 Selection")
        counts = a.get("exclusion_counts") or {}
        months = sorted(c["sale_month"] for c in sel)
        d.add("p", f"Search area: the subject's county neighborhood, widening to the county's broader neighborhood and market-area codes only if needed. Period: "
                   f"the {a['params']['lookback_months']} months before {vdate}. Property type: {use}s (use code {s.get('DOR_UC')}). Sources: the "
                   f"Department of Revenue's {year} roll (NAL) and sales (SDF) files ({R('roll')}, {R('sales')}). Criteria: sales the county "
                   "qualified as arm's length (codes 01 and 02), one building, living area within about 25%, effective year built within 15 "
                   "years, county land value within a factor of about 1.65, and a county-value-to-price ratio inside the county's normal range.")
        d.add("p", f"Result: {a['candidates_considered']:,} qualified sales were considered and {a['candidates_usable']:,} met the criteria. The "
                   f"{words(len(sel))} most similar were used, sold {mon(months[0])} to {mon(months[-1])}. Sales were ranked by similarity, never by price. "
                   + (("Sales failing each rule (a sale can fail more than one): " + ", ".join(f"{k.lower()} {v:,}" for k, v in counts.items())
                       + f". The closest excluded sales are listed in {R('excluded')}. ") if counts else "")
                   + "The search covers the county's recorded sales file only; it is not a survey of unrecorded sales or listings.")
        d.add("h2", "5.2 Property comparison")
        chunks = [sel[i:i + 3] for i in range(0, len(sel), 3)]
        for ci, chunk in enumerate(chunks):
            off = ci * 3
            head = ["Characteristic", "Subject"] + [f"Sale {off + j + 1}" for j in range(len(chunk))]
            rows = [["Address", s.get("PHY_ADDR1") or ""] + [c["address"] for c in chunk],
                    ["Parcel", ap["parcel_id"]] + [c["parcel_id"] for c in chunk],
                    ["Sale date", "-"] + [mon(c["sale_month"]) for c in chunk],
                    ["Sale price", "-"] + [m(c["sale_price"]) for c in chunk],
                    ["Living area (sq ft)", n(s.get("TOT_LVG_AREA"))] + [n(c["sqft"]) for c in chunk],
                    ["Lot size (sq ft)", n(s.get("LND_SQFOOT")) if s.get("LND_SQFOOT") else "Not stated"] + [n(c.get("lot_sqft")) if c.get("lot_sqft") else "Not stated" for c in chunk],
                    ["Year built / effective", f"{y(s.get('ACT_YR_BLT'))} / {y(s.get('EFF_YR_BLT'))}"] + [f"{y(c['actual_year_built'])} / {y(c['effective_year_built'])}" for c in chunk],
                    ["Condition", "Not evaluated"] + ["Not evaluated" for _ in chunk],
                    ["Location", f"Neighborhood {s.get('NBRHD_ORIG') or '-'}"] + [(f"Neighborhood {c['neighborhood']}" if c.get("neighborhood") else c["location"].capitalize())
                                                                    + (" (same)" if c["location"].startswith("same county neighborhood") else "") for c in chunk],
                    ["Special features value", m(s.get("SPEC_FEAT_VAL"))] + [m(c["county_special_features_value"]) for c in chunk],
                    ["Transaction", "-"] + [f"Qualified (code {c['qualification_code']})" + ("; new construction" if c.get("new_construction") else "") for c in chunk],
                    ["County just value", m(cv["just_value"])] + [m(c["county_just_value"]) for c in chunk],
                    ["Source", R("roll")] + [R("sales") for _ in chunk]]
            d.add("table", head, rows, [1.6, 1.3] + [1.3] * len(chunk), f"grid{ci}")
        d.add("h2", "5.3 Adjustments")
        d.add("p", "Sign convention: a positive adjustment raises a sale's price because the sale is inferior to the subject in that respect, or "
                   "sold when prices were lower than on January 1; a negative adjustment lowers it for the opposite reason. The conversion from "
                   "market value to just value is a separate step in Section 6 and is not part of these adjustments.")
        basis = {"time": f"County monthly price index ({R('level')})", "land": f"County land values ({R('roll')}, {R('sales')})",
                 "special_features": f"County feature values ({R('roll')}, {R('sales')})", "living_area": f"Rate extracted from these sales ({R('adjustments')})"}
        for ci, chunk in enumerate(chunks):
            off = ci * 3
            head = ["Adjustment item"] + [f"Sale {off + j + 1}" for j in range(len(chunk))] + ["Basis or source"]
            rows = [["Unadjusted sale price"] + [m(c["sale_price"]) for c in chunk] + [R("sales")],
                    ["Time to January 1"] + [signed(c["adjustments"]["time"]) for c in chunk] + [basis["time"]],
                    ["Land"] + [signed(c["adjustments"]["land"]) for c in chunk] + [basis["land"]],
                    ["Special features"] + [signed(c["adjustments"]["special_features"]) for c in chunk] + [basis["special_features"]],
                    ["Living area"] + [signed(c["adjustments"]["living_area"]) for c in chunk] + [basis["living_area"]],
                    ["Age, condition and quality"] + ["Not evaluated" for _ in chunk] + ["Not in public records; controlled by selection"],
                    ["Net adjustment"] + [signed(c["net_adjustment"]) for c in chunk] + ["Sum of the rows above"],
                    ["Adjusted price"] + [m(c["indicated_value"]) for c in chunk] + [R("adjustments")],
                    ["Gross adjustment"] + [f"{m(sum(abs(c['adjustments'][k] or 0) for k in ('time', 'land', 'special_features', 'living_area')))} "
                                            f"({c['gross_adjustment_pct']:.1%})" for c in chunk] + ["Sum of absolute adjustments; sets the weights in Section 6"]]
            d.add("table", head, rows, [1.6] + [1.15] * len(chunk) + [2.0], f"adjg{ci}")
        d.add("h2", "5.4 Adjustment explanations")
        explained = 0
        for key, label in (("time", "Time"), ("land", "Land"), ("special_features", "Special features"), ("living_area", "Living area")):
            amts = [c["adjustments"][key] for c in sel]
            if not any(amts):
                continue
            explained += 1
            det = sel[0]["adjustment_detail"][key]
            if key == "time":
                diff = f"The sales closed {mon(months[0])} to {mon(months[-1])}; the valuation date is {vdate}."
                big = max(sel, key=lambda c: abs(c["adjustments"]["time"]))
                calc = ("sale price \u00d7 (time factor - 1); factors " + rng([c["time_factor"] for c in sel], lambda v: f"{v:.4f}")
                        + f". Sale {sel.index(big) + 1}: {m(big['sale_price'])} \u00d7 ({big['time_factor']:.4f} - 1) = {signed(big['adjustments']['time'])}")
                lim = (a.get("time_index_note") or "") + f"; it is a county-wide trend, not a measurement for this neighborhood (index in {R('level')})"
            elif key == "land":
                diff = "County land values differ: subject " + m(s.get("LND_VAL")) + ", sales " + rng([c["county_land_value"] for c in sel], m) + "."
                calc = f"(subject land value - sale land value) / {val['county_level']:.4f}"
                lim = "county land values are mass-valuation estimates; location premiums not captured in them are not adjusted"
            elif key == "special_features":
                diff = "County special-feature values differ: subject " + m(s.get("SPEC_FEAT_VAL")) + ", sales " + rng([c["county_special_features_value"] for c in sel], m) + "."
                calc = f"(subject feature value - sale feature value) / {val['county_level']:.4f}"
                lim = "the county does not publish what each feature is; values are mass-valuation estimates"
            else:
                diff = "Living areas differ: subject " + n(s.get("TOT_LVG_AREA")) + " sq ft, sales " + rng([c["sqft"] for c in sel], n) + " sq ft."
                calc = f"(subject sq ft - sale sq ft) \u00d7 ${a['building_rate_per_sqft']:,.2f} per sq ft"
                lim = "the rate is extracted from a small set of sales"
            d.add("h2", label)
            d.add("table", ["Element", "Detail"], [["Difference", diff], ["Basis", det["support"].capitalize()], ["Calculation", calc],
                                                  ["Result", rng(amts, signed) + " across the sales" + ("" if all(amts) else " (zero where there is no difference)")],
                                                  ["Limitation", lim[0].upper() + lim[1:]]], [1.2, 5.8], f"adjx_{key}")
        if not explained:
            d.add("p", "No adjustment was needed: the sales match the subject on every adjusted characteristic.")

        d.add("h1", "6. Reconciliation and requested value")
        ordered = sorted(sel, key=lambda c: c["gross_adjustment_pct"])
        least = [f"Sale {sel.index(c) + 1}" for c in ordered[:2]]
        most = [f"Sale {sel.index(c) + 1}" for c in ordered[-2:]] if len(ordered) > 3 else []
        wx, med_v = recon.get("weighted_cross_check"), val["market_value_indication"]
        near = wx is not None and med_v and abs(wx - med_v) <= 0.02 * med_v
        d.add("p", f"The adjusted prices range from {m((a.get('indication') or {}).get('low'))} to {m((a.get('indication') or {}).get('high'))}. "
                   f"The median, {m(med_v)}, is used because each sale then counts once and no single sale can move the "
                   f"result far. {' and '.join(least)} needed the least adjustment relative to price and deserve the most weight"
                   + (f"; {' and '.join(most)} needed the most and deserve less" if most else "") + ". Weighting each sale by the inverse of its gross "
                   f"adjustment gives {m(wx)}" + (", close to the median, so the choice of method does not drive the result." if near else
                                                 f", {abs(wx - med_v) / med_v:.1%} from the median; the reviewer should weigh which is more reliable."))
        d.add("p", "Market value is then converted to just value as a separate step, using either the county's DR-493 cost-of-sale figure or the "
                   "county's measured ratio of just value to sale price. The two are alternatives and are never combined. The request uses the "
                   "higher of the two results, the one more favorable to the county, rounded to the nearest $100.")
        steps = [["1", "Adjusted sale prices (Section 5.3)", "Median of " + rng([c["indicated_value"] for c in sel], m), m(val["market_value_indication"]), R("adjustments")],
                 ["2", "Cross-check: weighting by least adjustment", "Weighted mean of the adjusted prices", m(recon.get("weighted_cross_check")), R("adjustments")]]
        if "market_less_cost_of_sale" in jvi:
            steps.append(["3", "Just value at the DR-493 cost of sale", f"{m(val['market_value_indication'])} x (1 - {cos['rate']:.0%})",
                          m(jvi["market_less_cost_of_sale"]["value"]), R("level")])
        steps.append([str(len(steps) + 1), "Just value at the county's measured ratio", f"{m(val['market_value_indication'])} x {val['county_level']:.4f}",
                      m(jvi["market_at_county_level"]["value"]), R("level")])
        steps.append([str(len(steps) + 1), "Requested just value", "Higher of the conversions, rounded to $100", m(val["proposed_just_value"]), "-"])
        if "comparables_own_assessment_ratio" in jvi:
            steps.append([str(len(steps) + 1), "Cross-check: county's own ratio for these sales", jvi["comparables_own_assessment_ratio"]["formula"].replace("market value indication ", "$"),
                          m(jvi["comparables_own_assessment_ratio"]["value"]), R("sales")])
        if "assessment_uniformity" in jvi:
            steps.append([str(len(steps) + 1), "Cross-check: similar homes' county value", jvi["assessment_uniformity"]["formula"].replace("peer median ", ""),
                          m(jvi["assessment_uniformity"]["value"]), R("peers")])
        steps.append([str(len(steps) + 1), "County just value", f"{year} roll", m(cv["just_value"]), R("roll")])
        d.add("table", ["Step", "Item", "Input or calculation", "Result", "Supporting reference"], steps, [0.4, 2.2, 2.3, 1.0, 1.1], "calc")
        g = bridge.get("gap") or {}
        above = val.get("cross_checks_above_request") or []
        d.add("p", f"Of the {m(g.get('total'))} difference between the county's value and the request, {m(g.get('county_value_above_market_indication'))} "
                   f"is the amount by which the county's value exceeds the market indication before any conversion, {m(g.get('just_value_conversion'))} is the conversion from "
                   f"market value to just value, and {m(g.get('rounding'))} is rounding."
                   + (f" {' and '.join(x.replace('_', ' ') for x in above).capitalize()} point higher than the request and are left to the reviewer." if above else ""))
        sens = recon.get("sensitivity") or {}
        d.add("p", f"Sensitivity: the unadjusted prices have a median of {m(sens.get('recorded_prices_median'))}, and without the time adjustment "
                   f"the median adjusted price is {m(sens.get('without_time_adjustment_median'))}. At the county's measured ratio its "
                   f"{m(cv['just_value'])} corresponds to a market value of {m(round(cv['just_value'] / val['county_level']))}"
                   + (", above each of these." if round(cv["just_value"] / val["county_level"]) > max(sens.get("recorded_prices_median") or 0,
                                                                                                  sens.get("without_time_adjustment_median") or 0) else "."))

    d.add("h1", ("7" if supports else "5") + ". Material limitations and contrary evidence")
    items_c = []
    if val.get("contradiction"):
        c = val["contradiction"]
        items_c.append(("The property's own sale", f"It sold in {month_long(c['sale_month'])} for {m(c['sale_price'])} ({R('history')}).",
                        "A qualified sale of the property itself before January 1 is direct evidence of its value.",
                        f"At the county's measured ratio it implies {m(c['implied_just_value'])}, which supports the county's value.",
                        "It defeats the request; no value is requested.", "Whether the sale had unusual terms is not known."))
    if later.get("count"):
        hi = max(later["sales"], key=lambda x: x["sale_price"])
        items_c.append(("Sales after January 1",
                        f"{words(later['count']).capitalize()} homes within 10% of the subject's size sold after January 1 for {rng([x['sale_price'] for x in later['sales']], m)}"
                        f"; the highest was {hi['address']} at {m(hi['sale_price'])} in {mon(hi['sale_month'])} ({R('later')}).",
                        ("Some of these prices exceed the requested value, and the higher ones approach or exceed the county's figure."
                         if supports else "Later prices can show whether the county's figure was in line with the market."),
                        "They are prices, which measure market value. Moved back to January 1 with the county index and put on the just-value basis "
                        f"at the county's ratio, they range from {rng([x['just_value_equivalent'] for x in later['sales']], m)} against the county's "
                        f"{m(cv['just_value'])}" + (f"; the highest corresponds to {m(hi['just_value_equivalent'])}" if hi else "") + ". "
                        + (f"Put the other way, the county's figure corresponds to a market value of {m(round(cv['just_value'] / val['county_level']))} at its "
                           f"own ratio, and every later price is below that." if max(x["sale_price"] for x in later["sales"]) < cv["just_value"] / val["county_level"]
                           else f"At its own ratio the county's figure corresponds to a market value of {m(round(cv['just_value'] / val['county_level']))}."),
                        (("They do not change the analysis: " if supports or not later["contrary"] else "No value is requested in any case; ")
                         + (f"{words(later['contrary'])} of them point to the county's value or higher."
                            if later["contrary"] else "none points to the county's value or higher.")),
                        "Their terms, condition and any builder incentives are not known, and the index after January 1 rests on fewer sales."))
    if a and a.get("systematic_bias"):
        items_c.append(("Age of the comparable sales", a["systematic_bias"].capitalize() + ".", "Older homes usually sell for less, so the indication would be too low.",
                        "Age is not adjusted because public data cannot support an age adjustment.", "It prevents a requested value.",
                        "A supported age or condition adjustment, or newer comparable sales, would be needed."))
    k = sum(1 for c in sel if c.get("new_construction"))
    if k and supports:
        new = [c for c in sel if c.get("new_construction")]
        old = [c for c in sel if not c.get("new_construction")]
        ratio = lambda cs: statistics.median(c["county_just_value"] / c["sale_price"] for c in cs if c.get("county_just_value") and c.get("sale_price"))
        if old:
            mn, mo = statistics.median(c["indicated_value"] for c in new), statistics.median(c["indicated_value"] for c in old)
            comp_txt = (f"After adjustment their median is {m(round(mn))}, against {m(round(mo))} for the {words(len(old))} resale{'s' if len(old) > 1 else ''} "
                        f"in the set ({abs(mn / mo - 1):.1%} apart). The county values them at a median {ratio(new):.1%} of price, against "
                        f"{ratio(old):.1%} for the resale{'s' if len(old) > 1 else ''}.")
            close = abs(mn / mo - 1) <= 0.05
        else:
            comp_txt = f"There is no resale in the set to compare with. The county values them at a median {ratio(new):.1%} of price."
            close = False
        items_c.append(("New-construction sales", f"{words(k).capitalize()} of the {words(len(sel))} sales were sold new by the builder.",
                        "Builder sales can include incentives, upgrades or lot premiums that make the recorded price differ from a resale price.",
                        comp_txt, "They are kept, with this qualification." if close else "They are kept, but the difference from resales needs review.",
                        "Incentives and upgrades are not in public records. Common valuation guidance prefers resales where enough exist."))
    if sel and a.get("time_index_note"):
        sens = recon.get("sensitivity", {}) or {}
        nt = sens.get("without_time_adjustment_median")
        if supports and nt and val.get("market_value_indication"):
            alt = round(nt * val["proposed_just_value"] / val["market_value_indication"])
            eff = (f"Without it, the same conversion gives about {m(alt)}, still below the county's {m(cv['just_value'])}; the conclusion does not depend on the index."
                   if alt < cv["just_value"] else f"Without it, the same conversion gives about {m(alt)}, at or above the county's value; the conclusion depends on the index.")
        else:
            eff = "No value is requested in any case."
        items_c.append(("Time adjustment", "Each sale is moved to January 1 with the county's monthly price index" + (f" ({R('level')})" if supports else "") + "; "
                        + str(a["time_index_note"]).replace("county-wide monthly index for this use; ", "") + ".",
                        "A noisy index can move adjusted prices up or down.",
                        f"Without any time adjustment the median adjusted price is {m(nt)}.", eff, "A neighborhood-level index is not available from public data."))
    for title_, ident, why, comp, effect, unres in items_c:
        d.add("h2", title_)
        d.add("table", ["Point", "Assessment"], [["Item", ident], ["Why it could matter", why], ["Comparability and relevance", comp],
                                               ["Effect on the analysis", effect], ["Unresolved", unres]], [1.7, 5.3], "contrary")
    d.add("p", "General limitations:")
    d.add("bullets", ["Interior condition, quality, view and renovations are not in the public files and are not adjusted for. No inspection was made.",
                      "Sales are as recorded and qualified by the county. Buyers and sellers were not contacted, and concessions are not known.",
                      "Location is compared by the county's neighborhood and market-area codes. Distance, waterfront and flood exposure are not measured."])

    cond = [o for o in owner if o["kind"] in ("photo", "repair_estimate", "inspection") and o["county_facing"]]
    if cond:
        d.add("h2", "Condition evidence")
        d.add("p", f"The owner supplied the documents below. They have not been independently verified. Property is valued as of {vdate}, so each "
                   "item shows the date the document was made and, separately, the date the condition is said to have existed. A repair estimate "
                   "states a cost to repair; it is not offered as a dollar-for-dollar reduction in value.")
        d.add("table", ["Item", "Document date", "Condition date", "Reference"],
              [[o["label"], o.get("document_date") or "Date not established", o.get("condition_date") or "Not stated", R(f"owner_{o['evidence_id']}")]
               for o in cond], [3.2, 1.2, 1.2, 1.0], "cond")

    if witnesses:
        d.add("h1", ("8" if supports else "6") + ". Witness evidence")
        d.add("table", ["Witness", "Role or firsthand knowledge", "Expected factual subjects", "Related exhibits"],
              [[f"{w['witness']}, {w.get('witness_address') or 'address to be added before the exchange'}", w.get("witness_role") or "Owner",
                w.get("witness_subject") or "The matters in this submission",
                ", ".join(R(f"owner_{o['evidence_id']}") for o in owner if o["county_facing"]) or "-"] for w in witnesses], [2.2, 1.4, 2.4, 1.0], "wit")
        d.add("p", "This summarizes expected testimony. No statement has been taken from any witness.")
    else:
        d.omit("Witness evidence", "no witness has been identified for this case")
    if not cond:
        d.omit("Condition evidence", "the owner has supplied no condition documents")
    if not supports:
        d.omit("Comparable sales analysis and reconciliation", "the evidence does not support a requested value")
    _exhibits(d, base, col, a, val, files, owner, supports)
    return d


def _exhibits(d, base, col, a, val, files, owner, supports):
    s = col["subject"]
    ap = base["appeal"]
    year = ap["tax_year"]
    roll_date = f"{year} {col.get('roll_stage') or ''} roll".replace("  ", " ")
    sel = (a or {}).get("selected") or []
    months = sorted(c["sale_month"] for c in sel)
    window = f"{mon(months[0])} to {mon(months[-1])}" if months else f"before January 1, {year}"
    nal, sdf = files["NAL"], files["SDF"]
    pub = lambda f: str(f.get("published") or "")[:10] or "Date not established"
    got = lambda f: date_short(f.get("retrieved_at"))
    d.exhibit("roll", "Subject property record", f"County roll record for the subject parcel ({roll_date})", pub(nal),
              f"Florida DOR NAL file, retrieved {got(nal)}", "Identity, values and characteristics")
    d.add("p", f"Source: {source_line(files['NAL'])}. Record key PARCEL_ID {ap['parcel_id']}.")
    fields = [("PARCEL_ID", "Parcel", ap["parcel_id"]), ("PHY_ADDR1", "Site address", s.get("PHY_ADDR1")), ("PHY_CITY", "City", s.get("PHY_CITY")),
              ("DOR_UC", "Use code", s.get("DOR_UC")), ("NBRHD_CD", "Neighborhood", s.get("NBRHD_ORIG")), ("JV", "Just value", m(s.get("JV"))),
              ("AV_SD", "Assessed value, school", m(s.get("AV_SD"))), ("AV_NSD", "Assessed value, non-school", m(s.get("AV_NSD"))),
              ("TV_SD", "Taxable value, school", m(s.get("TV_SD"))), ("TV_NSD", "Taxable value, non-school", m(s.get("TV_NSD"))),
              ("LND_VAL", "Land value", m(s.get("LND_VAL"))), ("SPEC_FEAT_VAL", "Special features value", m(s.get("SPEC_FEAT_VAL"))),
              ("TOT_LVG_AREA", "Living area (sq ft)", n(s.get("TOT_LVG_AREA"))), ("ACT_YR_BLT", "Actual year built", y(s.get("ACT_YR_BLT"))),
              ("EFF_YR_BLT", "Effective year built", y(s.get("EFF_YR_BLT")))]
    d.add("table", ["Field", "Meaning", "Value"], [[f, lbl, str(v if v is not None else "-")] for f, lbl, v in fields], [1.6, 2.6, 2.8], "fields")
    if supports:
        d.exhibit("sales", "Comparable-sale transaction records", f"Qualified sales used as comparables, {window}, with deed references and county values",
                  pub(sdf), f"Florida DOR SDF and NAL files, retrieved {got(sdf)}", "Sale prices, dates and characteristics")
        d.add("p", f"Source: {source_line(files['SDF'])}, joined to the NAL file for characteristics. Each is a qualified (code 01 or 02), "
                   f"improved, single-parcel sale recorded before January 1, {year}.")
        d.add("table", ["No.", "Parcel", "Address", "Date", "Price", "Deed", "Code", "Sq ft", "County value", "Value / price"],
              [[str(i + 1), c["parcel_id"], c["address"], mon(c["sale_month"]), m(c["sale_price"]),
                (f"OR {c['record']['or_book']}/{c['record']['or_page']}" if c["record"].get("or_book") else (c["record"].get("clerk_no") or "-")),
                c["qualification_code"] or "-", n(c["sqft"]), m(c["county_just_value"]),
                f"{c['county_just_value'] / c['sale_price']:.1%}" if c.get("county_just_value") and c.get("sale_price") else "-"] for i, c in enumerate(sel)],
              [0.34, 0.98, 1.2, 0.74, 0.72, 0.8, 0.42, 0.45, 0.75, 0.58], "sales")
        d.exhibit("adjustments", "Adjustment calculations", "Adjustment of each sale to the subject, with formulas", d.report_date,
                  "Claim OS calculation from Exhibits A, B and D", "Adjusted price of each sale")
        rows = []
        for i, c in enumerate(sel):
            ad = c["adjustments"]
            rows.append([f"Sale {i + 1}", m(c["sale_price"]), signed(ad["time"]), signed(ad["land"]), signed(ad["special_features"]),
                         signed(ad["living_area"]), signed(c["net_adjustment"]), f"{c['gross_adjustment_pct']:.1%}", m(c["indicated_value"])])
        d.add("table", ["Sale", "Price", "Time", "Land", "Features", "Living area", "Net", "Gross", "Adjusted"], rows,
              [0.55, 0.85, 0.8, 0.8, 0.8, 0.85, 0.85, 0.5, 0.95], "adj")
        d.add("p", "Each adjustment, as calculated:")
        d.add("table", ["Sale", "Time", "Land", "Features", "Living area"],
              [[f"Sale {i + 1}"] + [c["adjustment_detail"][k]["formula"] for k in ("time", "land", "special_features", "living_area")]
               for i, c in enumerate(sel) if c.get("adjustment_detail")], [0.55, 1.75, 1.75, 1.6, 1.65], "adjf")
        d.add("p", "Support for each adjustment: " + " ".join(f"{k.replace('_', ' ').capitalize()}: {v['support']}." for k, v in
                                                           (sel[0].get("adjustment_detail") or {}).items()))
        d.add("bullets", [f"Not adjusted: {a['adjustment_basis']['not_adjusted']}.",
                          f"Building rate: ${a['building_rate_per_sqft']:,.2f} per sq ft, the {a['building_rate_basis']}.",
                          f"Reconciliation: {a['indication']['method']}, giving {m(a['indication']['market_value'])}."])
        d.exhibit("level", "Time index, cost of sale and measured ratio", "County time index, Form DR-493 cost of sale and the county's measured ratio",
                  pub(sdf), "Florida DOR SDF file; Form DR-493" + (f" ({val['cost_of_sale']['section']})" if val.get("cost_of_sale") else ""),
                  "Time adjustment and conversion to just value")
        d.add("p", f"Time index ({a.get('time_method')}), with the factor applied to each sale:")
        d.add("table", ["Sale", "Sale date", "Time factor", "Time-adjusted price"],
              [[f"Sale {i + 1}", mon(c["sale_month"]), f"{c['time_factor']:.4f}", m(round(c["sale_price"] * c["time_factor"]))] for i, c in enumerate(sel)],
              [1.0, 1.2, 1.2, 1.8], "time")
        ti = a.get("time_index_table") or {}
        if ti.get("rows"):
            d.add("p", f"The index is county-wide for use code {s.get('DOR_UC')}: the median sale price per sq ft of qualified sales in each month with at "
                       f"least {ti['min_sales']} sales, smoothed by a three-month rolling median. The January 1 level, ${ti['anchor_ppsf']:,.2f} per sq ft, "
                       "is interpolated between December and January. Each month's factor is the January 1 level divided by that month's smoothed value.")
            d.add("table", ["Month", "Qualified sales", "Median per sq ft", "Smoothed", "Factor to Jan 1"],
                  [[mon(r["month"]), n(r["sales"]), f"${r['median_ppsf']:,.2f}", f"${r['smoothed_ppsf']:,.2f}", f"{r['factor']:.4f}"] for r in ti["rows"]],
                  [1.2, 1.2, 1.4, 1.2, 1.2], "tindex")
        if val.get("cost_of_sale"):
            cs = val["cost_of_sale"]
            d.add("p", f"Cost of sale: {cs['rate']:.0%}, as reported by the property appraiser on Form DR-493 for the {year} roll "
                       f"(Florida Department of Revenue, {cs['section']}, {cs['source']}). The sales above are recorded prices with no cost-of-sale deduction, so it is applied once.")
        d.add("p", f"Measured level: {val['county_level']:.4f}, the {a.get('level_source')}.")
    else:
        d.exhibit("sales", "Comparable-sale transaction records", f"Recorded sales considered, {window}", pub(sdf),
                  f"Florida DOR SDF file, retrieved {got(sdf)}", "Why no value is requested")
        why = (a or {}).get("reliability_reason")
        d.add("p", f"Source: {source_line(files['SDF'])}, joined to the NAL file for characteristics.")
        if sel:
            d.add("p", f"The {words(len(sel))} most similar qualified sales found, ranked by similarity and not used:")
            d.add("table", ["Sale", "Address", "Date", "Price", "Sq ft", "Year built / effective", "Code"],
                  [[str(i + 1), c["address"], mon(c["sale_month"]), m(c["sale_price"]), n(c["sqft"]),
                    f"{y(c['actual_year_built'])} / {y(c['effective_year_built'])}", c["qualification_code"] or "-"] for i, c in enumerate(sel)],
                  [0.45, 2.0, 0.8, 1.0, 0.65, 1.2, 0.5], "sales")
        d.add("p", f"Why no value is requested: {val['outcome_reason']}." + (f" Comparable set: {why}." if why and why != val["outcome_reason"] else ""))
    peers = col.get("peers") or {}
    d.exhibit("peers", "Assessments of similar homes", f"County values of similar homes in the same neighborhood ({roll_date})", pub(nal),
              f"Florida DOR NAL file, retrieved {got(nal)}", "Uniformity, offered as support only")
    if peers.get("peers"):
        d.add("p", f"The subject is valued at ${peers['subject_value_per_sqft']:,.2f} per sq ft. The median for {peers['peers']} similar homes is "
                   f"${peers['median_value_per_sqft']:,.2f} ({peers['basis']})" + (f"; half of them fall between ${peers['quartiles_per_sqft'][0]:,.2f} and "
                   f"${peers['quartiles_per_sqft'][1]:,.2f}" if peers.get("quartiles_per_sqft") else "") + f". Listed below: {peers.get('examples_basis') or 'the closest in living area'}. "
                   f"Source: {source_line(files['NAL'])}.")
        d.add("table", ["Parcel", "Address", "Sq ft", "Just value", "Per sq ft"],
              [[e["parcel_id"], e["address"], n(e["sqft"]), m(e["county_just_value"]), f"${e['value_per_sqft']:,.2f}"] for e in peers.get("examples", [])[:10]],
              [1.3, 2.4, 0.8, 1.3, 1.0], "peers")
    else:
        d.add("p", "No similar homes were found in the same peer group within the size range.")
    d.exhibit("excluded", "Sales considered and not used", f"Closest sales that were not used, {window}, with the reason", pub(sdf),
              f"Florida DOR SDF file, retrieved {got(sdf)}", "Shows the selection was not one-sided")
    if a and a.get("excluded_nearest"):
        d.add("table", ["Address", "Date", "Price", "Reason not used"],
              [[e["address"], mon(e["sale_month"]), m(e["sale_price"]), "; ".join(r["detail"] for r in e["excluded_because"])] for e in a["excluded_nearest"][:12]],
              [1.8, 0.7, 0.9, 3.6], "excl")
    else:
        d.add("p", "No excluded sales to list.")
    d.exhibit("history", "Subject sale history", "The subject's recorded sales in the current sales file", pub(sdf),
              f"Florida DOR SDF file, retrieved {got(sdf)}", "Contrary evidence disclosed")
    own = col.get("own_sales") or []
    if own:
        d.add("table", ["Sale date", "Price", "Code", "Qualified", "Before Jan 1", "Deed"],
              [[mon(o["sale_month"]), m(o["sale_price"]), o["qualification_code"] or "-", "Yes" if o["qualified"] else "No", "Yes" if o["before_valuation_date"] else "No",
                (f"OR {o['record']['or_book']}/{o['record']['or_page']}" if o["record"].get("or_book") else (o["record"].get("clerk_no") or "-"))] for o in own],
              [1.0, 1.1, 0.6, 0.9, 1.0, 1.4], "own")
    else:
        d.add("p", "The sales file for this roll records no sale of the subject. Earlier sales, if any, are outside this file.")
    sub = (a or {}).get("subsequent_sales") or []
    lat = val.get("later_sales") or {}
    if lat.get("count"):
        d.exhibit("later", "Sales after January 1", "Similar homes sold after the valuation date, as a check", pub(sdf),
                  f"Florida DOR SDF file, retrieved {got(sdf)}", "Consistency of the January 1 indication")
        d.add("p", "Homes in the subject's neighborhood within 10% of its living area that sold after January 1. Each price is moved back to January 1 "
                   f"with the county index and multiplied by the county's measured ratio ({val['county_level']:.4f}) to compare with the subject's just value.")
        d.add("table", ["Address", "Sale date", "Price", "Time factor", "At Jan 1", "Just-value equivalent", "What it indicates"],
              [[x["address"], mon(x["sale_month"]), m(x["sale_price"]), f"{x['time_factor']:.4f}", m(x["time_adjusted_price"]), m(x["just_value_equivalent"]),
                x["relation"]] for x in lat["sales"]], [1.6, 0.7, 0.85, 0.7, 0.85, 1.0, 1.4], "later")
    elif sub:
        d.add("p", "Sales after January 1 among the comparable homes, disclosed and not used:")
        d.add("table", ["Address", "Parcel", "Sale date", "Price", "Sq ft"],
              [[x["address"], x["parcel_id"], mon(x["sale_month"]), m(x["sale_price"]), n(x["sqft"])] for x in sub], [2.2, 1.4, 0.8, 1.2, 0.8], "sub")
    for o in [o for o in owner if o["county_facing"]]:
        d.exhibit(f"owner_{o['evidence_id']}", o["label"], o["label"], o.get("document_date") or "Date not established", "Supplied by the owner, not verified",
                  o.get("supports") or ("Condition" if o["kind"] in ("photo", "repair_estimate", "inspection") else "Property facts"))
        d.add("p", f"Supplied by the owner and not independently verified. Document date: {date_short(o.get('document_date')) if o.get('document_date') else 'undated'}. "
                   f"Date the owner says the condition existed: {o.get('condition_date') or 'not stated'}. Original file SHA-256 {str(o.get('sha256') or '')[:16]}.")
        if o.get("image_path"):
            d.add("image", o["image_path"], f"{o['label']}. Shown as supplied; scaled to fit the page only.")
        else:
            d.add("p", "The original file is kept unaltered in the case record and goes with every submission copy.")
