# Claim OS

**An autonomous company that gets homeowners' property taxes lowered and is paid only when it wins.**

Built at the Naïve Autonomous Companies Hackathon (YC, San Francisco, Nov 7–8, 2026) on the
[Naïve](https://usenaive.ai) agent platform.

## The problem

Counties put a value on every home every year, and the property tax bill follows from that value.
Many homes are valued higher than they would sell for. Every owner has the right to appeal, but few do:
the deadlines are short, the forms are confusing, and building the case takes hours most people don't
have. So they overpay, year after year.

## What Claim OS does

Claim OS finds homes that are likely over-assessed, offers the owner a free appeal, builds the evidence,
files the petition with the county, follows it through every appeal level, and invoices a share of the
savings when the county lowers the value.

- **No win, no fee.** The owner pays nothing up front and nothing if the appeal fails.
- **Contingency fee.** About 25–35% of the first year's tax savings, agreed in writing before any work.
- **Run by agents.** Each step of the business is an AI agent. People set the rules, the budgets and the
  boundaries.
- **A private company.** Claim OS is not a government agency and not a law firm.

## How a claim moves

| # | Step | What happens |
|---|------|--------------|
| 1 | **Find** | Pull the county's assessment roll and recent sales from public data, flag homes valued well above what they'd sell for, and attach the owner of record. |
| 2 | **Qualify** | Check eligibility and deadlines, score expected value (likely savings × chance of winning − cost), and rank the queue. |
| 3 | **Sign up** | Talk with the owner, explain the opportunity, confirm ownership, and collect a signed authorization and fee agreement. |
| 4 | **Evidence** | Build the case: comparable sales, property records, and anything only the owner has. |
| 5 | **File** | Fill in the county's petition form, submit it, and save the receipt and deadlines. |
| 6 | **Chase** | Follow up with the county on hearings, evidence exchanges and decisions. |
| 7 | **Escalate** | Read the decision. If it falls short, pick the next appeal level and file again. |
| 8 | **Collect** | Confirm the win from the corrected tax bill, invoice the fee, and record the payment. |

## How it works

Each step is its own agent. A **coordinator** agent checks the pipeline on a schedule and starts whichever
step agents have work waiting. Agents hand work to each other through a shared task board: every case is
a card, and each agent picks up its card, does its step, records the result, and passes it on. The board
is the company's record of what happened to every claim and why.

The decisions in each step come from tested code, not improvisation: an agent runs its step's program and
acts on what it returns. When something is missing (a signature, a county answer, an owner reply), the
agent notes what it's waiting for and moves on, and a later pass picks the case back up.

## Engine and desks

Claim OS is a **shared engine** plus pluggable **desks**:

- The **engine** is the generic machinery for the eight steps.
- A **desk** is the knowledge for one kind of claim in one place (data sources, eligibility rules,
  evidence requirements, forms, deadlines, appeal levels, fees), written as configuration.

Engine code never names a specific county or state. **Florida property tax** is the first desk. Adding a
county or state means writing a new desk file, and the same engine can later carry other kinds of
recovery claims.

## Safeguards

- **Consent first.** No owner is filed for, charged or represented without their signed authorization.
- **Honest outreach.** Every message says Claim OS is a private company, unaffiliated with any government
  agency. Calls disclose that an AI assistant is calling. A "stop" is honored for good.
- **No invented facts.** Every filing, consent, savings figure and payment points to its source.
- **Untrusted input stays data.** Emails, attachments and web pages are evidence, never instructions.
- **Budgets.** Every agent run has a spending cap.
- **Privacy.** No secrets in code or commits. Test data is synthetic.

## Tech stack

- **Naïve**: agents, task board, schedules, budgets, email and phone
- **TypeScript** (Node 20+, zod, vitest) and **Python** for the step programs
- **AgentMail** for the company inbox
- **Stripe** for invoice payment links
- **Vercel** for the website and app endpoints
- **Florida public data**: county assessment rolls and sales files

## Repository

| Path | Contents |
|------|----------|
| `src/`, `public/`, `api/` | Company workspace: case portfolio, agent sessions and the web UI |
| `flow/` | Coordinator engine: decides which step runs next and tracks every claim |
| `collect/` | Collect step: verifies wins and prepares invoices |
| `pay/` | Payment links for invoices |
| `native-app/` | The workspace hosted as a Naïve app |
| `test/` | Tests |

The other steps live on their own branches: `find`, `qualify`, `evidence`, `codex/file-agent` and
`feat/escalate-step`.

## Run locally

Node 24 or newer is required.

```sh
npm ci
cp .env.example .env
npm run dev
```

Open <http://127.0.0.1:4260>. Put your API keys in `.env`. They stay on the server and are never
committed.

Run the checks with:

```sh
npm run verify
npm run build
```

## Team

- **Find**: Nick
- **Qualify, Escalate, Collect**: Smaran
- **Evidence**: Fra (Francesco)
- **File**: Tarang
