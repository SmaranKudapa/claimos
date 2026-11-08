# Escalate ("Appeal again"): design

## What it decides

| County decision | Escalate, automatically |
|---|---|
| Full win | COLLECT (`W_FULL_WIN`) |
| Partial reduction | Appeal the rest only if it is above the owner's sign-up threshold, the next level is open to us and it is worth it; otherwise accept (`W_PARTIAL_ACCEPTED`). No preference on file means accept. |
| Denial | Appeal at the next level if authorized, in time, safe and worth it (`A_NEXT_LEVEL`, `A_FAST_TRACK`); otherwise close with a reason (`C_…`). |
| Dismissed, fixable (missing form, signature, authorization) | Fix and refile at the same level if the config allows and there is time (`A_REFILE_SAME_LEVEL`). |
| Dismissed, not fixable (late) | Close (`C_PROCEDURAL_BAR`). |
| Not final (hearing scheduled) | PENDING with a date to check again (`P_HEARING_SCHEDULED`, `P_NOT_FINAL`). |
| Can't tell | Second read with a stronger model → ask Chase to clarify (`P_CLARIFY`) while there is time → treat as a denial (`F_ASSUMED_DENIAL`) and let the economics decide. |
| Next level needs a licensed representative | Close for ClaimOS and tell the owner they can continue with one (`C_REFER_OUT`). |

Statuses and where they go (all automatic): ESCALATE → Evidence (with `evidenceRequests`) → File · COLLECT → Collect · CLOSED → closed with a reason · PENDING → Chase at `requeueOn` · INCOMPLETE → Chase re-fetches the document. Every status except INCOMPLETE carries an `ownerUpdate` that the coordinator or communications agent sends through the owner's consented channel.

## Principles

1. **No human in the loop.** No status, code, command or config option routes a case to a person. A test runs every sample and 300 random cases and checks this, and scans `src/` for review-queue code.
2. **Rules decide; the AI only reads.** A reader extracts facts. Code makes every decision.
3. **Every fact quotes the letter.** `reader/verify-quotes.ts` drops any fact whose quote is not in the letter (ignoring case and whitespace). A dropped outcome becomes "unclear".
4. **Numbers beat labels.** A verified new value decides the outcome (≤ target: full win; below assessed: partial; equal: denied; above: denied against the higher value, `F_VALUE_INCREASED`). Wording that disagrees triggers a second read.
5. **Conservative machine fallbacks.** Second read, then a clarification request to Chase, then a safe default. A partial win is never put at risk: whenever appealing the rest is blocked, the partial win is accepted (`F_ESCALATION_BLOCKED`), never closed.
6. **Owner choices are collected up front** (Sign up) and applied here; Escalate never stops to ask.
7. **Rules are data.** The appeal ladder, deadlines, fees, fallbacks and probability adjustments live in a versioned desk config. Engine code never names a jurisdiction (a test enforces it).
8. **Deterministic and auditable.** Same case, decision, config version and reading → same result. Each result carries its stage log, input hash and config version; each run appends to `out/audit.jsonl`.
9. **Honest numbers.** Owner updates are templates; their dollar figures come only from the case's assessed value or a quote-verified new value (a test enforces it). They promise nothing.

## Pipeline

| Stage | Does | Stops with |
|---|---|---|
| E0 Intake | Shape, jurisdiction, case and level match, letter text; input hash | `I_SCHEMA`, `I_WRONG_DESK`, `I_CASE_MISMATCH`, `I_LEVEL_MISMATCH`, `I_NO_DECISION_TEXT` |
| E1 Read | Reader → quote check → numbers beat labels → second read → clarify / assumed denial; reader failures retry | `P_READ_RETRY`, `P_CLARIFY` |
| E2 Route | Wins, waits and technicalities | `W_FULL_WIN`, `P_HEARING_SCHEDULED`, `P_NOT_FINAL`, `A_REFILE_SAME_LEVEL`, `C_PROCEDURAL_BAR` |
| E3 Next level | Next rung, licensed rep, authorization, deadline (earlier of letter and rule), fast track, reopen risk | `C_LADDER_END`, `C_REFER_OUT`, `C_NOT_AUTHORIZED`, `C_DEADLINE_PASSED`, `C_DEADLINE_TOO_CLOSE`, `C_REOPEN_RISK` |
| E4 Economics | gap, annual savings, fee revenue, P(win) × rung × denial-reason multipliers, costs, EV | `C_SMALL_GAP`, `C_LOW_PWIN`, `C_LOW_EV` |
| E5 Preferences | Partial mode: the owner's threshold | `W_PARTIAL_ACCEPTED` |
| E6 Evidence + budget | Evidence requests from the denial reasons; daily filing-fee budget, best EV first | `P_BUDGET`, `C_BUDGET` |
| E7 Decision | Status from the code prefix (I_ > P_ > C_ > W_ > A_); summary; owner update | `A_NEXT_LEVEL`, `A_FAST_TRACK`; `C_UNHANDLED` if nothing applied |

`F_` codes are flags and never change the status.

## Inputs and handoffs

- **Case** (`EscalateCaseSchema`): the team's case id (Find's `case_id`), parcel, jurisdiction, owner and consented channel, assessed and target values, tax rate, Qualify's P(win), current level, filings, authorization (scope and escalation preferences), prior decisions, read attempts.
- **Decision** (`CountyDecisionSchema`): decision id, case id, level, received date, channel, full letter text.
- **readState**: every PENDING from the reader returns `readState`; Chase sends it back as `readAttempts` so retries and clarification resume and always end.

## What other steps need to do

- **Sign up** must record `authorization.scope` (levels the owner authorizes, or `all_levels`) and `authorization.escalation` (`appealPartialIfRemainingAnnualAbove`, `acceptReopenRisk`). Until then the samples carry them.
- **Chase** currently attaches only the first lines of a county reply as a card comment. Escalate needs the full letter text and the case.
- **File** still stops at `ready_for_operator_review` before submitting, so re-filings from Escalate wait there.

## Naïve

- The AI reader (`reader/naive.ts`) calls Naïve's model proxy (`client.proxy.messages`), forces one structured `submit_reading` call, validates it with zod, retries once, caps cost per case across both reads, and caches readings by (decision id, text hash, prompt version, model).
- Naïve's audit log is read-only through the API (`auditLogs.list`), so decisions are recorded in `out/audit.jsonl` and, when run as an agent, in the agent's session and board updates.
