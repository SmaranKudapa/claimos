# taxappeal-find — the Find step

Step 1 of the claims engine (Find → Qualify → Sign up → Evidence → File → Chase → Escalate → Collect),
for the **property-tax desk**. It reads every county's public tax roll, flags homes the county has
over-assessed, attaches the owner of record, gets a Zillow/Redfin second opinion on the shortlist,
and hands each case to Qualify. Runs on a laptop, in CI, or autonomously as a Naïve agent on a schedule.

```
 state data portal ──► ingest ──► detect ──► match owners ──► second opinion ──► store ──► hand off
 (all 67 FL counties)  cached,    neighbors   owner_id,        Naïve data /       SQLite    files + Naïve
                       only new   + sales     portfolios,      Apify Zillow →     upsert    board cards
                       files      + cap       condo units      Apify Redfin       by case   for Qualify
```

| Core loop column | Engine (shared, `taxfind/engine`) | Desk adds (`taxfind/desks/property_tax`) |
|---|---|---|
| Data ingestion | `ingest.py` cached conditional downloads, safe unzip | `florida/source.py` DOR portal discovery for 67 counties |
| Matching records to people | `people.py` owner_id, owner type, absentee, portfolios, condo units | — |
| Upload parser | `uploads.py` CSV/XLSX/PDF/text → parcel (id, address, fuzzy) | — |
| Detection rule | — | `screen.py` neighbor + sales signals, homestead cap, tiers |
| Second opinion | `avm/` providers, cache, spend cap | — |
| Hand-off | `handoff.py`, `naive.py`, `schema.py` | `florida/__init__.py` filing window, payloads |

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
taxfind sources                                   # 67 counties, roll year, posted date
taxfind run --counties Lee --no-avm               # ~1 min; writes data/out/<run>/candidates.{csv,jsonl}
taxfind run --counties all --no-avm               # whole state, ~30 min the first time, cached after
taxfind watch --once                              # autonomous pass: only counties with new files
taxfind calendar                                  # which jurisdictions file in which month
./scripts/demo.sh Lee                             # the full cycle end to end, no keys needed
pytest -q                                         # 62 tests, no network
```

Outputs per run in `data/out/<run_id>/`: `candidates.jsonl` (full payloads, the Qualify contract),
`candidates.csv` (one row per case, for people), `summary.json` (per-county stats and errors).

## How detection works

Per house (`DOR_UC 001`) and condo (`004`), two independent signals, both required:

1. **Neighbors** — county value per sq ft ÷ median of similar homes in the same peer group (size ±20%,
   effective age ±10 yrs, and for houses a similar lot value so waterfront isn't compared with dry lots).
   Flag at ≥ 1.15.
2. **Sales** — county value ÷ (nearby comparable arm's-length sales before the Jan 1 valuation date,
   time-adjusted month by month) × the county's own normal value-to-price level. Flag at ≥ 1.10.

**Peer groups** follow the county's appraisal neighborhood, with fixes for how counties actually fill it in:
condos are compared **within their own building** (a whole beach town in one "neighborhood" made Gulf-front
towers look over-assessed); a neighborhood covering most of a county is split by **survey section**
(1 sq mi) or **township**; a blank neighborhood falls back to the county's **market area**.

**Overrides:** the home's own arm's-length sale — before or after Jan 1 — beats any comparison: if it
supports the county's value, the case goes to `review`. A deed after Jan 1 sets `owner.may_have_changed`.

**Savings** = school cut × school rate (on the school assessed value, which has no 10% non-homestead cap)
+ other cut × other rate (on the capped assessed value), never more than the taxable value left after
exemptions. Rates default to 5.5 + 9.5 mills. Tiers: `strong` (≥ $500/yr), `possible`, `review`
(outliers, own sale disagrees, or Zillow/Redfin disagrees), `cap_absorbs` (caps or exemptions leave no
money), `new_build` (built in the last 2 years).

**Self-check per county.** Sales recorded after the valuation date were never seen by the screen. Find
compares how often flagged homes then sold below the county's value with how often everything else did.
`validated` (≥ 1.25× as often), `weak` (cards to Qualify are **held** for that county), or `untested`
(fewer than 30 flagged homes sold). It is a filter, not a verdict — Qualify and a human look decide.

## Second opinion (Zillow / Redfin / Naïve)

Only the top candidates per county are looked up (`FIND_AVM_MAX_LOOKUPS`, default 300), within a
per-run dollar cap (`FIND_AVM_BUDGET_USD`, default $5), cached 60 days. Providers in order
(`FIND_AVM_PROVIDERS`):

| Provider | What it calls | Input | ~Cost |
|---|---|---|---|
| `naive` | Naïve data catalogue, domain `real_estate` — pick the tool with `taxfind naive-tools`, set `NAIVE_REAL_ESTATE_TOOL` | address | per tool's listed price |
| `apify_zillow` | `maxcopell/zillow-detail-scraper` (`addresses[]`), falls back to `kawsar/affordable-zillow-details-scraper` (`address[]`) | address | ~$1.70–2 / 1,000 |
| `apify_redfin` | `tri_angle/redfin-detail` (`addresses[]`) — used when Zillow returns nothing | address | ~$2.25 / 1,000 + per address |
| `mock` | deterministic fake values, labelled `mock` — demos without keys only | — | free |

Result per case (`avm_check`): `confirmed` (county value ≥ 5% above estimate × normal level), `inconclusive`,
`disputed` (demoted to `review`), `no_unit` (a condo whose unit number isn't on the roll — the building
address would return the wrong home, so it isn't looked up), `no_estimate`. The estimate is a
false-positive filter, not evidence: boards weigh comparable sales, which the Evidence desk builds from `evidence.sales`.

## Uploads

```bash
taxfind upload leads.csv --county Lee        # CSV/TSV/XLSX with any of: parcel/folio/account, address, unit, zip, owner
taxfind upload trim_notice.pdf --county Lee  # a TRIM notice or any text: parcel ids or street addresses are pulled out
```
Writes `<file>_matched.csv` with the matched parcel, match method (`parcel_id`, `address+zip`,
`fuzzy_in_zip`, `street_unique`, `ambiguous`, `unmatched`) and the screen's verdict.

## Autonomous on Naïve

See [`naive/`](naive/) and [`docs/NAIVE.md`](docs/NAIVE.md). In short: `naive login`, then
`QUALIFY_AGENT=agt_… ./naive/setup.sh` pushes the skill, uploads the code, creates the `find` agent
(bash + board + data tools, closed by default, $3 per run cap) and a cron deployment every 6 hours.
Each run processes only counties that posted new files and posts new strong/possible cases to the
Qualify agent's board, idempotent by `case_id`.

## Hand-off to Qualify

Contract: [`docs/HANDOFF.md`](docs/HANDOFF.md), machine-readable: `taxfind schema`.

## Expanding

- **More Florida**: nothing to do — new rolls are discovered automatically (preliminary in July, final in October).
- **Another state**: add `taxfind/desks/property_tax/<state>/` with `discover()` and `run_county()` that map
  the state's roll into the common columns `screen.py` reads, plus its `filing_window()`. Register it in
  `pipeline.DESKS`. See [`docs/EXPANSION.md`](docs/EXPANSION.md) for the calendar and rules by state.

## Known limitations

- **Storm-affected counties fail the self-check.** In Hillsborough, Pinellas, Sarasota, Manatee, Collier and
  Brevard (2026 roll), flagged homes did *not* sell below the county's value more often than other homes,
  most likely because hurricane-damaged neighbors and as-is sales drag the comparisons down. Those
  counties are marked `weak` and their cards are held automatically. Trimming outlier sales (IAAO-style,
  `trim_iqr`) was tested and did not fix it; a damage-aware rule is the next step.
- **Square footage is the county's effective area**, which can weight garages and porches. Comparisons are
  like-for-like within a county, but never quote it to an owner as living area.
- **Condo units**: some counties (e.g. Lee) leave the unit off the street address. Find recovers it from the
  owner's mailing address or the address format where it safely can; otherwise the unit is null and the
  condo isn't sent for a Zillow/Redfin lookup.
- **Tax rate** is an assumed 5.5 school + 9.5 other mills. Real rates vary by taxing district
  and city; swap in per-district rates before quoting savings.
- **The filing deadline** is estimated (25 days after a mid-August TRIM mailing). Each county's VAB posts the
  exact date.
- Not tested live: Naïve and Apify calls were exercised against their documented request shapes and in
  dry-run mode, not with real keys. See `docs/NAIVE.md` for what to confirm at the event.

## Configuration

Copy `.env.example`. Everything has a default; nothing is required for `--no-avm` runs.
