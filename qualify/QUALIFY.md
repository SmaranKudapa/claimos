# The Qualify Step — How It Works

Qualify is the gate between **Find** and **Sign up** in the Claim OS recovery engine (Property Tax desk first). It lives in `qualify/` at the repo root (next to `find/`), as a standalone TypeScript package next to the prototype. It takes every candidate property Find produces and decides, with reasons, whether the company should spend money pursuing it, by which filing route, and in what order. **It never contacts anyone and never files anything.**

This document explains the whole process end to end and maps every part of it to the code.

---

## 1. The big picture

```
Find ──► Qualify ──► Sign up ──► Evidence ──► File ──► Chase ──► Escalate ──► Collect
           │
           ├── QUALIFIED     → Sign up, highest priority first, up to the daily capacity
           ├── NEEDS_REVIEW  → a human approves, rejects, or edits
           ├── NEXT_CYCLE    → held until a filing window opens, then re-qualified
           ├── INCOMPLETE    → back to Find to enrich the record
           └── REJECTED      → not pursued (reason codes say why)
```

Everything after Qualify costs real money and reputation: outreach, evidence, filing fees, follow-ups. Qualify's job is to let through only claims that are **eligible, valuable, winnable, and fileable in time**.

### Design principles

| Principle | What it means in the code |
|---|---|
| **Cheap before expensive** | Stages run in cost order. Free checks run first; the LLM runs last and only on leads that survived everything else. |
| **Rules are data, not code** | Every threshold, window, comp rule, and eligibility rule lives in a versioned *desk config* (`config/*.json`). The code never names a jurisdiction. |
| **Rules decide; the LLM advises** | The LLM can flag a lead, exclude a comp, lower p(win), or send a lead to a human. It can never raise a lead's status or reject it on its own. |
| **Fail safe** | Any error, missing data, or uncertainty resolves to `INCOMPLETE` or `NEEDS_REVIEW`, never `QUALIFIED`. |
| **Conservative promises** | Savings use the cautious end of the value range, so the number shown to an owner is one we can stand behind. |
| **Explainable** | Every outcome has machine-readable reason codes, a stage-by-stage log, and a one-line summary. |
| **Deterministic** | Same inputs + same config version (+ the cached LLM review) → same decision. Safe to re-run any time. |

---

## 2. Quick start

```bash
cd qualify
npm install
npm test                 # 61 tests
npm run demo             # synthetic data, offline reviewer, no API key needed
npm run verify           # typecheck + tests + demo in one go
```

`npm run demo` also writes `out/demo-cases.json`: every result as a dossier-shaped case record for the Claim OS UI (see section 6).

With a real Naïve key:

```bash
cp .env.example .env     # fill QUALIFY_MODEL; the key can come from here or the repo-root .env
npm run qualify -- run \
  --candidates data/candidates.sample.json \
  --config config/desk.placeholder.json \
  --suppression data/suppression.sample.json
```

All CLI commands:

| Command | What it does |
|---|---|
| `qualify run --candidates F --config F [--suppression F] [--today D] [--llm naive\|mock\|off] [--out F] [--audit F] [--json]` | Qualify a batch, print the ranked table, write results and audit log |
| `qualify show --results F --case ID [--json]` | Show one case with its stage log and LLM checks |
| `qualify review --results F --case ID --by NAME --approve` | Approve a case in the review queue |
| `qualify review ... --reject CODE [--note TEXT]` | Reject a case with a reason code |
| `qualify review ... --exclude-comps A,B [--patch JSON] --candidates F --config F` | Edit a case and re-run it |
| `qualify cases --results F [--candidates F] [--config F] [--export F]` | Export results as Claim OS case records (prototype `caseRecord` fields + a Qualify beat) |
| `qualify validate-config --config F` | Check a desk config |
| `qualify codes` | List every reason code |

`--llm` defaults to `naive` when an API key is set and `off` otherwise. The key is read from `NAIVE_API_KEY` or, to match the rest of the repo (prototype server, Vercel functions), `VETTA_API_KEY`; likewise `NAIVE_API_BASE_URL` or `VETTA_API_BASE_URL`. The CLI loads `qualify/.env` first, then the repo-root `.env`, and never overwrites a variable that's already set. Pick a model with `vetta models list --human` and smoke-test it with `vetta proxy message --model <id> --text "hi"`. A key only needs the `proxy:write` scope: `vetta keys create --name qualify --scopes proxy:write`. `mock` uses an offline heuristic reviewer so you can demo the full pipeline without a key.

---

## 3. A lead's journey, stage by stage

```
S0 Intake ─► S1 Suppression ─► S2 Eligibility ─► S3 Valuation ─► S4 Economics ─► S5 Timing ─► S6 LLM review ─► S7 Decision
  free           free              free            low (comps)       free           free          highest           free
```

Each stage can stop a lead. A stopped lead skips every later stage. The pipeline lives in `src/pipeline.ts`; each stage is a file in `src/stages/`.

### S0 · Intake & validation — `s0-intake.ts`

*Is the record complete and trustworthy enough to judge?*

| Check | Rule | If it fails |
|---|---|---|
| Schema | Record matches `CandidateSchema` (`src/types.ts`) | `INCOMPLETE · I_SCHEMA` |
| Required fields | Required fields present (the error names which) | `INCOMPLETE · I_MISSING` |
| Sanity | Values > 0, plausible area and tax rate, no future dates | `INCOMPLETE · I_INVALID` |
| Freshness | Assessment is for the desk's valuation date; data fetched within `maxSourceAgeDays` | `INCOMPLETE · I_STALE` |
| Comps | Comps with impossible values are dropped (not fatal) | noted in the stage log |
| Normalize | Addresses and owner names cleaned; property types mapped through `propertyTypeAliases` | — |
| Dedupe | One record per (jurisdiction, parcel); newest fetch wins field group by field group | merged, not failed |

`INCOMPLETE` cases go back to Find with the exact missing or bad fields.

### S1 · Suppression — `s1-suppression.ts`

*Are we allowed to, and should we, pursue this owner?* This runs before any paid lookup.

| Check | Code |
|---|---|
| Rejected recently with identical inputs (same input hash and config version, within `rejectionCacheDays`) | `S_CACHED` (reuses the earlier reasons) |
| Parcel or owner on the do-not-contact list | `S_DNC` |
| Already a client, or an open case exists | `S_EXISTING_CASE` |
| Owner declined within `cooldownDays` | `S_COOLDOWN` |
| Represented by another agent | `S_REPRESENTED` |
| Government owner | `S_EXEMPT_OWNER` |

The suppression list is a JSON file (`data/suppression.sample.json` shows the shape). The rejection cache reads the previous run's results file.

### S2 · Hard eligibility — `s2-eligibility.ts`

*Can this claim legally be filed by us this cycle?*

| Check | Outcome |
|---|---|
| No desk config for this jurisdiction | `REJECTED · E_NO_DESK` |
| Property type not supported | `REJECTED · E_TYPE` |
| Appeal already on file this cycle | `REJECTED · E_ALREADY_FILED` |
| Fully exempt | `REJECTED · E_EXEMPT` |
| No owner name or mailing address | `INCOMPLETE · I_OWNER` |
| Trust, entity, estate, or several owners | flag `F_COMPLEX_OWNER` |
| Arm's-length sale within `transferLookbackDays` of the valuation date | flag `F_RECENT_TRANSFER` |
| Major permit since the prior valuation, or built in the last year | flag `F_VALUE_CHANGE` |

**Flags never reject.** They lower p(win) (if listed in `penalizedFlags`) or sign-up odds, and they send the lead to human review in S7.

### S3 · Valuation — `s3-valuation.ts`

*Is the property overassessed, by how much, and how sure are we?*

1. **Select comps.** A comp is kept only if it's arm's-length (if required), the same property type (if required), within `maxDistance`, within `sizeTolerance` of the subject's area, within `ageTolerance` years, and sold inside the window around the valuation date (`saleWindowBeforeDays` / `saleWindowAfterDays`). Survivors get a similarity score:

   ```
   similarity = 1 − (0.35·distance/maxDistance + 0.35·sizeDiff/sizeTolerance
                     + 0.20·daysFromValuationDate/window + 0.10·ageDiff/ageTolerance)
   ```

   The top `maxComps` by similarity are used.

2. **Estimate.** Each comp implies a subject value: `price ÷ comp area × subject area`. The estimate is the **median**; the range is the **25th–75th percentile**.

3. **Confidence (0–1).**

   ```
   confidence = min(1, comps/(minComps+2))          ← enough comps?
              × clamp(1 − 2·(high−low)/estimate, 0.3, 1)   ← do they agree?
              × (0.5 + 0.5·mean similarity)          ← how similar?
              − 0.05 per missing optional field (yearBuilt, lotArea)
   ```

4. **Target value (what we argue for).** The cautious end:

   ```
   target = min(assessed, estimate + (1 − confidence) × (high − low))
   gap    = assessed − target
   ```

   The less sure we are, the closer the target sits to the assessed value, and the smaller the claimed gap.

5. **Uniformity basis** (only if the desk allows it and Find supplied `neighborhood.medianAssessmentRatio`): `target = cautious market target × neighborhood ratio`. Every allowed basis with a positive gap is kept, best first; S5 decides which one is actually filed.

| Condition | Outcome |
|---|---|
| Comps never fetched | `INCOMPLETE · I_NO_COMPS` |
| Fewer than `minComps` usable comps | `REJECTED · V_INSUFFICIENT_COMPS` |
| No basis has a positive gap | `REJECTED · V_NO_GAP` |
| Best gap below `minGapPct` | `REJECTED · V_GAP_SMALL` |
| Confidence below `minConfidence` | `REJECTED · V_LOW_CONFIDENCE`, unless savings ≥ `highValueReviewThreshold`, in which case flag `F_LOW_CONFIDENCE` |

### S4 · Economics — `s4-economics.ts`

*Is it worth the money and effort?*

| Quantity | Definition |
|---|---|
| `annualSavings` | `gap × taxRate` (the value-based rate only) |
| `totalSavings` | annual savings over the route's persistence cycles, discounted at `discountRate` |
| `fee` | `feePct ×` (first-cycle or total savings, per `feeBasis`) |
| `pWin` | `sigmoid((gapPct − midpoint)/scale) × (floor + (1−floor)·confidence) × route multiplier × (1 − flagPenalty)^(penalized flags) + LLM adjustment`, capped at `cap` |
| `pSignup` | `pSignupPrior`, × `complexOwnerSignupFactor` for complex owners |
| `preCosts` | spent on every lead we contact (enrichment, outreach, LLM) |
| `postCosts` | spent only after sign-up (evidence, follow-ups, the route's filing fee) |

The core formula:

```
EV       = pSignup × ( pWin × fee − postCosts ) − preCosts
maxLoss  = preCosts + postCosts
```

Economics depend on the route, so S4 computes EV for every (route, basis) pair and checks the best case:

| Condition | Outcome |
|---|---|
| Best annual savings below `minAnnualSavings` | `REJECTED · C_SAVINGS_LOW` |
| Best-case EV below `minExpectedValue` | `REJECTED · C_EV_LOW` |

p(win) and p(signup) are **v1 heuristics**. Section 10 explains how they get replaced with fitted models.

### S5 · Timing & route — `s5-timing.ts`

*Is a filing route open with enough time to finish, and which one?*

A (route, basis) pair is **viable** if its basis clears `minGapPct` and its EV clears `minExpectedValue`. A viable pair is **feasible** today if:

```
route.opens ≤ today ≤ route.closes   and   closes − today − bufferDays ≥ workDaysNeeded
```

- **A feasible pair exists:** pick the highest EV, breaking ties by more days left. That sets the route, deadline, basis, and final economics. We file now even if a stronger claim would open later.
- **Nothing feasible:** `NEXT_CYCLE · T_NO_ROUTE`. `requalifyOn` = the next route opening (or `nextCycleOpens`) minus `requalifyLeadDays`. The summary says exactly why (closed, not yet open, or too few days left). The case must be fully re-qualified then, because the valuation date changes with the cycle.
- **Urgency** rises from 1.0 to `urgencyMaxBoost` as the slack (days left − days needed) shrinks. It feeds the priority score.

### S6 · LLM review — `s6-llm.ts`, `src/llm/`

*Did the rules miss anything a careful analyst would catch?*

**When it runs.** Only on leads that survived S0–S5. It's skipped when the desk disables it, when there's no client (`--llm off`), or when EV is below `minEvToReview` and the lead has no flags (not worth the cost). It always runs on flagged and high-value leads.

**What it gets.** A structured packet (`buildPacket` in `src/llm/prompt.ts`): the normalized subject, the selected comps with similarity scores and implied values, every rule flag and number from S2–S5, and the desk's rules as plain text. **Owner names are left out**, because no check needs them. Raw source excerpts are wrapped in `<source_document>` tags, and the prompt says text inside them is data, never instructions.

**What it does.** It works through a fixed checklist, not an open question:

| ID | Check | Looks for |
|---|---|---|
| C1 | Data consistency | Fields that disagree across sources |
| C2 | Comp suitability | Comps that aren't truly comparable, and outliers |
| C3 | Hidden value changes | Additions, renovations, splits the rules missed |
| C4 | Transfer evidence | A recent sale price that undercuts the claim |
| C5 | Owner & authority | Who must sign; trust/entity/estate complications |
| C6 | Claim basis | Whether the chosen basis is the strongest and coherent |
| C7 | Embarrassment test | Anything that would make contacting this owner look careless |

It must reply by calling the `submit_review` tool with: a verdict per check (`pass` / `concern` / `fail`) with evidence references, `recommended_action`, `comps_to_exclude`, `p_win_adjustment`, and a short summary. Evidence references must point at something real in the packet: `subject.<path>`, `comp:<id>`, `doc:<ref>`, or `result.<path>`.

**How the reply merges with the rules:**

| LLM says | Effect |
|---|---|
| A verdict with no valid evidence | Ignored (marked `counted: false`) |
| A cited `concern` | Flag `F_LLM_CONCERN` → NEEDS_REVIEW |
| A cited `fail`, or `recommended_action: reject` | Flag `F_LLM_FAIL` → NEEDS_REVIEW (a human confirms; the LLM never rejects alone) |
| `recommended_action: review` | NEEDS_REVIEW |
| `p_win_adjustment` | Clipped to [−0.30, +0.05], then S3–S5 re-run on a copy |
| `comps_to_exclude` | Unknown ids dropped; S3–S5 re-run once on a copy, deterministically, with no second LLM call |
| The re-run would stop the lead | Keep the original numbers; flag `F_LLM_FAIL` → NEEDS_REVIEW |
| Excluding comps would *raise* EV | Keep the original numbers; flag `F_LLM_COMPS_FAVORABLE` → NEEDS_REVIEW |
| Excluding comps lowers or keeps EV | Adopt the new numbers |

> **The one-way rule:** the LLM can only keep a lead's status or move it toward more caution. It never runs on stopped leads, never removes a flag, and anything it would use to stop a lead becomes a human decision instead.

**Reliability and cost:**

- The reply is schema-validated (`LlmOutputSchema`). An invalid reply is retried once with the validation error. A second failure (or a network error) adds `F_LLM_UNAVAILABLE` → NEEDS_REVIEW.
- If the model calls no tool but returns JSON text, that's parsed as a fallback.
- Pre-flight cost estimate: if it exceeds `maxCostPerLeadUsd`, the review is skipped and flagged. Actual cost is computed from token usage and the configured prices.
- **Escalation:** if an escalation model is set, the lead is high value, and the first review is worried (any non-pass or a non-proceed action), it's re-reviewed by the stronger model and that answer is used.
- **Cache:** reviews are cached by hash(model + prompt version + packet + source docs) in `.cache/llm/`. Unchanged leads are never reviewed twice, which is also what makes runs reproducible: Naïve's model proxy doesn't accept a temperature setting.
- `promptVersion` is pinned in the config. Changing the prompt means bumping it, which invalidates the cache.

**Where the model comes from.** `src/llm/naive.ts` calls Naïve's model proxy through `@usenaive-sdk/managed-agents` (`client.proxy.messages`): one org-level call with no agent and no session. The model id comes from `QUALIFY_MODEL` (or `llm.model` in the config). `src/llm/mock.ts` has two offline reviewers: `HeuristicReviewer` for demos and `ScriptedReviewer` for tests.

**No OpenAI / OpenRouter calls.** This step's only model call goes through Naïve's proxy. If the team ever stops using the proxy, add a fourth client at `src/llm/<provider>.ts` that implements `LlmClient` (one forced tool call named `submit_review`), wire it into the CLI as `--llm <provider>`, and fill in three placeholders: the provider base URL, the API key env var (e.g. `OPENAI_API_KEY` or `OPENROUTER_API_KEY`), and the model id. That slot is documented, not built.

### S7 · Decision & ranking — `s7-decision.ts`

The first match wins:

| # | Condition | Status |
|---|---|---|
| 1 | Any `I_` code | INCOMPLETE |
| 2 | Any `S_`, `E_`, `V_`, `C_` code | REJECTED |
| 3 | `T_NO_ROUTE` | NEXT_CYCLE |
| 4 | Any `F_` flag, any forced review, or annual savings ≥ `highValueReviewThreshold` while `reviewHighValue` is on (adds `F_HIGH_VALUE`) | NEEDS_REVIEW |
| 5 | Everything else | QUALIFIED |

```
priority = EV × urgency × (0.5 + 0.5 × confidence)
```

**Capacity-aware release.** `qualifyAll` sorts by status, then priority. Only the top `dailyReleaseLimit` QUALIFIED cases get `releaseDate = today`; the rest stay queued and are re-ranked on the next run as deadlines get closer.

`decidedBy` is `rules`, `llm` (when the LLM alone sent the lead to review), or `human:<name>`.

---

## 4. Human review — `src/review.ts`

| Action | Allowed on | Result |
|---|---|---|
| **Approve** | NEEDS_REVIEW only | QUALIFIED; picked up by the next release |
| **Reject** (with a known reason code) | Anything not already rejected | REJECTED with `H_REJECTED` + the given code |
| **Edit** (exclude comps, patch fields) | Any case | Re-runs the pipeline **without the LLM**. If it still survives, it stays NEEDS_REVIEW until someone approves it |

A lead that failed a hard rule never reaches the queue, so reviewers can't approve around the rules. Every action stamps `audit.review` (who, what, when, note) and appends to the audit log. Reviewer decisions are the labels for tuning thresholds and evaluating the LLM (section 10).

---

## 5. Inputs

### Candidate (from Find) — `CandidateSchema` in `src/types.ts`

| Group | Fields | Required |
|---|---|---|
| Identity | `parcelId`, `jurisdictionId`, `situsAddress`, `propertyType`, `useCode?` | yes (except `useCode`) |
| Owner | `names[]`, `type` (individual · joint · trust · entity · estate · government), `mailingAddress?`, `ownerOccupied?` | `names`, `type` |
| Assessment | `assessedValue`, `valuationDate`, `taxRate`, `history?[]`, `exemptions[]` | value, date, rate |
| Physical | `livingArea`, `lotArea?`, `yearBuilt?`, `lastPermitDate?`, `permitTypes[]` | `livingArea` |
| Transfer | `{ date, price, armsLength }` | no |
| Neighborhood | `{ medianAssessmentRatio }` (uniformity basis only) | no |
| Comps | `[{ compId, price, saleDate, livingArea, propertyType, yearBuilt?, distance, armsLength }]` | no (absent → `I_NO_COMPS`) |
| Status | `appealOnFile`, `priorAppealOutcome?`, `existingCaseId?` | `appealOnFile` |
| Provenance | `fetchedAt`, `sources{}`, `rawDocs[{ ref, kind, text }]` | `fetchedAt` |

Dates are `YYYY-MM-DD`. `taxRate` is a fraction (value-based levies only). `distance` is in whatever unit the desk's `maxDistance` uses.

### Desk config — `DeskConfigSchema` in `src/types.ts`

One file per jurisdiction per cycle, validated on load. A bad config stops the run instead of producing wrong decisions. See `config/desk.placeholder.json`.

| Section | Contents |
|---|---|
| `version` | Recorded on every result and in the rejection cache |
| `jurisdiction` | `id`, `name`, `valuationDate`, `supportedPropertyTypes`, `propertyTypeAliases`, `allowedClaimBases`, `reductionPersistenceCycles`, `discountRate`, `majorPermitTypes` |
| `routes[]` | `id`, `name`, `formId`, `opens`, `closes`, `filingFee`, `workDaysNeeded`, `bufferDays`, `filer`, `authorizationRequired`, `claimBases`, `pWinMultiplier`, `reductionPersistenceCycles?` |
| `nextCycleOpens` | Used for `requalifyOn` when no listed route opens later |
| `compRules` | `maxDistance`, `sizeTolerance`, `ageTolerance`, `saleWindowBeforeDays`, `saleWindowAfterDays`, `minComps`, `maxComps`, `armsLengthOnly`, `sameTypeOnly` |
| `thresholds` | `minGapPct`, `minAnnualSavings`, `minExpectedValue`, `minConfidence`, `highValueReviewThreshold`, `reviewHighValue`, `transferLookbackDays`, `maxSourceAgeDays` |
| `economics` | `feePct`, `feeBasis`, `preCosts{}`, `postCosts{}`, `pSignupPrior`, `complexOwnerSignupFactor`, `pWin{ midpointGapPct, scale, cap, confidenceFloor, flagPenalty, penalizedFlags }` |
| `timing` | `requalifyLeadDays`, `urgencyMaxBoost` |
| `suppression` | `cooldownDays`, `rejectionCacheDays` |
| `llm` | `enabled`, `model`, `escalationModel`, `promptVersion`, `window`, `maxTokens`, `maxCostPerLeadUsd`, `priceUsdPerMTokIn/Out`, `minEvToReview`, `deskRulesText` |
| `capacity` | `dailyReleaseLimit` |

**The placeholder config is made up.** Every date, fee, and threshold in it exists only so the pipeline runs. Before using real results, write a config with your jurisdiction's actual valuation date, filing routes, fees, and comp rules.

---

## 6. Outputs

### QualifyResult

| Field | Contents |
|---|---|
| `caseId`, `parcelId`, `jurisdictionId`, `address` | Identity (`caseId = case_<jurisdiction>_<parcel>`) |
| `status` | QUALIFIED · NEEDS_REVIEW · NEXT_CYCLE · INCOMPLETE · REJECTED |
| `reasonCodes[]`, `flags[]` | Machine-readable codes (section 7) |
| `summary` | One plain-English line for the dashboard |
| `stageLog[]` | `{ stage, outcome: pass/stop/skip, detail }` for every stage that ran |
| `valuation` | estimate, low, high, confidence, comps used (with similarity and implied value), comps excluded, every basis option, the chosen basis, target, gap, gap % |
| `economics` | annualSavings, totalSavings, fee, pWin, pSignup, preCosts, postCosts, ev, maxLoss |
| `route` | id, name, formId, deadline, daysLeft, urgency |
| `priority`, `releaseDate` | Ranking, and whether it went to Sign up today |
| `requalifyOn` | For NEXT_CYCLE |
| `llm` | ran or skipped (and why), model, promptVersion, each check with evidence and whether it counted, recommendation, adjustment, exclusions, summary, cost, cached, escalated |
| `audit` | configVersion, inputHash, decidedAt, decidedBy, review |

The CLI writes all results to `out/results.json`.

### Case records for the Claim OS UI — `src/case.ts`

The repo has no shared Case schema yet; the UI reads a `caseRecord` object and a list of `claimBeats` (`prototype/assets/demo-data.js`). `toCaseRecord(result, { candidate?, config?, deskName? })` and `toQualifyBeat(result)` map a QualifyResult onto those shapes, so the dossier can show real Qualify output without the UI knowing Qualify's internals. `qualify cases` does the same from the command line.

| UI field | From |
|---|---|
| `id` | `caseId` |
| `desk` | `deskName` option (default "Property Tax") |
| `claimant` | the candidate's owner names (null without the candidate) |
| `address`, `apn` | `address`, `parcelId` |
| `assessedValue` | the candidate's assessed value (or target + gap) |
| `proposedValue` | `valuation.target`: the cautious value we'd argue for |
| `potentialRecovery` | `economics.annualSavings` |
| `probability`, `expectedValue`, `estimatedFee` | `economics.pWin`, `economics.ev`, `economics.fee` |
| `filingFee` | the chosen route's `filingFee` (needs the config) |
| `caseCost` | `economics.maxLoss` − filing fee |
| `deadline` | `route.deadline`, formatted like "Dec 18, 2026" |

Money fields are null for INCOMPLETE and REJECTED leads, so the UI never shows a value for a lead the company won't pursue. Each record also carries `status`, `summary`, `reasonCodes`, `flags`, `confidence`, `routeName`, `formId`, `priority`, `releaseDate`, `requalifyOn`, `decidedBy`, `configVersion`, and the full result under `qualify`. The beat uses the prototype's `{ id, label, title, kicker, summary, source, value, actor, state }` shape, with `state` one of `qualified`, `review`, `waiting`, `incomplete`, `rejected`.

When the team adds a real shared Case type, map onto it here (or store the result under `case.qualify`) rather than changing the pipeline.

### Audit log — `src/audit.ts`

`out/audit.jsonl` gets one JSON line per decision and per review action: input hash, config version, status, codes, flags, every stage's outcome, the full LLM review, and who decided. It's append-only. It answers "why did the agent contact this person?" and lets you replay old decisions against a new config.

---

## 7. Reason codes

Run `qualify codes` for the live list (`src/codes.ts`). **The prefix decides the status.**

| Prefix | Status | Codes |
|---|---|---|
| `I_` | INCOMPLETE | `I_SCHEMA`, `I_MISSING`, `I_INVALID`, `I_STALE`, `I_OWNER`, `I_NO_COMPS` |
| `S_` | REJECTED | `S_DNC`, `S_EXISTING_CASE`, `S_COOLDOWN`, `S_CACHED`, `S_REPRESENTED`, `S_EXEMPT_OWNER` |
| `E_` | REJECTED | `E_NO_DESK`, `E_TYPE`, `E_ALREADY_FILED`, `E_EXEMPT` |
| `V_` | REJECTED | `V_INSUFFICIENT_COMPS`, `V_NO_GAP`, `V_GAP_SMALL`, `V_LOW_CONFIDENCE` |
| `C_` | REJECTED | `C_SAVINGS_LOW`, `C_EV_LOW` |
| `T_` | NEXT_CYCLE | `T_NO_ROUTE` |
| `F_` | NEEDS_REVIEW | `F_COMPLEX_OWNER`, `F_RECENT_TRANSFER`, `F_VALUE_CHANGE`, `F_LOW_CONFIDENCE`, `F_HIGH_VALUE`, `F_LLM_CONCERN`, `F_LLM_FAIL`, `F_LLM_COMPS_FAVORABLE`, `F_LLM_UNAVAILABLE` |
| `H_` | REJECTED | `H_REJECTED` (a reviewer's decision) |

---

## 8. When to re-run Qualify

Qualify is stateless and safe to re-run. The engine (or a scheduled task) should run it when:

| Trigger | Why | How the code handles it |
|---|---|---|
| New or updated data for a parcel | Inputs changed | New input hash, so the rejection cache doesn't apply |
| A window opens (`requalifyOn` reached) | NEXT_CYCLE cases become live | Run with the new cycle's config |
| Desk config version changes | Rules moved | Config version is part of the cache key |
| Right before outreach is sent | Suppression and freshness can change | Sign up should re-run S0–S1 on the case |
| After sign-up, before filing | Confirm the route is still feasible | Re-run the case with today's date |
| A reviewer edits a case | Correction applied | `review --exclude-comps / --patch` re-runs it |

---

## 9. Project layout

```
qualify/
├── QUALIFY.md                  ← this document
├── README.md                   ← setup and commands
├── config/desk.placeholder.json  ← example desk config (made-up values)
├── data/                       ← synthetic sample candidates + suppression list
├── scripts/make-sample-data.ts ← regenerates the sample data (seeded)
├── src/
│   ├── types.ts                ← schemas: Candidate, DeskConfig, Suppression, QualifyResult
│   ├── codes.ts                ← reason codes and prefix → status
│   ├── config.ts               ← load + validate desk config and suppression list
│   ├── draft.ts                ← per-lead working state, QualifyContext, stop()
│   ├── pipeline.ts             ← qualify() and qualifyAll(): S0 → S7, dedupe, release
│   ├── stages/s0-intake.ts … s7-decision.ts
│   ├── llm/client.ts           ← LlmClient interface + caches
│   ├── llm/naive.ts            ← Naïve model proxy client
│   ├── llm/prompt.ts           ← checklist, packet, prompts, output schema, evidence refs
│   ├── llm/mock.ts             ← offline reviewers (heuristic, scripted)
│   ├── review.ts               ← approve / reject / edit
│   ├── audit.ts                ← JSONL audit log
│   ├── case.ts                 ← QualifyResult → Claim OS case record + Qualify beat
│   ├── report.ts               ← CLI table and case view
│   ├── cli.ts                  ← command line
│   └── index.ts                ← public API for other steps
└── test/                       ← 61 tests (stages, config validation, LLM merge rules, review, Naïve wiring, UI adapters, sample set)
```

Use it from another step:

```ts
import { qualifyAll, loadDeskConfig, NaiveLlmClient, naiveCredentialsFromEnv, FileLlmCache, SuppressionSchema, toCaseRecord } from "taxappeal-qualify"; // or a relative path to qualify/src/index.js

const config = loadDeskConfig("config/my-desk.json");
const { results } = await qualifyAll(candidatesFromFind, {
  config,
  today: "2026-11-05",
  suppression: SuppressionSchema.parse(suppressionList),
  priorResults: new Map(),
  llm: new NaiveLlmClient(naiveCredentialsFromEnv()), // NAIVE_API_KEY or VETTA_API_KEY
  llmCache: new FileLlmCache(".cache/llm"),
  models: { primary: process.env.QUALIFY_MODEL!, escalation: null },
});
const toSignUp = results.filter((r) => r.status === "QUALIFIED" && r.releaseDate);
const dossiers = results.map((r) => toCaseRecord(r, { config })); // for the control-room UI
```

---

## 10. The learning loop (after the hackathon)

The heuristics are deliberately simple and every one is a config value, so they can be replaced with real data as it arrives:

- **p(win):** once Chase reports outcomes (won/lost, reduction granted), fit p(win) by segment and replace the sigmoid. Track calibration: of cases predicted at 70%, about 70% should win.
- **p(signup):** learn from Sign up by owner type, savings size, and channel.
- **Target value:** compare the target with the value actually granted; tighten or loosen the conservative adjustment.
- **Thresholds:** tune `minGapPct`, `minConfidence`, and `minExpectedValue` from reviewer decisions and outcomes.
- **LLM evaluation:** every reviewer decision becomes a labeled example. Before changing the model or prompt, re-run the set and compare agreement with reviewers and the false-proceed rate.

Metrics to watch: qualified → signed rate, win rate on filed cases, review-queue rate, reviewer agreement with the LLM, cost per qualified lead, and deadline misses after qualifying.

---

## 11. Decisions made while building (vs. the design PDF)

These fill gaps the design left open, each in the more cautious direction:

1. **Any LLM concern sends the lead to review.** The PDF had two slightly different rules (concerns force review "if high value" in S6, but "any concern" in S7). The code follows the stricter S7 rule.
2. **The LLM can't reject indirectly either.** If its p(win) adjustment or comp exclusions would push a lead below a threshold, the lead goes to a human (`F_LLM_FAIL`) instead of being rejected.
3. **Comp exclusions can't inflate a claim.** If dropping the comps the LLM flagged would raise EV, the original numbers are kept and a human decides (`F_LLM_COMPS_FAVORABLE`).
4. **Viable before feasible in S5.** A claim basis only counts if it clears the gap and EV minimums. If the only strong basis is fileable on a closed route, the lead becomes NEXT_CYCLE instead of being filed now on a weak basis.
5. **Edits skip the LLM.** Once a human is reviewing, the LLM doesn't run again on that case.
6. **Determinism without temperature.** Naïve's proxy doesn't take a temperature, so reproducibility comes from the review cache and the pinned prompt version.

## 12. Known limits of v1

- **Placeholder config and synthetic data.** Nothing in `config/` or `data/` is real.
- **Valuation is price-per-area only.** There are no time or feature adjustments to comps yet.
- **p(win) and p(signup) are heuristics** until outcome data exists.
- **Suppression and prior results are JSON files.** Move them to the shared database when the steps are wired together.
- **Model prices in the config are placeholders.** Set them from Naïve's pricing for your model so the cost cap is accurate.
