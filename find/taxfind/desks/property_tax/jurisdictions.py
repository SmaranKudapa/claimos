"""Where the property-tax desk can work, and when each filing window is open.

`status`: live (Find runs there today), next (good fit, build next), partner (needs an attorney or
licensed partner), later (weak economics or a licensing barrier). Months are the usual residential
filing window; every county posts its own exact date. Researched 2026-11; re-check before launch.
"""
from __future__ import annotations

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

JURISDICTIONS = [
    {"id": "FL", "name": "Florida (67 counties)", "status": "live", "months": [8, 9],
     "window": "25 days after TRIM notices (mailed mid-August)",
     "representation": "anyone with the owner's written authorization; licensed brokers/appraisers/CPAs sign alone",
     "data": "statewide roll + sales from Florida DOR, free", "sales_public": True,
     "obstacle": "Save Our Homes 3% / non-homestead 10% caps shrink savings for long-time owners",
     "sources": ["https://floridarevenue.com/property/documents/pt101.pdf"]},
    {"id": "NYC", "name": "New York City", "status": "next", "months": [1, 2, 3],
     "window": "Mar 15 for houses (Class 1), Mar 1 for other classes",
     "representation": "non-attorneys allowed with a yearly Tax Commission registration (TC610)",
     "data": "unconfirmed", "sales_public": None,
     "obstacle": "Class 1 caps (6%/yr, 20%/5 yrs); best for condos, co-ops, recent buyers",
     "sources": ["https://www.nyc.gov/site/taxcommission/about/challenging-notice-of-property-value.page"]},
    {"id": "TX", "name": "Texas", "status": "next", "months": [4, 5],
     "window": "May 15 or 30 days after the notice, whichever is later",
     "representation": "paid consultants register with TDLR; attorneys, CPAs exempt; agents/appraisers exempt for single-family",
     "data": "per appraisal district, many free exports", "sales_public": False,
     "obstacle": "non-disclosure state: no sale prices, so neighbors-only (equity) rule; 10% homestead cap",
     "sources": ["https://texas.public.law/statutes/tex._tax_code_section_41.44", "https://www.tdlr.texas.gov/ptc/ptcfaq.htm"]},
    {"id": "GA", "name": "Georgia", "status": "next", "months": [5, 6, 7],
     "window": "45 days from each county's notice date (rolling)",
     "representation": "written authorization; no consultant license found",
     "data": "per county; statewide sales index is paid", "sales_public": True,
     "obstacle": "HB 581 inflation cap on homesteads where localities did not opt out",
     "sources": ["https://dor.georgia.gov/filing-property-tax-appeal"]},
    {"id": "WA", "name": "Washington", "status": "next", "months": [6, 7, 8],
     "window": "July 1 or 30 days after the notice (counties may allow 60)",
     "representation": "authorized agent; no license",
     "data": "per county", "sales_public": True, "obstacle": "short window; data split across counties",
     "sources": ["https://app.leg.wa.gov/RCW/default.aspx?cite=84.40.038"]},
    {"id": "PA-ALLEGHENY", "name": "Allegheny County, PA", "status": "next", "months": [7, 8],
     "window": "July 1 - Sept 1 for the next tax year",
     "representation": "authorized representative with signed authorization",
     "data": "free on WPRDC (assessments + sales)", "sales_public": True,
     "obstacle": "taxing bodies can file counter-appeals",
     "sources": ["https://www.alleghenycounty.us/Services/Property-Assessments-and-Real-Estate/Appeals/Board-of-Property-Assessment-Appeals-and-Review-BPAAR"]},
    {"id": "PA-PHILA", "name": "Philadelphia", "status": "next", "months": [9, 10],
     "window": "first Monday of October", "representation": "unconfirmed",
     "data": "unconfirmed", "sales_public": True, "obstacle": "confirm representation rules first",
     "sources": ["https://www.phila.gov/departments/board-of-revision-of-taxes/appeal-forms-and-instructions/"]},
    {"id": "IL-COOK", "name": "Cook County, IL", "status": "partner", "months": list(range(1, 13)),
     "window": "by township, ~30 days after notice; then a Board of Review window",
     "representation": "attorneys only at the Board of Review: partner with a law firm",
     "data": "free county open data (values + sales)", "sales_public": True, "obstacle": "attorney requirement",
     "sources": ["https://www.cookcountyboardofreview.com/board-review-official-rules"]},
    {"id": "NJ", "name": "New Jersey", "status": "partner", "months": [2, 3, 4],
     "window": "Apr 1 (May 1 in revaluation towns) or 45 days after notices",
     "representation": "attorneys only, with hardship exceptions",
     "data": "free statewide MOD-IV roll with sale prices", "sales_public": True,
     "obstacle": "attorney rule; taxes must be current", "sources": []},
    {"id": "NY-UPSTATE", "name": "New York outside NYC", "status": "later", "months": [5, 6],
     "window": "Grievance Day, default 4th Tuesday of May (Nassau Mar 1, Westchester June)",
     "representation": "authorized on form RP-524", "data": "statewide roll on data.ny.gov", "sales_public": True,
     "obstacle": "hundreds of assessing units with their own calendars",
     "sources": ["https://tax.ny.gov/pit/property/contest/grievproced.htm"]},
    {"id": "AZ", "name": "Arizona", "status": "later", "months": [3, 4],
     "window": "60 days after the notice", "representation": "paid agents need a DFI license ($200)",
     "data": "per county, paid", "sales_public": True, "obstacle": "Prop 117 caps taxable value growth at 5%",
     "sources": ["https://sboe.az.gov/faq/how-appeal", "https://azdfi.gov/industry/property-tax-agents"]},
    {"id": "IN", "name": "Indiana", "status": "later", "months": [6],
     "window": "June 15 if the notice was mailed before May 1",
     "representation": "state-certified tax representative unless an attorney",
     "data": "statewide sales-disclosure search", "sales_public": True, "obstacle": "certification barrier", "sources": []},
    {"id": "OH", "name": "Ohio", "status": "later", "months": [1, 2, 3],
     "window": "Mar 31 (or first-half tax due date if later)",
     "representation": "listed filers only (spouse, CPA, licensed appraiser/broker...)",
     "data": "per county auditor", "sales_public": None,
     "obstacle": "one complaint per 3-year cycle; school boards counter-file", "sources": []},
    {"id": "NC", "name": "North Carolina", "status": "later", "months": [4, 5, 6],
     "window": "before the county review board adjourns", "representation": "attorney or power of attorney",
     "data": "statewide NC OneMap parcels", "sales_public": True,
     "obstacle": "infrequent revaluations; some 2026 revaluations paused", "sources": []},
    {"id": "MI", "name": "Michigan", "status": "later", "months": [3, 7], "window": "March Board of Review; Tax Tribunal by July 31",
     "representation": "agents allowed", "data": "per local unit", "sales_public": None,
     "obstacle": "Proposal A taxable-value cap: cuts often save long-time owners nothing", "sources": []},
    {"id": "CO", "name": "Colorado", "status": "later", "months": [5, 6], "window": "protest by June 8 (odd years)",
     "representation": "agent with written authority", "data": "per county", "sales_public": False,
     "obstacle": "two-year reappraisal cycle; sale declarations confidential", "sources": []},
]


def calendar(statuses=("live", "next", "partner")) -> str:
    rows = [j for j in JURISDICTIONS if j["status"] in statuses]
    w = max(len(j["name"]) for j in rows) + 2
    out = [" " * w + "status   " + " ".join(m[:3] for m in MONTHS)]
    for j in rows:
        cells = " ".join(("###" if i + 1 in j["months"] else " . ") for i in range(12))
        out.append(f"{j['name']:<{w}}{j['status']:<9}{cells}")
    covered = sorted({m for j in rows for m in j["months"] if j["status"] in ("live", "next")})
    gaps = [MONTHS[m - 1] for m in range(1, 13) if m not in covered]
    out.append("")
    out.append("months with no live/next window: " + (", ".join(gaps) if gaps else "none"))
    return "\n".join(out)
