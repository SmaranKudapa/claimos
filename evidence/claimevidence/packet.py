from __future__ import annotations

USE = {"001": "single-family residence", "004": "condominium unit"}


def _m(v):
    return "—" if v is None else f"${v:,.0f}"


def _n(v):
    return "—" if v is None else f"{v:,.0f}"


def _y(v):
    return "—" if v is None else f"{int(v)}"


def _src_line(f):
    return (f"Florida Department of Revenue, {f.get('tax_year', '')} {f.get('roll_stage', '')} {f.get('kind')} file, "
            f"published {str(f.get('published') or '')[:10]}, retrieved {str(f.get('retrieved_at') or '')[:10]}, "
            f"SHA-256 {str(f.get('sha256') or '')[:16]}…. {f.get('url')}")


def render_packet(base, col, a, val, items, matrix, rules, deadlines) -> str:
    s = col["subject"]
    ap = base["appeal"]
    files = {f["kind"]: f for f in col["files"]}
    cv = val["county_values"]
    L = []
    L.append(f"# Evidence of value — {ap['jurisdiction']['county']} County, Florida, tax year {ap['tax_year']}")
    L.append("")
    L.append(f"**Parcel** {ap['parcel_id']} · **Property** {s.get('PHY_ADDR1') or ''}, {s.get('PHY_CITY') or ''} · "
             f"**Use** {USE.get(s.get('DOR_UC'), s.get('DOR_UC'))} · **Valuation date** 1 January {ap['tax_year']}")
    L.append("")
    L.append("> Draft prepared by Claim OS software from official public records for human review. It is a comparable-sales "
             "analysis, **not an appraisal**, and has **not** been reviewed by a licensed appraiser. It is not a petition, "
             "a sworn statement or a filed document.")
    L.append("")
    L.append("## Summary")
    ind = (a or {}).get("indication")
    if val["outcome"] == "supports_reduction":
        L.append(f"The county's {ap['tax_year']} just value for this parcel is **{_m(cv['just_value'])}**. "
                 f"{ind['comparables']} qualified sales of similar {USE.get(s.get('DOR_UC'), 'homes')}s, recorded before the valuation date "
                 f"and adjusted to 1 January, indicate a market value of **{_m(val['market_value_indication'])}** "
                 f"(range {_m(ind['low'])}–{_m(ind['high'])}). On the same basis the county applies to its own qualified sales, "
                 f"that supports a just value of **{_m(val['proposed_just_value'])}**.")
        L.append("")
        L.append(f"**Requested just value: {_m(val['proposed_just_value'])}** (a reduction of {_m(val['effects']['just_value_reduction'])} "
                 f"from the county's {_m(cv['just_value'])}).")
    else:
        L.append(f"The analysis does **not** currently support a requested value. Outcome: **{val['outcome'].replace('_', ' ')}** — {val['outcome_reason']}.")
    L.append("")
    L.append("## Exhibit 1 — Subject property as recorded by the county")
    L.append("")
    L.append("| Item | County record |\n|---|---|")
    for label, v in (("Just value", _m(cv["just_value"])), ("Assessed value (school)", _m(cv["assessed_value_school"])),
                     ("Assessed value (non-school)", _m(cv["assessed_value_non_school"])), ("Land value", _m(s.get("LND_VAL"))),
                     ("Special features value", _m(s.get("SPEC_FEAT_VAL"))), ("Living area (sq ft)", _n(s.get("TOT_LVG_AREA"))),
                     ("Effective year built", _y(s.get("EFF_YR_BLT"))), ("Actual year built", _y(s.get("ACT_YR_BLT"))),
                     ("Appraisal neighborhood", s.get("NBRHD_ORIG") or "—")):
        L.append(f"| {label} | {v} |")
    L.append("")
    L.append(f"Source: [S1] {_src_line(files['NAL'])}")
    L.append("")
    L.append("## Exhibit 2 — Comparable sales, adjusted to 1 January")
    L.append("")
    if a and a.get("selected"):
        sel = a["selected"]
        L.append("| | Subject | " + " | ".join(f"Sale {i + 1}" for i in range(len(sel))) + " |")
        L.append("|---|---|" + "---|" * len(sel))
        L.append("| Address | " + str(s.get("PHY_ADDR1") or "") + " | " + " | ".join(c["address"] for c in sel) + " |")
        L.append("| Parcel | " + base["appeal"]["parcel_id"] + " | " + " | ".join(c["parcel_id"] for c in sel) + " |")
        L.append("| Sale month | — | " + " | ".join(c["sale_month"] for c in sel) + " |")
        L.append("| Deed record | — | " + " | ".join(
            (f"OR {c['record']['or_book']}/{c['record']['or_page']}" if c["record"].get("or_book") else (c["record"].get("clerk_no") or "—")) for c in sel) + " |")
        L.append("| Sale price | — | " + " | ".join(_m(c["sale_price"]) for c in sel) + " |")
        L.append("| Living area | " + _n(s.get("TOT_LVG_AREA")) + " | " + " | ".join(_n(c["sqft"]) for c in sel) + " |")
        L.append("| Effective year | " + _y(s.get("EFF_YR_BLT")) + " | " + " | ".join(_y(c["effective_year_built"]) for c in sel) + " |")
        L.append("| Location | — | " + " | ".join(c["location"] for c in sel) + " |")
        if "adjustments" in sel[0]:
            for k, label in (("time", "Time to 1 January"), ("land", "Land"), ("special_features", "Special features"), ("living_area", "Living area")):
                L.append(f"| Adj. {label} | — | " + " | ".join(f"{c['adjustments'][k]:+,}" for c in sel) + " |")
            L.append("| Net adjustment | — | " + " | ".join(f"{c['net_adjustment']:+,} ({c['net_adjustment_pct']:+.0%})" for c in sel) + " |")
            L.append("| **Indicated value** | — | " + " | ".join(f"**{_m(c['indicated_value'])}**" for c in sel) + " |")
        L.append("")
        flagged = [f"Sale {i + 1}: {', '.join(c['flags'])}" for i, c in enumerate(sel) if c.get("flags")]
        if flagged:
            L.append("Flagged for review: " + "; ".join(flagged) + ".")
            L.append("")
        L.append(f"All sales are qualified (codes 01/02), improved, single-parcel transactions recorded before 1 January {ap['tax_year']}. "
                 f"Source: [S2] {_src_line(files['SDF'])}")
    else:
        L.append(f"No reliable comparable set: {(a or {}).get('reliability_reason')}.")
    L.append("")
    L.append("## Exhibit 3 — Method")
    L.append("")
    if a and a.get("indication"):
        for k, v in a["adjustment_basis"].items():
            L.append(f"- **{k.replace('_', ' ').capitalize()}:** {v}.")
        L.append(f"- **Building rate:** ${a['building_rate_per_sqft']:,.2f} per sq ft — {a['building_rate_basis']}.")
        L.append(f"- **Time index:** {a.get('time_method')}.")
        L.append(f"- **County level:** {val['county_level']:.4f} — {a.get('level_source')}.")
        L.append(f"- **Reconciliation:** {a['indication']['method']}; coefficient of dispersion {a['dispersion_cod']:.1%} ({a['reliability']}).")
        sens = a.get("sensitivity")
        if sens:
            L.append(f"- **Sensitivity:** {sens['detail']}")
        L.append("")
        L.append("Selection rules:")
        for k, v in a["param_basis"].items():
            L.append(f"- {v}")
    L.append("")
    L.append("## Exhibit 4 — Requested value calculation")
    L.append("")
    for k, v in (val.get("just_value_indications") or {}).items():
        L.append(f"- **{k.replace('_', ' ').capitalize()}:** {_m(v['value'])} = {v['formula']}. {v['basis'].capitalize()}.")
    L.append(f"- **Rule:** {val['proposed_rule']}.")
    if val.get("proposed_just_value"):
        L.append(f"- **Requested just value:** {_m(val['proposed_just_value'])}.")
    L.append("")
    peers = col.get("peers") or {}
    L.append("## Exhibit 5 — Assessment comparison with similar homes")
    L.append("")
    if peers.get("peers"):
        L.append(f"The county values the subject at ${peers['subject_value_per_sqft']:,.2f} per sq ft. The median for {peers['peers']} similar homes "
                 f"in the same peer group is ${peers['median_value_per_sqft']:,.2f} ({peers['basis']}).")
        L.append("")
        L.append("| Parcel | Address | Living area | County just value | Value per sq ft |\n|---|---|---|---|---|")
        for e in peers.get("examples", [])[:8]:
            L.append(f"| {e['parcel_id']} | {e['address']} | {_n(e['sqft'])} | {_m(e['county_just_value'])} | ${e['value_per_sqft']:,.2f} |")
        L.append("")
        L.append("This compares assessments, not sale prices. It is offered as supporting context alongside the sales evidence.")
    L.append("")
    L.append("## Exhibit 6 — Contrary and excluded evidence")
    L.append("")
    own = col.get("own_sales") or []
    if own:
        L.append("Recorded sales of the subject:")
        for o in own:
            L.append(f"- {o['sale_month']}: {_m(o['sale_price'])}, qualification code {o['qualification_code']}"
                     f"{' (qualified)' if o['qualified'] else ''}{'' if o['before_valuation_date'] else ', after 1 January'}.")
    else:
        L.append("The subject has no recorded sale in the county's sales file for this roll.")
    if val.get("contradiction"):
        L.append(f"- **Contrary:** {val['contradiction']['detail']} ({val['contradiction']['sale_month']}, {_m(val['contradiction']['sale_price'])}).")
    sub = (a or {}).get("subsequent_sales") or []
    if sub:
        L.append("")
        L.append("Sales after 1 January (not used in the indication; disclosed):")
        for x in sub:
            L.append(f"- {x['address']} ({x['parcel_id']}), {x['sale_month']}, {_m(x['sale_price'])}, {_n(x['sqft'])} sq ft.")
    if a:
        L.append("")
        L.append(f"{a['candidates_considered']} sales of the same use in the market area were considered and {a['candidates_usable']} were suitable. "
                 f"Exclusions by reason: " + ", ".join(f"{k.lower()} {v}" for k, v in (a.get("exclusion_counts") or {}).items()) + ".")
        ex = a.get("excluded_nearest") or []
        if ex:
            L.append("")
            L.append("| Excluded sale | Month | Price | Reason |\n|---|---|---|---|")
            for e in ex[:8]:
                L.append(f"| {e['address']} | {e['sale_month']} | {_m(e['sale_price'])} | {'; '.join(r['detail'] for r in e['excluded_because'])} |")
    L.append("")
    homeowner = [i for i in items if i["county_facing"] and i["origin"] in ("homeowner_upload",)]
    if homeowner:
        L.append("## Exhibit 7 — Owner-supplied documents")
        L.append("")
        for i in homeowner:
            L.append(f"- {i['title']} (dated {(i['facts'] or {}).get('document_date') or 'undated'}; owner-supplied, not independently verified).")
        L.append("")
    L.append("## Limitations")
    L.append("")
    L.append("- Characteristics are the county's recorded values. Interior condition, quality, view and renovations are not in the public files and were not adjusted for.")
    L.append("- Sales are as recorded and qualified by the county. They were not individually verified with buyers or sellers.")
    L.append("- The county level is measured from the county's own qualified sales; it is an equalization basis, not a statutory percentage.")
    unresolved = [r for r in rules if r["status"] == "unresolved"]
    if unresolved:
        L.append("- Open procedural questions are listed in the internal review record and must be resolved before use.")
    L.append("")
    L.append("## Sources")
    L.append("")
    L.append(f"- [S1] {_src_line(files['NAL'])}")
    L.append(f"- [S2] {_src_line(files['SDF'])}")
    for r in rules:
        if r.get("cite_in_packet"):
            L.append(f"- [{r['id']}] {r['summary']} — {r['source']}{(' ' + r['section']) if r.get('section') else ''} (checked {r.get('retrieved')}).")
    L.append("")
    L.append(f"_Claim OS evidence cycle {ap['cycle_id']} · method {base.get('method_version', '')}_".replace(" · method ", " · "))
    return "\n".join(L) + "\n"


def render_internal(base, col, a, val, items, matrix, rules, deadlines, intake, tasks, inp) -> str:
    ap = base["appeal"]
    L = [f"# Internal review record — {ap['cycle_id']}", "",
         "Not for submission. Contains operational notes, uncertainty, estimates and private references.", ""]
    L.append("## Intake checks")
    L.append("")
    L.append("| Check | Status | Detail | Blocks | Resolver |\n|---|---|---|---|---|")
    for c in intake["checks"]:
        L.append(f"| {c['id']} {c['check']} | {c['status']} | {c['detail']} | {c['blocks']} | {c['resolver'] or ''} |")
    L.append("")
    L.append("## Requirements")
    L.append("")
    L.append("| ID | Requirement | Required | Status | Resolver | Missing |\n|---|---|---|---|---|---|")
    for r in matrix:
        L.append(f"| {r['id']} | {r['requirement']} | {'yes' if r['required'] else 'no'} | {r['status']} | {r['resolver'] or ''} | {r['missing'] or ''} |")
    L.append("")
    if val and val.get("tax_estimate"):
        t = val["tax_estimate"]
        L.append("## Estimated tax effect (internal only, never a promise)")
        L.append("")
        L.append(f"About ${t['annual_savings']:,}/yr, range ${t['annual_savings_range'][0]:,}–${t['annual_savings_range'][1]:,}, on {t['rate_basis']} rates. {t['caveat']}")
        L.append("")
        L.append(f"Effects: {val['effects']}")
        L.append("")
    if val and val.get("versus_find"):
        L.append("## Versus Find")
        L.append("")
        L.append(f"{val['versus_find']}")
        L.append("")
    L.append("## Deadlines (kept separate)")
    L.append("")
    for k, d in (deadlines or {}).items():
        L.append(f"- **{k.replace('_', ' ')}:** {d.get('date') or 'not set'} ({d.get('status')}; verified={d.get('verified')}). Trigger: {d.get('trigger')}. {d.get('basis') or ''}")
    L.append("")
    L.append("## Homeowner requests (not sent)")
    L.append("")
    for t in tasks:
        L.append(f"- {t['task_id']} {t['title']} — blocking={t['blocking']}, delivery={t['delivery']}")
    L.append("")
    L.append("## Rules applied")
    L.append("")
    for r in rules:
        L.append(f"- [{r['id']}] ({r['status']}) {r['summary']} — {r['source']} {r.get('section') or ''} (checked {r.get('retrieved')}). Applied as: {r.get('applied_as')}")
    L.append("")
    auth = inp.get("authorization") or {}
    L.append("## Authorization reference")
    L.append("")
    L.append(f"status={auth.get('status')} instrument={auth.get('instrument')} document_ref={auth.get('document_ref')} signed_at={auth.get('signed_at')}")
    return "\n".join(L) + "\n"
