from __future__ import annotations

import datetime as dt
import re

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


def source_line(f: dict) -> str:
    return (f"Florida Department of Revenue, {f.get('kind')} file for the {f.get('roll_stage') or ''} roll, published "
            f"{str(f.get('published') or '')[:10]}, retrieved {str(f.get('retrieved_at') or '')[:10]}, SHA-256 {str(f.get('sha256') or '')[:16]}")


class Doc:
    def __init__(self, title: str, case_label: str):
        self.title = title
        self.case_label = case_label
        self.blocks: list[tuple] = []
        self.exhibits: list[dict] = []

    def add(self, *b):
        self.blocks.append(b)

    @staticmethod
    def ref(key: str) -> str:
        return "{{ex:%s}}" % key

    def exhibit(self, key: str, title: str, description: str, date: str, source: str, supports: str):
        eid = f"Exhibit {len(self.exhibits) + 1}"
        self.exhibits.append({"key": key, "id": eid, "title": title, "description": description, "date": date, "source": source,
                              "supports": supports, "page": None})
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
          petitioner: str, submission: dict, synthetic: bool = False) -> Doc:
    s = col["subject"]
    ap = base["appeal"]
    year = ap["tax_year"]
    files = {f["kind"]: f for f in col["files"]}
    cv = val["county_values"]
    ind = (a or {}).get("indication")
    supports = val["outcome"] == "supports_reduction" and bool(a and a.get("selected"))
    use = USE.get(str(s.get("DOR_UC") or "").zfill(3), "property")
    owner = homeowner_view(items)
    R = Doc.ref
    zipc = str(s.get("PHY_ZIPCD") or "").split(".")[0]
    addr = ", ".join(x for x in (s.get("PHY_ADDR1"), s.get("PHY_CITY")) if x) + (f", FL {zipc}" if zipc else ", FL")
    title = (forum.get("document") or "Evidence summary") if supports else "Evidence review, not for submission"
    d = Doc(("TEST FIXTURE, NOT FOR SUBMISSION. " if synthetic else "") + title, f"{ap['parcel_id']} / {year}")
    d.add("title", d.title)
    d.add("subtitle", f"{forum.get('authority')}, tax year {year}")
    witnesses = [o for o in owner if o.get("witness")]
    meta = [("Receiving authority", forum.get("authority") or "-"),
            ("Proceeding", forum.get("label") or "-"),
            ("Party submitting", "Petitioner"),
            ("Petitioner", petitioner),
            ("Property address", addr or "-"),
            ("Parcel", ap["parcel_id"]),
            ("Property type", use),
            ("Tax year", str(year)),
            ("Valuation date", date_long(f"{year}-01-01")),
            ("Petition number", submission.get("petition_number") or "Not yet assigned"),
            ("Contact telephone", submission.get("contact_phone") or "To be added before submission"),
            ("Off-site witnesses", "; ".join(w["witness"] + (f", {w['witness_phone']}" if w.get("witness_phone") else "") for w in witnesses)
             if witnesses else "No off-site witnesses"),
            ("Value challenged", f"{year} just value of {m(cv['just_value'])}"),
            ("Value requested", f"Just value of {m(val['proposed_just_value'])}" if supports else "No value is requested. The evidence does not support one."),
            ("Report date", date_long(generated_on)),
            ("Version", f"{version['number']}, content fingerprint {version['fingerprint'][:12]}"),
            ("Prepared by", "Claim OS software, from the public records listed in the evidence index. The text and figures are produced by fixed code, not written by hand."),
            ("Reviewed by", "Not reviewed at the time of generation. Review and approval are recorded separately against this version.")]
    d.add("meta", meta)
    d.add("note", "No appraiser, real estate broker or attorney prepared or reviewed this summary. It is submitted as the petitioner's evidence.")
    if not supports:
        d.add("note", "Not for submission. The evidence gathered does not support a lower value, so this review is kept for the case record only.")
    if synthetic:
        d.add("note", "This document is built from synthetic test records. It describes no real property and must never be sent to a county.")
    d.add("h1", "Summary")
    d.add("p", f"Issue: whether the {year} just value exceeds the property's just value, meaning its market value, on January 1, {year} "
               "(s. 193.011, Florida Statutes).")
    if supports:
        jvi = val["just_value_indications"]
        d.add("p", f"The property appraiser set the {year} just value of this {use} at {m(cv['just_value'])} ({R('roll')}).")
        d.add("p", f"{words(ind['comparables']).capitalize()} qualified sales of similar homes, adjusted to January 1, {year}, indicate a market value of "
                   f"{m(val['market_value_indication'])}. The adjusted sales range from {m(ind['low'])} to {m(ind['high'])} ({R('sales')} and {R('adjustments')}).")
        if "market_less_cost_of_sale" in jvi:
            d.add("p", f"After the county's {val['cost_of_sale']['rate']:.0%} cost-of-sale adjustment, the sales indicate a just value of "
                       f"{m(jvi['market_less_cost_of_sale']['value'])}. Measured against the county's own qualified sales, the same market value "
                       f"implies {m(jvi['market_at_county_level']['value'])} ({R('level')}).")
        else:
            d.add("p", f"At the ratio of just value to sale price the county applies to its qualified sales, the sales indicate a just value of "
                       f"{m(jvi['market_at_county_level']['value'])} ({R('level')}).")
        d.add("p", f"The petitioner requests a just value of {m(val['proposed_just_value'])}, the higher of these figures rounded to the nearest $100. "
                   f"That is {m(val['effects']['just_value_reduction'])} below the county's value.")
        d.add("p", f"The county's records are the source for the property's characteristics. Interior condition and quality are not in those records and are not adjusted for. "
                   f"Sales the analysis did not use, the property's own sale history and sales after January 1 are listed in {R('excluded')} and {R('history')}.")
    else:
        d.add("p", f"The property appraiser set the {year} just value at {m(cv['just_value'])} ({R('roll')}). "
                   f"The evidence gathered so far does not support a requested value. Reason: {val['outcome_reason']}.")
    d.add("h1", "Evidence index")
    d.add("index")
    d.add("h1", "Subject property")
    facts = [["Just value", m(cv["just_value"]), "County roll", R("roll")],
             ["Assessed value, school / non-school", f"{m(cv['assessed_value_school'])} / {m(cv['assessed_value_non_school'])}", "County roll", R("roll")],
             ["Land value", m(s.get("LND_VAL")), "County roll", R("roll")],
             ["Special features value", m(s.get("SPEC_FEAT_VAL")), "County roll", R("roll")],
             ["Living area (sq ft)", n(s.get("TOT_LVG_AREA")), "County roll", R("roll")],
             ["Year built, actual / effective", f"{y(s.get('ACT_YR_BLT'))} / {y(s.get('EFF_YR_BLT'))}", "County roll", R("roll")],
             ["Neighborhood code", str(s.get("NBRHD_ORIG") or "-"), "County roll", R("roll")]]
    disc = []
    for o in owner:
        for field, claimed in (o.get("claimed") or {}).items():
            recorded = s.get(field)
            facts.append([f"{FIELD_LABEL.get(field, field)} as stated by the owner", n(claimed) if isinstance(claimed, (int, float)) else str(claimed),
                          "Owner statement, not verified", R(f"owner_{o['evidence_id']}") if o["county_facing"] else "Case record"])
            if recorded is not None and str(recorded) != str(claimed):
                disc.append(f"{FIELD_LABEL.get(field, field)}: the county records {n(recorded) if isinstance(recorded, (int, float)) else recorded}; "
                            f"the owner states {n(claimed) if isinstance(claimed, (int, float)) else claimed}.")
        if o.get("statement") and o.get("include_statement"):
            facts.append([o["label"], o["statement"], "Owner statement, not verified", "Case record"])
    d.add("table", ["Fact", "Value", "Source", "Reference"], facts, [2.1, 2.2, 1.7, 1.0], "facts")
    if disc:
        d.add("p", "Discrepancies between the county's records and the owner's statements. The analysis uses the county's figures until the difference is documented:")
        d.add("bullets", disc)
    if cv.get("homestead"):
        d.add("p", "The property has a homestead exemption. Its assessed value is capped below just value, so a lower just value changes the assessed value only if it falls below the capped amount.")
    if supports:
        jvi = val["just_value_indications"]
        d.add("h1", "Valuation analysis")
        d.add("p", f"Method. Each qualified sale is moved to January 1, {year} with the county's monthly price index, then adjusted for differences in "
                   f"land value, special features and living area. The adjusted prices are reconciled at their median. {R('adjustments')} shows each adjustment and its basis.")
        d.add("p", f"Result. The {words(len(a['selected']))} adjusted sales indicate {m(val['market_value_indication'])}. Their coefficient of dispersion is "
                   f"{a['dispersion_cod']:.1%}.")
        sens = a.get("sensitivity") or {}
        if sens.get("without_flagged_comparables"):
            k = sens["comparables_used"]
            flagged = len(a["selected"]) - k
            d.add("p", f"Sensitivity. Leaving out the {words(flagged)} sale{'s' if flagged != 1 else ''} with large adjustments, the median of the "
                       f"remaining {words(k)} is {m(sens['without_flagged_comparables'])} ({sens['shift']:+.1%}).")
        rows = []
        if "market_less_cost_of_sale" in jvi:
            c = jvi["market_less_cost_of_sale"]
            rows.append(["Market value less cost of sale", c["formula"].replace("market value indication ", "$"), m(c["value"]),
                         f"County DR-493, {val['cost_of_sale']['section']} ({R('level')})"])
        c = jvi["market_at_county_level"]
        rows.append(["Market value at the county's measured level", c["formula"].replace("market value indication ", "$").replace("county level ", ""),
                     m(c["value"]), f"County's qualified sales ({R('level')})"])
        if "assessment_uniformity" in jvi:
            c = jvi["assessment_uniformity"]
            rows.append(["Assessments of similar homes", c["formula"].replace("peer median ", ""), m(c["value"]), f"Support only ({R('peers')})"])
        d.add("table", ["Indication", "Calculation", "Just value", "Basis"], rows, [2.0, 2.4, 1.0, 1.6], "ind")
        d.add("p", f"Requested just value: {m(val['proposed_just_value'])}, the highest indication rounded to the nearest $100.")
        d.add("h1", "Comparable sales")
        sel = a["selected"]
        head = ["", "Subject"] + [f"Sale {i + 1}" for i in range(len(sel))]
        grid = [["Address", s.get("PHY_ADDR1") or ""] + [c["address"] for c in sel],
                ["Sale date", "-"] + [c["sale_month"] for c in sel],
                ["Sale price", "-"] + [m(c["sale_price"]) for c in sel],
                ["Living area", n(s.get("TOT_LVG_AREA"))] + [n(c["sqft"]) for c in sel],
                ["Effective year", y(s.get("EFF_YR_BLT"))] + [y(c["effective_year_built"]) for c in sel],
                ["Land value", m(s.get("LND_VAL"))] + [m(c["county_land_value"]) for c in sel],
                ["Net adjustment", "-"] + [signed(c["net_adjustment"]) for c in sel],
                ["Adjusted price", "-"] + [m(c["indicated_value"]) for c in sel]]
        d.add("table", head, grid, None, "grid")
        sq = float(s.get("TOT_LVG_AREA") or 0)
        ey = int(s.get("EFF_YR_BLT") or 0)
        why = []
        for i, c in enumerate(sel):
            size = (c["sqft"] / sq - 1) if sq else 0
            why.append([f"Sale {i + 1}", c["location"][0].upper() + c["location"][1:], f"{abs(size):.0%} {'larger' if size > 0 else 'smaller'}",
                        f"{abs((c['effective_year_built'] or ey) - ey)} years {'newer' if (c['effective_year_built'] or ey) > ey else 'older'}" if c["effective_year_built"] != ey else "same",
                        f"{c['gross_adjustment_pct']:.0%}", "; ".join(c.get("flags") or []) or "-"])
        d.add("p", "Why each sale was used:")
        d.add("table", ["Sale", "Location", "Size vs subject", "Effective age vs subject", "Gross adjustment", "Flags"], why,
              [0.6, 2.0, 1.0, 1.2, 0.8, 1.4], "why")
        counts = a.get("exclusion_counts") or {}
        d.add("p", f"Sales considered: {a['candidates_considered']:,} qualified sales of the same property use in the market area. "
                   f"{a['candidates_usable']:,} met the selection rules ({a['param_basis'] if isinstance(a.get('param_basis'), str) else 'size, age, land value and recency limits'}). "
                   f"The closest excluded sales are listed with their reasons in {R('excluded')}."
                   + (f" Sales failing each rule (a sale can fail more than one): " + ", ".join(f"{k.lower()} {v:,}" for k, v in counts.items()) + "." if counts else ""))
    if val.get("contradiction"):
        c = val["contradiction"]
        d.add("h1", "Evidence supporting the county's value")
        d.add("p", f"The property sold in {month_long(c['sale_month'])} for {m(c['sale_price'])}. At the county's measured level that implies "
                   f"{m(c['implied_just_value'])}, which supports the county's value ({R('history')}).")
    cond = [o for o in owner if o["kind"] in ("photo", "repair_estimate", "inspection") and o["county_facing"]]
    if cond:
        d.add("h1", "Condition evidence")
        d.add("p", f"The owner supplied the documents below. They have not been independently verified. Property is valued as of January 1, {year}, "
                   "so each item shows the date the document was made and, separately, the date the condition is said to have existed. "
                   "A repair estimate states a cost to repair; it is not offered as a dollar-for-dollar reduction in value.")
        d.add("table", ["Item", "Document date", "Condition date", "Reference"],
              [[o["label"], o.get("document_date") or "Undated", o.get("condition_date") or "Not stated", R(f"owner_{o['evidence_id']}")] for o in cond],
              [3.2, 1.2, 1.2, 1.0], "cond")
    d.add("h1", "Witnesses")
    if witnesses:
        d.add("table", ["Witness", "Address", "General subject of testimony"],
              [[w["witness"], w.get("witness_address") or "To be added before the exchange", w.get("witness_subject") or "The matters in this summary"]
               for w in witnesses], [1.6, 2.4, 3.0], "wit")
        d.add("p", "This is a summary of expected testimony, not a statement taken from any witness.")
    else:
        d.add("p", "No witnesses are identified as of the report date.")
    d.add("h1", "Limitations")
    d.add("bullets", ["Characteristics are the county's recorded values. Interior condition, quality, view and renovations are not in the public files and are not adjusted for.",
                      "Sales are as recorded and qualified by the county. They were not confirmed with the buyers or sellers.",
                      "Location is compared by the county's neighborhood and market-area codes. Distance between properties is not measured.",
                      "Sales recorded after January 1 are disclosed but not used to set the value."])
    _exhibits(d, base, col, a, val, files, owner, supports)
    return d


def _exhibits(d, base, col, a, val, files, owner, supports):
    s = col["subject"]
    ap = base["appeal"]
    year = ap["tax_year"]
    roll_date = f"{year} {col.get('roll_stage') or ''} roll".replace("  ", " ")
    sel = (a or {}).get("selected") or []
    months = sorted(c["sale_month"] for c in sel)
    window = f"{months[0]} to {months[-1]}" if months else f"before January 1, {year}"
    d.exhibit("roll", "County roll record for the subject parcel", "County roll record for the subject parcel", roll_date,
              "Florida DOR NAL file", "Identity, values and characteristics")
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
        d.exhibit("sales", "Recorded sales used as comparables", "Qualified sales used as comparables, with deed references", window,
                  "Florida DOR SDF and NAL files", "Sale prices, dates and characteristics")
        d.add("p", f"Source: {source_line(files['SDF'])}, joined to the NAL file for characteristics. Each is a qualified (code 01 or 02), "
                   f"improved, single-parcel sale recorded before January 1, {year}.")
        d.add("table", ["Sale", "Parcel", "Address", "Date", "Price", "Deed", "Code", "Sq ft", "Eff. year"],
              [[f"Sale {i + 1}", c["parcel_id"], c["address"], c["sale_month"], m(c["sale_price"]),
                (f"OR {c['record']['or_book']}/{c['record']['or_page']}" if c["record"].get("or_book") else (c["record"].get("clerk_no") or "-")),
                c["qualification_code"] or "-", n(c["sqft"]), y(c["effective_year_built"])] for i, c in enumerate(sel)],
              [0.5, 1.05, 1.45, 0.6, 0.8, 0.95, 0.45, 0.55, 0.6], "sales")
        d.exhibit("adjustments", "Adjustment calculations", "Adjustment of each sale to the subject", f"As of January 1, {year}",
                  "Calculated from the roll, sales and index exhibits", "Adjusted price of each sale")
        rows = []
        for i, c in enumerate(sel):
            ad = c["adjustments"]
            rows.append([f"Sale {i + 1}", m(c["sale_price"]), signed(ad["time"]), signed(ad["land"]), signed(ad["special_features"]),
                         signed(ad["living_area"]), signed(c["net_adjustment"]), f"{c['gross_adjustment_pct']:.0%}", m(c["indicated_value"])])
        d.add("table", ["Sale", "Price", "Time", "Land", "Features", "Living area", "Net", "Gross", "Adjusted"], rows,
              [0.55, 0.85, 0.8, 0.8, 0.8, 0.85, 0.85, 0.5, 0.95], "adj")
        d.add("bullets", [f"{k.replace('_', ' ').capitalize()}: {v}." for k, v in a["adjustment_basis"].items()]
              + [f"Building rate: ${a['building_rate_per_sqft']:,.2f} per sq ft, the {a['building_rate_basis']}.",
                 f"Reconciliation: {a['indication']['method']}, giving {m(a['indication']['market_value'])}."])
        d.exhibit("level", "Time index, cost of sale and assessment level", "County time index, DR-493 cost of sale and measured level",
                  f"As of January 1, {year}", "County qualified sales; DR-493", "Time adjustment and conversion to just value")
        d.add("p", f"Time index: {a.get('time_method')}.")
        d.add("table", ["Sale", "Sale date", "Time factor", "Time-adjusted price"],
              [[f"Sale {i + 1}", c["sale_month"], f"{c['time_factor']:.4f}", m(round(c["sale_price"] * c["time_factor"]))] for i, c in enumerate(sel)],
              [1.0, 1.2, 1.2, 1.8], "time")
        if val.get("cost_of_sale"):
            cs = val["cost_of_sale"]
            d.add("p", f"Cost of sale: {cs['rate']:.0%}, as reported by the property appraiser on Form DR-493 for the {year} roll "
                       f"(Florida Department of Revenue, {cs['section']}, {cs['source']}). The sales above are recorded prices with no cost-of-sale deduction, so it is applied once.")
        d.add("p", f"Measured level: {val['county_level']:.4f}, the {a.get('level_source')}.")
    else:
        d.exhibit("sales", "Recorded sales considered", "Recorded sales considered", window, "Florida DOR SDF file", "Why no value is requested")
        why = (a or {}).get("reliability_reason")
        d.add("p", f"Source: {source_line(files['SDF'])}.")
        d.add("p", f"Why no value is requested: {val['outcome_reason']}." + (f" Comparable set: {why}." if why else ""))
    peers = col.get("peers") or {}
    d.exhibit("peers", "Assessments of similar homes", "County values of similar homes in the same peer group", roll_date,
              "Florida DOR NAL file", "Uniformity, offered as support only")
    if peers.get("peers"):
        d.add("p", f"The subject is valued at ${peers['subject_value_per_sqft']:,.2f} per sq ft. The median for {peers['peers']} similar homes is "
                   f"${peers['median_value_per_sqft']:,.2f} ({peers['basis']}). Source: {source_line(files['NAL'])}.")
        d.add("table", ["Parcel", "Address", "Sq ft", "Just value", "Per sq ft"],
              [[e["parcel_id"], e["address"], n(e["sqft"]), m(e["county_just_value"]), f"${e['value_per_sqft']:,.2f}"] for e in peers.get("examples", [])[:10]],
              [1.3, 2.4, 0.8, 1.3, 1.0], "peers")
    else:
        d.add("p", "No similar homes were found in the same peer group within the size range.")
    d.exhibit("excluded", "Sales considered and not used", "Closest sales that were not used, with the reason", window,
              "Florida DOR SDF file", "Shows the selection was not one-sided")
    if a and a.get("excluded_nearest"):
        d.add("table", ["Address", "Date", "Price", "Reason not used"],
              [[e["address"], e["sale_month"], m(e["sale_price"]), "; ".join(r["detail"] for r in e["excluded_because"])] for e in a["excluded_nearest"][:12]],
              [1.8, 0.7, 0.9, 3.6], "excl")
    else:
        d.add("p", "No excluded sales to list.")
    d.exhibit("history", "Subject sale history and sales after January 1", "The subject's recorded sales and sales after January 1",
              f"Through {str(files['SDF'].get('published') or '')[:10]}", "Florida DOR SDF file", "Contrary evidence disclosed")
    own = col.get("own_sales") or []
    if own:
        d.add("table", ["Sale date", "Price", "Code", "Qualified", "Before Jan 1", "Deed"],
              [[o["sale_month"], m(o["sale_price"]), o["qualification_code"] or "-", "Yes" if o["qualified"] else "No", "Yes" if o["before_valuation_date"] else "No",
                (f"OR {o['record']['or_book']}/{o['record']['or_page']}" if o["record"].get("or_book") else (o["record"].get("clerk_no") or "-"))] for o in own],
              [1.0, 1.1, 0.6, 0.9, 1.0, 1.4], "own")
    else:
        d.add("p", "The sales file for this roll records no sale of the subject.")
    sub = (a or {}).get("subsequent_sales") or []
    if sub:
        d.add("p", "Sales after January 1 among the comparable homes, disclosed and not used:")
        d.add("table", ["Address", "Parcel", "Sale date", "Price", "Sq ft"],
              [[x["address"], x["parcel_id"], x["sale_month"], m(x["sale_price"]), n(x["sqft"])] for x in sub], [2.2, 1.4, 0.8, 1.2, 0.8], "sub")
    for o in [o for o in owner if o["county_facing"]]:
        d.exhibit(f"owner_{o['evidence_id']}", o["label"], o["label"], o.get("document_date") or "Undated", "Supplied by the owner, not verified",
                  o.get("supports") or ("Condition" if o["kind"] in ("photo", "repair_estimate", "inspection") else "Property facts"))
        d.add("p", f"Supplied by the owner and not independently verified. Document date: {o.get('document_date') or 'undated'}. "
                   f"Date the owner says the condition existed: {o.get('condition_date') or 'not stated'}. Original file SHA-256 {str(o.get('sha256') or '')[:16]}.")
        if o.get("image_path"):
            d.add("image", o["image_path"], f"{o['label']}. Shown as supplied; scaled to fit the page only.")
        else:
            d.add("p", "The original file is kept unaltered in the case record and goes with every submission copy.")
