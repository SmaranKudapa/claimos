# AGENT_HANDOFF.md — taxappeal-find

Read this first. It is written for a coding agent (Claude Code or similar) picking up this project cold.
Last updated: 2026-11-07.

---

## 1. What the project is

A **property-tax appeal company run by AI agents**, built for the YC **Naïve Autonomous Company Hackathon**
(usenaive.ai). The company loop has 8 steps:

| # | Step | Owner | What it does |
|---|------|-------|--------------|
| 1 | **Find** | **Nick (this repo)** | Pull county tax rolls, flag over-assessed homes, attach the owner, hand off cases |
| 2 | Qualify | Smaran | Decide which cases are worth pursuing |
| 3 | Sign up | — | Owner signs an agreement (contingency fee) |
| 4 | Evidence | Fra | Build the comparable-sales evidence packet |
| 5 | File | Tarang | File the appeal (Florida: petition to the Value Adjustment Board) |
| 6 | Chase | — | Follow up on hearings and deadlines |
| 7 | Escalate | — | Hearing / further appeal |
| 8 | Collect | — | Collect the fee after the tax bill drops |

**This repo is only step 1, Find.** It must never contact owners or file anything.

Market: **Florida** first (all 67 counties publish rolls in one common format, for free), with templates for
more states so the business has filing windows year-round.

---

## 2. Hard rules (from the user — do not break)

1. **Never link this project to the user's trading bot or Obsidian vault.** No shared folders, configs, MCPs or memories.
2. **Never ask for, print, store or commit API keys.** The user types keys in his own terminal
   (e.g. `read -s "VAR?prompt: " && export VAR`). `.env` is gitignored and excluded from uploads.
3. Don't enter credentials anywhere on the user's behalf.
4. The user wants **short, exact, copy-paste** instructions. Never put `<placeholder>` in a command (zsh breaks on `<`);
   capture IDs automatically with `jq` instead.
5. Ignore hackathon sponsors (user's call) — **except** Monid is now being evaluated on its merits (section 8).
6. Apify is **not available** to the user any more. Don't propose it.

---

## 3. Where things live

| Place | Path | Notes |
|---|---|---|
| User's Mac (**source of truth**) | `~/Desktop/taxappeal-find` | Python 3.12 venv at `.venv` (system python3 is 3.9 — too old) |
| Install | `source .venv/bin/activate && pip install -e ".[dev]"` | CLI command is **`taxfind`** (not `find` — that shadowed Unix find) |
| Data dir | `FIND_DATA_DIR` (default `./data`) | downloads cache, `find.sqlite`, `screens/`, `out/<run_id>/` |
| Tests | `pytest -q` | 63 passing |

---

## 4. Code map

```
taxfind/
  cli.py            commands: sources, run, watch, upload, export, handoff, status, naive-tools, calendar, schema; loads .env
  config.py         ScreenParams (thresholds) + Settings (env vars)
  schema.py         candidate JSON schema v1 (the Find -> Qualify contract)
  pipeline.py       run counties -> save county stats -> stream outputs -> post cards (scoped to last_seen_run)
  engine/
    ingest.py       HttpCache (conditional GET + manifest), safe zip extract
    normalize.py    address/unit parsing (split_unit, unit_of, unit_from_legal), owner_type, vectorized *_series
    people.py       attach_owners (owner_id = hash(name+mailing), absentee, out_of_state, deed since roll), portfolio_rollup
    uploads.py      ParcelMatcher: match an uploaded list/document to parcels (strict fuzzy rules)
    store.py        SQLite: candidates, runs, county_stats, avm_cache, spend
    handoff.py      write_files (JSONL+CSV, streaming); post_cards (SQL-selected, idempotent by case_id)
    naive.py        NaiveClient (REST boards); dry-run writes to naive_outbox.jsonl
  desks/property_tax/
    screen.py       prepare, time_index, screen, evidence (the detection engine)
    florida/source.py   Florida DOR portal (SharePoint REST) reader; PARSE_VERSION=3
    florida/__init__.py filing_window, build_payloads, run_county (writes screens/FL_<cno>_<yr>.parquet)
    jurisdictions.py    filing calendar for many states
    new_state_template.py  how to add a state
  avm/
    providers.py    NaiveData, ZillowApify, RedfinApify, Mock + strict _match (address/ZIP/unit)
    enrich.py       budget-capped lookups, cache, carry_over; confirm >= 1.05, dispute < 0.95
naive/
  find.agent.yaml   Naïve agent definition
  find.system.md    agent's system prompt (install -> run -> publish -> report)
  SKILL.md          skill pushed to Naïve as "taxfind-find"
  setup.sh          5 steps: skill, upload code zip, agent apply, vault secrets, deploy create
  go.sh             one-shot: login check -> setup -> find agent/deployment -> run now
docs/  HANDOFF.md (schema for Qualify), NAIVE.md, EXPANSION.md, Find-on-Naive-guide.pdf
output/  statewide results (county_summary.csv, mail_ready_validated_counties.csv, all_candidates_statewide.zip)
```

---

## 5. How the Find screen works

Data: Florida DOR **NAL** (name-address-legal: every parcel, values, owner) + **SDF** (recorded sales), per county,
from `floridarevenue.com/property/dataportal` (files like `Lee 46 Final NAL 2026.zip`).

A home is flagged only if it fails **both** tests:

1. **Neighbor test** — assessed $/sqft vs similar peers (same neighborhood code; condos within their building;
   oversized neighborhoods split by section/township; blank neighborhood -> market area). Peers within
   ±20% size, ±10 yrs age, ±35% land. Fail if ratio **≥ 1.15** (min 8 peers).
2. **Sales test** — ≥ 3 comparable sales, time-adjusted to Jan 1, compared using the county's own
   value-to-price level. Fail if ratio **≥ 1.10**.

Then:
- **Savings** = school cut × 5.5 mills (on school AV) + other cut × 9.5 mills (on non-school AV), capped at taxable value.
- **Tiers**: `strong` (≥ $500/yr) · `possible` · `review` (own/later sale supports the value) ·
  `cap_absorbs` (homestead cap means no tax drop) · `new_build` · `none`.
- **County self-check (holdout)**: `validated` (lift ≥ 1.25, n ≥ 30) -> cards go out; `weak` -> cards held;
  `untested` (too few sales). `--include-closed` / `FIND_HANDOFF_INCLUDE_CLOSED=1` overrides the closed-window hold.

Thresholds are in `config.ScreenParams`. IQR trimming was tested and didn't help; default 0.

---

## 6. Results so far

- **Statewide run:** 67 counties, 7,702,332 homes, 24 min -> 87,934 strong, 30,034 possible.
- **11 validated counties** (incl. Miami-Dade, Broward, Palm Beach, Orange, Duval, Lee): 50,972 strong, ~$78.7M/yr savings.
- 17 weak counties held (mostly storm-hit Gulf coast).
- **Hendry** (small county, code 36): 8,998 homes -> 72 strong, 25 possible, ~$65.6k/yr; runs in ~4 s, ~406 MB peak.

---

## 7. Naïve setup (current state)

- CLI `@usenaive-sdk/cli` 1.0; user is logged in. Agent YAML applied with `naive agent apply -f naive/`.
- **Agent `find`**: model `z-ai/glm-5.3-flash` (no `window:` line — `loose` is unavailable for some models;
  `gpt-oss-120b` quit after one command, so it was replaced). Budget $30/month, $3/task. Tools deny-by-default.
- Code reaches the agent as an org file: `fetch_file` needs the **file id** `fil_8grx6bks1q11zazqzyddd3nxb1`
  (taxappeal-find.zip), not a filename. Re-upload + update the id in `find.system.md` whenever code changes.
- **No Qualify agent exists yet** -> cards go to the org's **orchestrator** board (`agt_hmr3fgs3qk4k2rsg7dtk7sk27b`).
  The agent has no `NAIVE_API_KEY`, so it posts cards itself with `board_write` (key = case_id).
- **Proven run:** session `ses_5xvbs8pe58qehn7kvxyvqr14qs`, run `FL-20261107T215256Z` (Hendry) — published
  `fil_0r3xfs52sc0wdqage1yq6g1j2q` (candidates.csv) and `fil_734mdr92d9ha8rsz26sphq94av` (summary.json).
- **Problem:** the agent box has ~958 MB RAM. **Lee was OOM-killed** (even with 2 GB swap). The scheduled
  deployment prompt still targets Lee.
- Useful commands: `naive agent list`, `naive deploy list`, `naive deploy run DEP_ID`,
  `naive session list --agent AGENT_ID`, `naive session events SES_ID --after-seq N --limit 100`,
  `naive session send SES_ID --message "..." --interrupt`, `naive agent spend AGENT_ID`.
- Known gotcha: on the user's Mac, a file copied over the bridge once stayed stale — verify file content after writing.

---

## 8. What we are working on right now

### A. Monid as a "freshness check" (in progress)
- Monid CLI is installed on the Mac (`monid 0.1.9`), key active, **$20 signup credit** (~$19.99 left).
- **Dead ends already tested:** Monid `zillow /get_property_details` ($0.01) and `/get_zestimate` ($0.03) need a
  Zillow **zpid**, and there is **no address -> zpid** endpoint; the test property also returned `zestimate: null`.
  Naïve's own data catalogue is the same Zillow wrapper (zpid-based). Apify unavailable.
- **Chosen endpoint:** `monid run -p anyapi -e /property_records.enformion -i '{"street":...,"city":...,"state":"FL","zip":...}' -w`
  - $0.1536 per call, billed only when a record is found. Input: `street`, `city`, `state` (required), `zip`.
  - Returns: apn, currentOwners, previousOwners, lastSalePrice, lastSaleUtc, ownerOccupied, ownerMailingAddress,
    foreclosureStage, assessed/market values, taxAmount, beds/baths/sqft, yearBuilt, etc. One address can return several parcels.
- **Plan:** add a Monid provider (shell out to the `monid` CLI) used just before handoff, **strong cases only,
  highest savings first, hard $ cap (~$3/run), cached, never twice per home**:
  - sale since the roll at/above assessed value -> move to `review`
  - different current owner -> `owner.may_have_changed = true`, update name
  - foreclosure -> hold the card
  - newer mailing address -> update for outreach
  - Match back by APN = parcel_id (normalize spaces/dots) before trusting a record.
- **Blocked on:** the exact CLI output shape. The user was asked to run `monid run --help` and one $0.15 test on a Hendry
  strong home (`7968 2nd Pl, LaBelle FL 33935`). Parse the JSON after the `Output` header, or use a JSON-output flag if `--help` shows one.

### B. Other open items
1. **Move the schedule from Lee to Hendry** (`naive deploy list` -> delete the Lee deployment -> `COUNTIES=Hendry bash naive/go.sh`).
2. **Cut memory** so large counties fit in ~1 GB (read NAL columns selectively, process by neighborhood chunks, downcast dtypes).
3. Confirm the Hendry cards actually appeared on the orchestrator board.
4. When a real Qualify agent exists (Smaran), point `NAIVE_QUALIFY_BOARD` / `QUALIFY_AGENT` at it.

---

## 9. Hand-off contract to Qualify

One JSON object per case (schema v1, `taxfind schema`). Key fields: `case_id` (`FL-<county>-<year>-<parcel>`),
`jurisdiction` (incl. `county_check.status`), `property`, `values`, `signals` (neighbor_ratio, sales_ratio, comps),
`estimate.annual_savings`, `tier`, `avm_check`, `owner` (name, mailing address, absentee, portfolio), `evidence`
(neighbors + comparable sales). Board card: title = address + yearly savings, body = JSON, key = case_id. See `docs/HANDOFF.md`.

---

## 10. Limits to be honest about

- Public data only: can't see condition, damage, or unrecorded upgrades — Qualify/Evidence must check.
- Savings use assumed millage (1.5%), not each parcel's exact rate.
- Florida petitions are due ~25 days after TRIM notices (mid-Aug–Sept); outside that window cards are held unless overridden.
- Zillow/Redfin scraping is against their terms; county sales are the primary, official evidence.
