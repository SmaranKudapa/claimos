# Expanding beyond Florida: a filing window in every month

Florida's window is late August to mid-September. To earn through the year, add jurisdictions whose
windows fall in other months. `taxfind calendar` prints this grid from
`taxfind/desks/property_tax/jurisdictions.py` (researched November 2026; re-check each before launch —
two dates changed recently: Allegheny now files July 1–Sept 1 for the next year, and some North
Carolina 2026 revaluations were paused).

```
                        status   Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec
Florida (67 counties)   live      .   .   .   .   .   .   .  ### ###  .   .   .
New York City           next     ### ### ###  .   .   .   .   .   .   .   .   .
Texas                   next      .   .   .  ### ###  .   .   .   .   .   .   .
Georgia                 next      .   .   .   .  ### ### ###  .   .   .   .   .
Washington              next      .   .   .   .   .  ### ### ###  .   .   .   .
Allegheny County, PA    next      .   .   .   .   .   .  ### ###  .   .   .   .
Philadelphia            next      .   .   .   .   .   .   .   .  ### ###  .   .
Cook County, IL         partner  ### ### ### ### ### ### ### ### ### ### ### ###
New Jersey              partner   .  ### ### ###  .   .   .   .   .   .   .   .
```

## Suggested order

1. **NYC (Jan–Mar)** — non-attorneys file with a yearly registration; huge volume. Aim at condos, co-ops
   and recent buyers, where the Class 1 caps bite least.
2. **Texas (Apr–May)** — the biggest contingency market; consultants register with TDLR. Texas does not
   publish sale prices, so the desk runs neighbors-only (equity) — the legal basis for most Texas protests.
3. **Georgia (May–Jul)** — agents allowed, sale prices public, county notice dates are staggered.
   Skip localities under the HB 581 homestead cap.
4. **Washington (Jun–Aug)** — agents allowed, sales public, no value cap; runs straight into Florida.
5. **Philadelphia + Allegheny (Jul–Oct)** — free open data with sales. Confirm Philadelphia's
   representation rules first.
6. **Cook County (any month, by township)** — attorneys only: a fee-share with a law firm.

Fees usually land when decisions or tax bills come out, months after filing, which spreads revenue further.

## What each state needs

| | Representation | Bulk data | Sale prices | Watch out for |
|---|---|---|---|---|
| NYC | yearly TC610 registration | unconfirmed | unconfirmed | Class 1 caps |
| Texas | TDLR consultant registration (attorneys, CPAs, real-estate licensees for single-family exempt) | per appraisal district | **no** (non-disclosure) | 10% homestead cap; crowded market |
| Georgia | written authorization | per county; statewide sales index paid | yes (PT-61) | HB 581 caps |
| Washington | authorized agent | per county | yes | short window |
| Allegheny | signed authorization | free (WPRDC) | yes | counter-appeals by taxing bodies |
| Cook | attorneys only | free open data | yes | attorney rule |

Alternates: Arizona (cheap license, paid data, 5% cap), Indiana (certified staff), Ohio and New Jersey
(brokers/attorneys), Michigan and Colorado (value caps, two-year cycle).

## Adding a state in code

Copy `taxfind/desks/property_tax/new_state_template.py` to `<state>/__init__.py`. It only has to map the
state's roll and sales into the common columns listed there, and give its filing window; detection,
owner matching, the second opinion, storage and hand-off are shared. Register it in
`taxfind/pipeline.py: DESKS` and flip its `status` to `live`.

## Sources
- Florida DOR, VAB petitions (PT-101): https://floridarevenue.com/property/documents/pt101.pdf
- NYC Tax Commission: https://www.nyc.gov/site/taxcommission/about/challenging-notice-of-property-value.page
- Texas Tax Code 41.44: https://texas.public.law/statutes/tex._tax_code_section_41.44 · TDLR: https://www.tdlr.texas.gov/ptc/ptcfaq.htm
- Georgia DOR appeals: https://dor.georgia.gov/filing-property-tax-appeal
- RCW 84.40.038 (Washington): https://app.leg.wa.gov/RCW/default.aspx?cite=84.40.038
- Allegheny BPAAR: https://www.alleghenycounty.us/Services/Property-Assessments-and-Real-Estate/Appeals/Board-of-Property-Assessment-Appeals-and-Review-BPAAR
- Philadelphia BRT: https://www.phila.gov/departments/board-of-revision-of-taxes/appeal-forms-and-instructions/
- Cook County Board of Review rules: https://www.cookcountyboardofreview.com/board-review-official-rules
- Arizona SBOE: https://sboe.az.gov/faq/how-appeal · DFI agents: https://azdfi.gov/industry/property-tax-agents
- New York ORPTS grievance: https://tax.ny.gov/pit/property/contest/grievproced.htm
