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
          petitioner: str, submission: dict, synthetic: bool = False, refs: dict | None = None) -> Doc:
    s = col["subject"]
    ap = base["appeal"]
    year = ap["tax_year"]
    files = {f["kind"]: f for f in col["files"]}
    cv = val["county_values"]
    ind = (a or {}).get("indication")
    supports = val["outcome"] == "supports_reduction" and bool(a and a.get("selected"))
    use = USE.get(str(s.get("DOR_UC") or "").zfill(3), "property")
    owner = homeowner_view(items)
    refs = refs or {}
    R = Doc.ref
    zipc = str(s.get("PHY_ZIPCD") or "").split(".")[0]
    addr = ", ".join(x for x in (s.get("PHY_ADDR1"), s.get("PHY_CITY")) if x) + (f", FL {zipc}" if zipc else ", FL")
    title = (forum.get("document") or "Evidence summary") if supports else "Evidence review, not for submission"
    d = Doc(("TEST FIXTURE, NOT FOR SUBMISSION. " if synthetic else "") + title, f"{ap['parcel_id']} / {year}")
    witnesses = [o for o in owner if o.get("witness")]
    jvi = val.get("just_value_indications") or {}
    sel = (a or {}).get("selected") or []
    later = val.get("later_sales") or {}
    bridge = val.get("bridge") or {}
    cos = val.get("cost_of_sale")

    d.add("title", d.title)
    d.add("subtitle", f"{forum.get('authority')}, tax year {year}")
    meta = [("Receiving authority", forum.get("authority") or "-"),
            ("Party submitting", "Petitioner"),
            ("Petitioner", petitioner),
            ("Property address", f"{addr} ({use})" if addr else "-"),
            ("Parcel", ap["parcel_id"]),
            ("Tax year", f"{year}; valuation date {date_long(f'{year}-01-01')}"),
            ("Petition number", submission.get("petition_number") or "Not yet assigned"),
            ("Contact telephone", submission.get("contact_phone") or "To be added before submission"),
            ("Off-site witnesses", "; ".join(w["witness"] + (f", {w['witness_phone']}" if w.get("witness_phone") else "") for w in witnesses)
             if witnesses else "No off-site witnesses"),
            ("Value challenged", f"{year} just value of {m(cv['just_value'])}"),
            ("Value requested", f"Just value of {m(val['proposed_just_value'])}" if supports else "No value is requested. The evidence does not support one."),
            ("Version", f"{version['number']}, {date_long(generated_on)}, content fingerprint {version['fingerprint'][:12]}"),
            ("Prepared by", "Claim OS software, from the public records listed in the evidence index. The text and figures are produced by fixed code, not written by hand."),
            ("Reviewed by", "Not reviewed at the time of generation. Review and approval are recorded separately against this version.")]
    d.add("meta", meta)
    d.add("note", "No appraiser, real estate broker or attorney prepared or reviewed this summary. It is submitted as the petitioner's evidence.")
    if not supports:
        d.add("note", "Not for submission. The evidence gathered does not support a lower value, so this review is kept for the case record only.")
    if synthetic:
        d.add("note", "This document is built from synthetic test records. It describes no real property and must never be sent to a county.")

    d.add("h1", "Summary")
    d.add("p", f"Issue: whether the {year} just value of {m(cv['just_value'])} exceeds the property's just value on January 1, {year}. "
               "Florida just value is market value after the usual costs of sale (s. 193.011(1) and (8), Florida Statutes).")
    if supports:
        prices = sorted(c["sale_price"] for c in sel)
        where = "in the subject's county neighborhood" if all("peer group" in c["location"] for c in sel) else "in the subject's market area"
        bullets = [f"{words(len(sel)).capitalize()} qualified sales of comparable homes {where} sold for "
                   f"{m(prices[0])} to {m(prices[-1])} before January 1, {year} ({R('sales')}).",
                   f"Adjusted to the subject and to January 1, they indicate a market value of {m(val['market_value_indication'])} "
                   f"({R('adjustments')}). The county's {m(cv['just_value'])} is {bridge.get('county_value_to_market_indication', 0):.0%} of that market value."]
        conv = []
        if "market_less_cost_of_sale" in jvi:
            conv.append(f"{m(jvi['market_less_cost_of_sale']['value'])} after the county's {cos['rate']:.0%} cost-of-sale adjustment")
        conv.append(f"{m(jvi['market_at_county_level']['value'])} at the ratio of just value to sale price the county applies to its own qualified sales")
        bullets.append("Converted to just value, the market value indicates " + " or ".join(conv) + f" ({R('level')}).")
        if "comparables_own_assessment_ratio" in jvi:
            r = statistics.median(c["county_just_value"] / c["sale_price"] for c in sel)
            bullets.append(f"The county values the same {words(len(sel))} sold homes at a median {r:.1%} of their sale prices; "
                           f"the subject is valued at {cv['just_value'] / bridge['steps'][0]['value']:.0%} of their median price ({R('sales')}).")
        if later.get("count"):
            bullets.append(("One similar home" if later["count"] == 1 else f"{words(later['count']).capitalize()} similar homes")
                           + f" sold after January 1 for {'' if later['count'] == 1 else 'a median '}{m(later['median_price'])}, "
                           f"a just-value equivalent of {m(later['median_just_value_equivalent'])} ({R('later')}).")
        d.add("bullets", bullets)
        d.add("p", f"Requested determination: set the {year} just value at {m(val['proposed_just_value'])}, the higher of the two "
                   "conversions of the market value, rounded to the nearest $100. Assessed and taxable values follow from that just value under any exemptions "
                   "and caps; they are not argued separately.")
    else:
        d.add("p", f"The evidence gathered does not support a requested value. Reason: {val['outcome_reason']}.")

    d.add("h1", "Petition and authorization")
    auth = refs.get("authorization") or {}
    d.add("table", ["Document", "Status", "Prepared or held by"],
          [["Petition to the Value Adjustment Board (Form DR-486)",
            f"Filed, petition {submission['petition_number']}" if submission.get("petition_number") else "Not yet filed; filed separately from this evidence",
            "Prepared by Claim OS for the petitioner; the clerk assigns the petition number"],
           ["Authorization to represent the owner (Form DR-486POA or written authorization)",
            "Signed; held in the case record" if auth.get("status") == "signed" else "Not yet signed",
            "Kept in the case record; it goes with the petition, not with this evidence"]],
          [3.0, 2.2, 2.3], "refs")

    d.add("h1", "Evidence index")
    d.add("index")

    d.add("h1", "Subject property")
    facts = [["Just value", m(cv["just_value"]), "County roll", R("roll")],
             ["Assessed value, school / non-school", f"{m(cv['assessed_value_school'])} / {m(cv['assessed_value_non_school'])}", "County roll", R("roll")],
             ["Taxable value, school / non-school", f"{m(cv['taxable_value_school'])} / {m(cv['taxable_value_non_school'])}", "County roll", R("roll")],
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
        d.add("h1", "Method")
        same_size = all(abs(c["size_diff_pct"]) < 0.10 for c in sel)
        near_age = all(c["effective_age_gap"] is not None and abs(c["effective_age_gap"]) <= 3 for c in sel)
        fit = [f"the sales are in the subject's county neighborhood"]
        if same_size:
            fit.append("within 10% of its living area")
        if near_age:
            fit.append("within three years of its effective year built")
        d.add("p", "Sales comparison, because recent qualified sales of similar homes are available: " + ", ".join(fit) + ". "
                   "Each sale is moved to January 1 with the county's monthly price index and adjusted for differences in county land value, "
                   "special features and living area. Age, condition and quality are not adjusted; they are controlled by choosing similar sales. "
                   "The adjusted prices are reconciled at their median, and the result is converted from market value to just value. "
                   "Income and cost approaches are not used: there is no rental evidence, and building cost data is not public.")
        d.add("h1", "Comparable sales")
        head = ["", "Subject"] + [f"Sale {i + 1}" for i in range(len(sel))]
        grid = [["Address", s.get("PHY_ADDR1") or ""] + [c["address"] for c in sel],
                ["Sale date", "-"] + [c["sale_month"] for c in sel],
                ["Sale price", "-"] + [m(c["sale_price"]) for c in sel],
                ["Living area", n(s.get("TOT_LVG_AREA"))] + [n(c["sqft"]) for c in sel],
                ["Year built / effective", f"{y(s.get('ACT_YR_BLT'))} / {y(s.get('EFF_YR_BLT'))}"] + [f"{y(c['actual_year_built'])} / {y(c['effective_year_built'])}" for c in sel],
                ["Land value", m(s.get("LND_VAL"))] + [m(c["county_land_value"]) for c in sel],
                ["County value", m(cv["just_value"])] + [m(c["county_just_value"]) for c in sel],
                ["Net adjustment", "-"] + [signed(c["net_adjustment"]) for c in sel],
                ["Adjusted price", "-"] + [m(c["indicated_value"]) for c in sel]]
        d.add("table", head, grid, None, "grid")
        recon = a.get("reconciliation") or {}
        wts = recon.get("weights") or {}
        mids = set(recon.get("median_between") or [])
        notes = []
        for i, c in enumerate(sel):
            notes.append([f"Sale {i + 1}", "; ".join(c.get("similarities") or []) or "-", "; ".join(c.get("differences") or []) or "none material",
                          "; ".join((c.get("uncertainty") or []) + (c.get("flags") or [])) or "-",
                          "sets the median" if c["parcel_id"] in mids else "counts once"])
        d.add("p", "How each sale compares:")
        d.add("table", ["Sale", "Similar", "Different", "Uncertainty", "Weight"], notes, [0.5, 2.0, 1.6, 2.1, 0.9], "notes")
        d.add("p", f"Reconciliation: the median of the adjusted prices, {m(val['market_value_indication'])}, set by the two middle sales. "
                   f"Giving more weight to the sales that needed the least adjustment gives {m(recon.get('weighted_cross_check'))}.")
        counts = a.get("exclusion_counts") or {}
        d.add("p", f"Search: {a['candidates_considered']:,} qualified sales of the same property use in the subject's market area before January 1, {year}. "
                   f"{a['candidates_usable']:,} met the selection rules; the {words(len(sel))} closest were used. Sales were not chosen by price. "
                   f"The nearest sales that were not used, with the reason for each, are in {R('excluded')}."
                   + (f" Sales failing each rule (a sale can fail more than one): " + ", ".join(f"{k.lower()} {v:,}" for k, v in counts.items()) + "." if counts else ""))

        d.add("h1", "Calculations")
        steps = bridge.get("steps") or []
        rows = [[st_["label"], m(st_["value"])] for st_ in steps[:3]]
        if "market_less_cost_of_sale" in jvi:
            rows.append([f"Just value: market value x (1 - {cos['rate']:.0%} cost of sale, DR-493)", m(jvi["market_less_cost_of_sale"]["value"])])
        rows.append([f"Just value: market value x {val['county_level']:.4f}, the county's measured ratio", m(jvi["market_at_county_level"]["value"])])
        if "comparables_own_assessment_ratio" in jvi:
            rows.append(["Cross-check: market value x the county's own ratio for these sales", m(jvi["comparables_own_assessment_ratio"]["value"])])
        if "assessment_uniformity" in jvi:
            rows.append([f"Cross-check: similar homes' county value per sq ft ({R('peers')})", m(jvi["assessment_uniformity"]["value"])])
        rows.append(["Requested just value (higher of the two conversions, rounded to $100)", m(val["proposed_just_value"])])
        rows.append(["County just value", m(cv["just_value"])])
        d.add("table", ["Step", "Value"], rows, [5.4, 1.6], "bridge")
        g = bridge.get("gap") or {}
        d.add("p", f"Of the {m(g.get('total'))} difference between the county's value and the request, {m(g.get('county_value_above_market_indication'))} "
                   f"is the county's value exceeding the indicated market value itself, {m(g.get('just_value_conversion'))} is the conversion from market value "
                   f"to just value, and {m(g.get('rounding'))} is rounding. The comparable adjustments and the conversion are separate steps.")
        if cos:
            d.add("p", f"Conversion: the Bay County Property Appraiser reports on Form DR-493 for the {year} roll that it adjusts recorded sale prices by "
                       f"{cos['rate']:.0%} for this property class ({R('level')}). The sales used here are recorded prices with no such deduction, so it is "
                       f"applied once, to the market value indication. The county's measured ratio, {val['county_level']:.4f}, is shown as the alternative; "
                       "the two are never combined. Neither is an exemption or an assessment cap.")
        sens = recon.get("sensitivity") or {}
        d.add("p", f"Sensitivity: the recorded prices alone have a median of {m(sens.get('recorded_prices_median'))}; without the time adjustment the "
                   f"median adjusted price is {m(sens.get('without_time_adjustment_median'))}; weighting the sales by how little they were adjusted gives "
                   f"{m(recon.get('weighted_cross_check'))}. Each is below the {m(round(cv['just_value'] / val['county_level']))} market value the county's "
                   f"value implies at its own ratio. Time index: {a.get('time_index_note')}.")

    d.add("h1", "Contrary evidence and limitations")
    if val.get("contradiction"):
        c = val["contradiction"]
        d.add("p", f"The property sold in {month_long(c['sale_month'])} for {m(c['sale_price'])}. At the county's measured level that implies "
                   f"{m(c['implied_just_value'])}, which supports the county's value ({R('history')}).")
    if later.get("count"):
        one = later["count"] == 1
        d.add("p", f"Sales after January 1: {'one home' if one else words(later['count']) + ' homes'} within 10% of the subject's size sold for "
                   f"{m(later['median_price'])}{'' if one else ' (median)'}, or {m(later['median_time_adjusted'])} moved back to January 1. "
                   f"At the county's ratio that is {m(later['median_just_value_equivalent'])}. "
                   + (f"{words(later['contrary']).capitalize()} of them point{'s' if later['contrary'] == 1 else ''} to a value at or above the county's."
                      if later["contrary"] else "No later sale points to a value at or above the county's.")
                   + f" {'It is' if one else 'They are'} a check on the January 1 indication, not its basis ({R('later')}).")
    lim = ["Interior condition, quality, view and renovations are not in the public files and are not adjusted for. No inspection was made.",
           "Sales are as recorded and qualified by the county. Buyers and sellers were not contacted, and concessions are not known."]
    if any(c.get("new_construction") for c in sel):
        k = sum(1 for c in sel if c.get("new_construction"))
        lim.append(f"{words(k).capitalize()} of the sales are new construction. Builder incentives, lot premiums and upgrades are not in public records.")
    lim.append("Location is compared by the county's neighborhood and market-area codes. Distance, waterfront and flood exposure are not measured.")
    if a and a.get("systematic_bias"):
        lim.append(a["systematic_bias"].capitalize() + ".")
    d.add("bullets", lim)

    cond = [o for o in owner if o["kind"] in ("photo", "repair_estimate", "inspection") and o["county_facing"]]
    if cond:
        d.add("h1", "Condition evidence")
        d.add("p", f"The owner supplied the documents below. They have not been independently verified. Property is valued as of January 1, {year}, "
                   "so each item shows the date the document was made and, separately, the date the condition is said to have existed. "
                   "A repair estimate states a cost to repair; it is not offered as a dollar-for-dollar reduction in value.")
        d.add("table", ["Item", "Document date", "Condition date", "Reference"],
              [[o["label"], o.get("document_date") or "Undated", o.get("condition_date") or "Not stated", R(f"owner_{o['evidence_id']}")] for o in cond],
              [3.2, 1.2, 1.2, 1.0], "cond")

    if supports:
        d.add("h1", "Conclusion")
        lo = min(v["value"] for v in jvi.values())
        hi = max(v["value"] for v in jvi.values())
        above = val.get("cross_checks_above_request") or []
        d.add("p", f"The just-value indications range from {m(lo)} to {m(hi)}"
                   + (f", and all are below the county's {m(cv['just_value'])}. " if hi < cv["just_value"] else f"; the county's value is {m(cv['just_value'])}. ")
                   + f"The request uses the higher of the two conversions of the market value indication"
                   + (f"; {' and '.join(x.replace('_', ' ') for x in above)} point higher and should be weighed by the reviewer" if above else "")
                   + f". The petitioner requests that the board set the {year} just value at {m(val['proposed_just_value'])}.")

    d.add("h1", "Witnesses")
    if witnesses:
        d.add("table", ["Witness", "Address", "General subject of testimony"],
              [[w["witness"], w.get("witness_address") or "To be added before the exchange", w.get("witness_subject") or "The matters in this summary"]
               for w in witnesses], [1.6, 2.4, 3.0], "wit")
        d.add("p", "This is a summary of expected testimony, not a statement taken from any witness.")
    else:
        d.add("p", "No witnesses are identified as of the report date.")
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
        d.add("p", "Each adjustment, as calculated:")
        d.add("table", ["Sale", "Time", "Land", "Features", "Living area"],
              [[f"Sale {i + 1}"] + [c["adjustment_detail"][k]["formula"] for k in ("time", "land", "special_features", "living_area")]
               for i, c in enumerate(sel) if c.get("adjustment_detail")], [0.55, 1.75, 1.75, 1.6, 1.65], "adjf")
        d.add("p", "Support for each adjustment: " + " ".join(f"{k.replace('_', ' ').capitalize()}: {v['support']}." for k, v in
                                                           (sel[0].get("adjustment_detail") or {}).items()))
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
    lat = val.get("later_sales") or {}
    if lat.get("count"):
        d.exhibit("later", "Sales after January 1", "Similar homes sold after the valuation date, as a check", "After January 1",
                  "Florida DOR SDF file", "Consistency of the January 1 indication")
        d.add("p", "Homes in the subject's neighborhood within 10% of its living area that sold after January 1. Each price is moved back to January 1 "
                   f"with the county index and multiplied by the county's measured ratio ({val['county_level']:.4f}) to compare with the subject's just value.")
        d.add("table", ["Address", "Sale date", "Price", "Time factor", "At Jan 1", "Just-value equivalent", "Compared with the county value"],
              [[x["address"], x["sale_month"], m(x["sale_price"]), f"{x['time_factor']:.4f}", m(x["time_adjusted_price"]), m(x["just_value_equivalent"]),
                x["relation"]] for x in lat["sales"]], [1.6, 0.7, 0.85, 0.7, 0.85, 1.0, 1.4], "later")
    elif sub:
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
