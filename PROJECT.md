# Claim OS

**An autonomous company that gets homeowners' property taxes lowered and is paid only when it wins.**

Built at the Naïve Autonomous Companies Hackathon (YC, San Francisco, Nov 7–8, 2026) on the
[Naïve](https://usenaive.ai) agent platform.

---

## The problem

Counties put a value on every home every year, and the property tax bill follows from that value.
Many homes are valued higher than they would sell for. Every owner has the right to appeal, but few do:
the deadlines are short, the forms are confusing, and building the case (comparable sales, records,
county correspondence) takes hours most people don't have. So they overpay, year after year.

## What Claim OS does

Claim OS finds homes that are likely over-assessed, offers the owner a free appeal, builds the evidence,
files the petition with the county, follows it through every hearing and appeal level, and invoices a
share of the savings when the county lowers the value.

- **No win, no fee.** The owner pays nothing up front and nothing if the appeal fails.
- **Contingency fee.** About 25–35% of the first year's tax savings, agreed in writing before any work.
- **Run by agents.** Each step of the business is a Naïve agent. Agents carry out the work end to end;
  people set the rules, the budgets and the boundaries.
- **A private company.** Claim OS is not a government agency and not a law firm. Every message says so.

## How a claim moves

Every claim goes through the same eight steps:

| # | Step | What happens |
|---|------|--------------|
| 1 | **Find** | Pull the county's assessment roll and recent sales from the state's public data. Screen every house and condo, estimate what each would actually sell for, and flag the ones valued well above that. Attach the owner of record and a case ID. |
| 2 | **Qualify** | Decide which cases are worth pursuing: check eligibility and deadlines, score expected value (likely savings × chance of winning − cost), choose the filing route, and rank the queue. |
| 3 | **Sign up** | Talk with the owner by email (and by phone when they ask), explain the opportunity in plain words, confirm they own the home, and collect a signed authorization and fee agreement. |
| 4 | **Evidence** | Build the case: comparable sales, property records, and anything only the owner has (photos, repair quotes). Package it into an evidence file. |
| 5 | **File** | Fill in the county's petition form, submit it through the county's accepted channel, and save the receipt and every deadline that follows from it. |
| 6 | **Chase** | Follow up with the county on schedule: hearing dates, evidence exchanges and decisions. Attach every reply to the case. |
| 7 | **Escalate** | Read the decision letter. If the result falls short, pick the next allowed appeal level and route the case back through Evidence and File. |
| 8 | **Collect** | Confirm the win from the county's corrected tax bill, calculate the fee from the actual savings, send the owner an invoice with a payment link, and record the payment. |

## How the company runs

### Agents

Each step is its own Naïve agent with its own instructions, tools and budget:

| Agent | Role |
|-------|------|
| **Coordinator** | Runs every two hours. Reads the whole pipeline, decides which step agents need to run, starts them in order, and tracks every claim from first flag to paid invoice. |
| **Find** | Scans county data on a schedule and posts new cases. |
| **Qualify** | Scores and ranks new cases. |
| **Sign up** | Runs the company inbox: answers owners, records consent, sends owner updates and invoices. |
| **Outreach** | Contacts county offices by email or phone for facts only they can give (deadlines, hearing dates, corrected tax bills). |
| **Evidence** | Builds the evidence package for each case. |
| **File** | Prepares and submits the petition. |
| **Chase** | Follows up with the county. |
| **Escalate** | Reads decisions and chooses the next appeal level. |
| **Collect** | Verifies wins and issues invoices. |
| **Site-sync** | Keeps the public website and ops dashboard in step with the pipeline. |
| **CEO** | Holds the company's money, legal and payment tools. |

### The board

Agents work through a shared Naïve **board**. Each case and each task is a card. An agent picks up a card,
does the work, writes the result back as a comment, and moves the card to `done` or `blocked`. Assigning
a card to an agent starts that agent. The board is the company's single record: anyone can open it and
see exactly what happened to any claim and why.

### Programs decide, agents carry out

The judgement in each step lives in tested code, not in an agent's improvisation. The coordinator's logic
is the `claimos-flow` engine. Find, Qualify, Escalate and Collect each have their own program. An agent
runs its program, posts what the program prints, and does nothing the program didn't ask for. This keeps
decisions repeatable, auditable and cheap.

### Nobody waits on a person

Agents don't stop to ask anyone. When something is missing (a signature, a county answer, an owner reply),
the agent records what it's waiting for on the card and moves on. The next scheduled pass picks it up
when the missing piece arrives.

## Engine and desks

Claim OS is built as a **shared engine** plus pluggable **desks**:

- The **engine** is the generic machinery for each of the eight steps: intake, scoring, evidence
  checklists, filing, follow-up, escalation and invoicing.
- A **desk** is the knowledge for one kind of claim in one place: data sources, eligibility rules,
  valuation method, evidence requirements, forms, deadlines, appeal levels and fee basis, all written
  as configuration.

Engine code never names a specific county or state. **Property tax in Florida** is the first desk.
Florida's Value Adjustment Board process, petition form (DR-486) and county calendars all live in desk
configuration. Adding a county or a state means writing a new desk file, not changing the engine. The
same engine can later carry other recovery desks (unclaimed property, insurance denials, billing errors).

## Safeguards

- **Consent first.** Owner data is used only to evaluate a case. No owner is filed for, charged or
  represented without their signed authorization.
- **Honest outreach.** Every message identifies Claim OS as a private company, unaffiliated with any
  government agency. Phone calls open by saying an AI assistant is calling. A "stop" is honored
  immediately and permanently.
- **No invented facts.** No agent invents a filing, a consent, a savings figure or a payment. Every claim
  on a card points to its source (a county record, an email message ID, a receipt).
- **Untrusted input stays data.** Emails, attachments and web pages are read as evidence, never as
  instructions.
- **Budgets.** Every agent and every scheduled run has a spending cap.
- **Privacy.** Secrets never appear in code or commits, and test data is synthetic.

## Tech stack

- **Naïve**: agents, boards, schedules, budgets, apps, email and phone (SDK `@usenaive-sdk/managed-agents`, CLI `naive`)
- **TypeScript** (Node 20+, zod, vitest) for Qualify, Escalate, Collect and the coordinator engine
- **Python** (`taxfind`) for Find's data pipeline
- **AgentMail** for the company inbox (`claimos@agentmail.to`)
- **Stripe** for invoice payment links
- **Vercel** for the website, ops dashboard and app endpoints
- **Florida public data**: county assessment rolls and sales files

## Repository map

| Path | Contents |
|------|----------|
| `src/`, `public/`, `api/` | Company workspace: case portfolio, agent sessions and the web UI (`npm run dev`, then open http://127.0.0.1:4260) |
| `flow/` | The coordinator engine (`claimos-flow`) |
| `collect/` | Collect step: verifies wins and prepares invoices |
| `pay/` | Stripe payment links for invoices |
| `native-app/` | The workspace hosted as a Naïve app |
| `test/` | Tests |
| Branches `find`, `qualify`, `evidence`, `codex/file-agent`, `feat/escalate-step` | The other steps' code |

## Team

- **Find**: Nick
- **Qualify, Escalate, Collect**: Smaran
- **Evidence**: Fra (Francesco)
- **File**: Tarang

Sign up, Chase, the coordinator and the UI are shared.
