# Find → Qualify hand-off (schema v1)

Find produces one **candidate** per property and tax year. It arrives three ways, all with the same
JSON: a line in `candidates.jsonl`, a row in the database (`data/find.sqlite`, table `candidates`,
column `payload`), and — for `strong` / `possible` — a card on the Qualify agent's Naïve board
whose body ends with the JSON in a ```json block. Full JSON Schema: `taxfind schema`.

## Identity and idempotency
- `case_id` = `<STATE>-<county code>-<tax year>-<parcel id>`, e.g. `FL-46-2026-094523C2046840030`.
- Re-running Find updates the same `case_id`; a card is created once per `case_id` (Naïve `key`).
- Cards are not posted for counties whose self-check is `weak`, or when the filing window has closed
  (`--include-closed` overrides the second for demos).
- `owner.owner_id` groups every parcel of one owner (same normalized name + mailing address) in a
  county. One signup can cover several cases: see `owner.flagged_parcels_in_run` and
  `owner.portfolio_savings_in_run`.

## What Qualify gets, by field

| Field | Meaning | Use in Qualify |
|---|---|---|
| `tier` | `strong` / `possible` (mail-ready), `review`, `cap_absorbs`, `new_build` | only `strong`/`possible` arrive as cards |
| `estimate.annual_savings` | $/yr if the value drops to `defensible_value`, net of the homestead cap | the "$" in EV = $ × p(win) − cost |
| `estimate.millage` | assumed rate: 5.5 mills school + 9.5 other (1.5% total) | replace with the parcel's real rates when known |
| `estimate.taxable_cut`, `estimate.taxable_cut_school` | how much each taxable base drops; school levies use the school assessed value, which has no 10% non-homestead cap | the "$" is school cut × school rate + other cut × other rate |
| `signals.neighbor_ratio`, `signals.sales_ratio` | > 1 = county value high; flagged at ≥ 1.15 and ≥ 1.10 | inputs to p(win); bigger and both high = stronger |
| `signals.neighbor_count`, `signals.comp_count` | how much data stands behind each ratio | low counts = lower confidence |
| `signals.own_sale_ratio`, `signals.own_sale`, `signals.later_sale` | the home's own sale before / after Jan 1 vs county value | strongest single piece of evidence; a sale that supports the value already moved the case to `review` |
| `owner.may_have_changed`, `owner.deed_since_roll` | a deed was recorded after Jan 1 | mail the current owner, not just the owner of record |
| `jurisdiction.county_check` | the county's self-check on sales after the valuation date: `validated`, `weak` (cards held), `untested` | discount p(win) in `untested` counties |
| `avm_check`, `signals.avm_ratio`, `signals.avm` | Zillow/Redfin/Naïve estimate check | `confirmed` raises p(win); `disputed` cases arrive as `review` |
| `signals.possible_sqft_error` | county area ≥ 15% above the listing's, beyond the county's usual gap | a factual-error appeal, often the easiest win |
| `property.homestead` | owner-occupied with exemption | homesteaded savings are capped; the owner lives there (mail works) |
| `property.unit`, `property.unit_source` | condo unit and where it came from; null = unknown | Sign up / Evidence look it up by parcel id |
| `property.sqft` | the county's *effective* area (may weight garages/porches) | never quote it to an owner as living area |
| `owner.*` | owner of record and tax-bill mailing address; `type` = individual, trust, company, estate, bank, government, association… | skip `government`/`bank`/`association`; `estate` needs a representative |
| `filing_window` | `opens`, `closes`, `status` (upcoming/open/closed) — Florida: ~25 days after TRIM mailing, mid-August | time left before the deadline; confirm the county's posted date |
| `evidence.neighbors`, `evidence.sales` | 8 nearest similar homes and 8 nearest comparable sales, with sale record numbers | the Evidence desk starts here |
| `source` | roll and sales file URLs, run id, timestamp | audit trail |

## Not included, on purpose
Phone numbers, emails and skip-traced contacts. Cold outreach is by mail to `owner.mailing_address`;
phone/SMS need prior consent (TCPA), which Sign up collects.
