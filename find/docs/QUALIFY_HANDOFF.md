# Find → Qualify handoff contract (schema v2)

**For Smaran.** This is what the Find agent delivers, how it arrives, and what Qualify owns.
Schema version **2**. The machine-readable JSON Schema is `taxfind/schema.py:CANDIDATE_JSON_SCHEMA`
and `taxfind schema` prints it.

> This contract is **proposed, not agreed**. Nothing here has been accepted by the Qualify side.
> Tell me what you need changed and I will change it — the version number exists for that.

---

## The division of responsibility

**Find discovers and documents candidates. Qualify decides whether any of them is worth pursuing.**

Find will never tell you a case is good. It tells you what the county's data says, how well
evidenced that is, what it assumed, and what it could not check. Every judgement call is yours.

## How cases arrive

One **board card per parcel**, posted to the board named by `NAIVE_QUALIFY_BOARD`.

- **Card key = `case_id`**, so re-running Find never double-posts a property.
- **Card title** carries the address and estimate. When one owner holds several flagged parcels the
  title leads with the portfolio: `QUINN BRIAN · 10 flagged parcels · est. $7,577/year — FL Hendry 2026 · …`
- **Card body** is a human summary followed by the full JSON payload in a fenced block.
- **Ranking** is risk-adjusted: `portfolio value × evidence quality`. A well-evidenced $600 case
  outranks a thin $2,000 one, and a $7,577 owner outranks a single $2,000 house.

### Delivery is honest about failure

`post_cards` returns a `status`, and it is never optimistic:

| status | meaning |
|---|---|
| `delivered` | every card in the batch was acknowledged by the board with a real id |
| `partial` | some acknowledged, some not — the rest are preserved in `retry_file` |
| `blocked` | **nothing was delivered.** `blocked_by` is `config`, `credentials` or `delivery_errors` |
| `empty` | nothing was eligible |

A card counts as delivered **only** when the board returns a real id. This matters: the previous
version treated a no-key dry run as success and reported "97 posted" when zero had been. If the key
is missing now, the run reports `blocked`, writes the batch to `data/undelivered/<run_id>.jsonl`,
and the whole run's status becomes `handoff_blocked`. Nothing is lost and nothing is claimed.

### What Find holds back on its own

- **Weak counties** — where the holdout self-check failed, cards are not posted at all.
- **Closed filing windows** — held unless `--include-closed`.
- Tiers `review`, `new_build` and `cap_absorbs` never reach you; they stay in the store.

## Reading a payload

Fields you will use most:

| Field | Why it matters |
|---|---|
| `case_id` | `FL-<county code>-<year>-<parcel>`. Stable across runs. Use it as your key too. |
| `status` | Always `candidate`. Every status after this is yours. |
| `tier` | `strong` (≥$500/yr est.) or `possible`. |
| `confidence.evidence_quality` | 0–1, with `components` showing how it was built. **Use this, not the dollar figure, to judge reliability.** |
| `estimate.annual_savings` | A point estimate on an **assumed** millage. |
| `estimate.annual_savings_range` | `[low, high]` across a plausible millage band. Quote this, not the point. |
| `explanation` | Plain-language account of why it was flagged and how the number was derived. |
| `assumptions` | Everything baked in. Read before quoting any figure to anyone. |
| `needs_verification` | Checks Find cannot do. Several are yours. |
| `warnings` | Anything odd about this specific record. |
| `flags.identical_assessment_cluster` | N>1 means N separate parcels, same owner, same peer group, identical county value. **A real pattern, not duplicate records.** |
| `portfolio` | `flagged_parcels` vs `parcels_in_county`, aggregate savings, match basis and caveat. |
| `jurisdiction.county_check.status` | `validated` / `untested`. Only 11 of 67 counties are validated. |
| `filing_window.verified` | `false` means the deadline is a statewide estimate and can be wrong by a week. |
| `outreach` | **Always `eligible: false`.** `blocked_by` lists why. |
| `source` | File URLs, roll stage, publication date, run id, retrieval timestamp. |

### Three things that are deliberately separate

**Candidate quality** (`tier`, `confidence`), **contact verification** (`outreach.contact_*`), and
**outreach eligibility** (`outreach.eligible`). A great case with no verified contact is still not
contactable. Do not collapse these.

## What Qualify needs to do

1. **Check freshness.** `owner.may_have_changed` is true when a deed was recorded after Jan 1.
2. **Check the window.** If `filing_window.verified` is false, read the county's own page before
   acting on the date. Volusia and Broward were 7 days apart in 2026.
3. **Respect suppression.** `outreach.owner_suppressed` means the owner name was unreadable in the
   roll, which is what a Fla. Stat. 119.071 confidential-address exemption looks like.
   **Do not attempt to identify them from another source.**
4. **Weight by evidence, not by size.** `county_check.status: untested` means the screen has never
   been shown to work in that county.
5. **Group by portfolio.** `portfolio.portfolio_id` — one conversation can carry ten cases.
6. **Decide and record a reason**, including for rejections. Find keeps the parcel-level record
   either way.

## Example — the top-ranked case from a real Bay County run

```json
{
  "schema_version": 2,
  "case_id": "FL-13-2026-40000650090",
  "desk": "property_tax",
  "status": "candidate",
  "jurisdiction": {
    "state": "FL",
    "county": "Bay",
    "county_code": "13",
    "tax_year": 2026,
    "roll_stage": "final",
    "county_check": {
      "flagged_sold": 100,
      "flagged_sold_below_value": 0.16,
      "others_sold": 3189,
      "others_sold_below_value": 0.08780181875195986,
      "lift": 1.8222857142857143,
      "status": "validated"
    }
  },
  "property": {
    "parcel_id": "40000650090",
    "alt_key": null,
    "address": "9900 S THOMAS DR",
    "unit": "603",
    "unit_source": "roll",
    "city": "PANAMA CITY BEACH",
    "zip": "32408",
    "use": "condo",
    "sqft": 1131.0,
    "effective_year_built": 2007.0,
    "neighborhood": "400000",
    "homestead": false
  },
  "values": {
    "just_value": 543150.0,
    "assessed_value": 510238.0,
    "taxable_value": 510238.0,
    "land_value": 0.0
  },
  "signals": {
    "neighbor_ratio": 1.6119093993210336,
    "neighbor_count": 344,
    "sales_ratio": 1.5942298602045186,
    "comp_count": 38,
    "own_sale_ratio": null,
    "peer_basis": "building",
    "own_sale_contradicts": false,
    "later_sale": null,
    "peer_group": "400000|B:9900 S THOMAS DR|32408",
    "level_factor_now": 1.0211099665156,
    "own_sale": null,
    "avm_ratio": null,
    "avm": null,
    "county_level": 0.9006097904003088,
    "county_level_source": "measured on 1080 sales"
  },
  "estimate": {
    "defensible_value": 340697.4198377648,
    "value_cut": 202452.5801622352,
    "taxable_cut": 169540.5801622352,
    "taxable_cut_school": 202452.5801622352,
    "annual_savings": 2724,
    "annual_savings_range": [
      1998,
      3995
    ],
    "millage": 0.015,
    "millage_band": [
      0.011,
      0.022
    ],
    "is_estimate": true,
    "millage_source": "ASSUMED, not billed: 5.5 mills school (on school assessed value) + 9.5 other (on non-school assessed value). Actual rates vary by county and district."
  },
  "confidence": {
    "evidence_quality": 1.0,
    "evidence_label": "strong",
    "components": {
      "peer_support": 0.25,
      "comp_support": 0.25,
      "county_self_check": 0.3,
      "no_contradicting_sale": 0.1,
      "owner_unchanged": 0.1
    }
  },
  "explanation": "Flagged because the county's value per sq ft is 61% above 344 similar condos in the same building (ratio 1.61, threshold 1.15), AND the county's value is 59% above what 38 comparable sales imply once adjusted to Jan 1 and compared at the county's own value-to-price level of 0.90 (ratio 1.59, threshold 1.10). A home must fail both tests. The estimate moves the value to $340,697, caps the cut at the assessed and taxable values, and applies an assumed millage to give ~$2,724/yr. County self-check for this county: validated.",
  "assumptions": [
    "Millage is assumed, not read from the parcel's tax bill.",
    "Non-ad-valorem charges (fire, solid waste, lighting) are excluded; they do not change with value.",
    "County value-to-price level for this use: 0.90 (measured on 1080 sales).",
    "Sales are time-adjusted to Jan 1 of the tax year using the county's own monthly/quarterly medians.",
    "Savings are capped at the assessed value and again at the taxable value left after exemptions."
  ],
  "warnings": [],
  "needs_verification": [
    "Confirm the parcel's actual millage for its taxing district \u2014 the savings here use an assumed rate, not a billed one.",
    "Confirm this county's VAB petition deadline from the county's own site; the filing window here is an unverified statewide estimate.",
    "Inspect condition and the county property record card. Public roll data cannot see damage, defects or unpermitted work."
  ],
  "flags": {
    "identical_assessment_cluster": null
  },
  "tier": "strong",
  "avm_check": "not_checked",
  "owner": {
    "owner_id": "own_829d065339f43ee1",
    "name": "CHUCRAY, JERRY",
    "type": "individual",
    "mailing_address": {
      "line1": "18964 BEARS PAW LN",
      "line2": null,
      "city": "STRONGSVILLE",
      "state": "OH",
      "zip": "44136"
    },
    "absentee": true,
    "out_of_state": true,
    "may_have_c
```

## Running it

```bash
export FIND_DATA_DIR=$HOME/find-data
export NAIVE_QUALIFY_BOARD=<the qualify agent or board id>
export NAIVE_API_KEY=<a key with board write access>     # without this the handoff reports blocked
taxfind run --counties Bay --handoff board
```

`taxfind handoff` retries the backlog, including anything in `data/undelivered/`.

## Known limitations you should not have to discover yourself

- **Savings use an assumed millage** (1.5% all-in), not each parcel's billed rate. Hence the range.
- **Only 11 of 67 counties are validated**; 17 are weak (held automatically) and 39 untested.
- **Memory caps the agent sandbox at roughly 100k homes.** Martin (518 MB) and Bay (636 MB) fit;
  Charlotte (976 MB) is marginal; Pasco (1.4 GB) and Lee (2.2 GB) do not. See `docs/COUNTY_COVERAGE.md`.
- **Public data only.** No condition, no damage, no unpermitted work.
- **Filing windows are unverified** except Volusia, Miami-Dade and Broward for 2026.
