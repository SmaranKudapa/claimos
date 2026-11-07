---
name: taxfind-find
description: How to run and read the taxfind Find program (over-assessed homes from public rolls).
---

# taxfind — Find step

## Commands
- `taxfind sources` — counties the state has published, with roll year and stage.
- `taxfind run --counties Lee,Collier [--no-avm] [--handoff file|board]` — one pass.
- `taxfind watch --once --handoff board` — autonomous pass: only counties with new files.
- `taxfind upload <file> --county <name>` — match a list (CSV/XLSX), a TRIM notice (PDF) or pasted
  text to parcels and say which ones have a case.
- `taxfind export --tiers strong,possible --out ./export` — JSONL + CSV from the database.
- `taxfind status` — recent runs and spend. `taxfind naive-tools` — find a home-value data tool.
- `taxfind schema` — the JSON schema of a candidate (what Qualify receives).

## Tiers
- **strong** — both signals (neighbors and sales), clean data, at least $500/yr at stake. Mail-ready.
- **possible** — both signals, less money. **review** — big gap or high value, or the
  Zillow/Redfin estimate disagreed: a person looks first. **cap_absorbs** — over-assessed, but the
  homestead cap means no savings. **new_build** — built in the last two years, set aside.

## Signals in each candidate
- `neighbor_ratio` — county $/sq ft ÷ median of similar homes in the same appraisal neighborhood.
- `sales_ratio` — county value ÷ (comparable sales time-adjusted to Jan 1 × county's normal level).
- `avm_ratio` — county value ÷ (Zillow/Redfin estimate × county's normal level). `avm_check`:
  confirmed (≥1.05), inconclusive, disputed (<0.95, demoted to review), no_unit (condo, unit unknown).

## Environment
`FIND_DATA_DIR`, `NAIVE_API_KEY`, `NAIVE_QUALIFY_BOARD` (the Qualify agent's `agt_` id),
`NAIVE_REAL_ESTATE_TOOL`, `APIFY_TOKEN`, `FIND_AVM_PROVIDERS` (default `naive,apify_zillow,apify_redfin`),
`FIND_AVM_BUDGET_USD` (default 5), `FIND_AVM_MAX_LOOKUPS` (default 300 per county).
