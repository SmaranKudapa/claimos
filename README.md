# Claim OS

An autonomous recovery company powered by Naïve managed agents, Monid tool execution and AgentMail correspondence.

## Company capabilities

- Eight Naïve specialists: Find, Qualify, Sign up, Evidence, File, Chase, Escalate and Collect.
- Durable sessions with version-pinned agents, structured handoffs, per-session budgets and provider event receipts.
- Monid discovery, schema inspection, approved execution, asynchronous run tracking and cost evidence.
- AgentMail claim inbox, owner-scoped drafts, approved delivery, message IDs and case-thread replies.
- A persistent case portfolio, evidence documents, approval queue and coordinator that advances ready work.
- Explicit holds for missing authority, filing adapters, outcome proof and payment receipts.

## Run

Node 24 or newer is required.

```sh
npm ci
cp .env.example .env
npm run dev
```

Open http://127.0.0.1:4260. Configure `NAIVE_API_KEY`, `MONID_API_KEY` and `AGENTMAIL_API_KEY` in the local `.env`. Keys stay server-side. The workspace reads provider configuration from the file without exposing secrets to the browser.

`NAIVE_MODEL` defaults to `vetta/auto`. Each session has a $0.25 native Naïve cap; a case has a $2 session allowance. Monid execution currently admits inspected flat-priced calls up to $0.25. Metered tools need a reviewed spending policy.

## Operating flow

Activate the company to create the managed agents and AgentMail inbox. Add a sourced property case, then run its agent. The coordinator polls real Naïve sessions and follows ready handoffs. Monid requests and email drafts wait for exact-input approval. Source text and inbound messages are treated as evidence, never as instructions.

No filing or payment adapter is enabled by default. An agent-produced draft is not a submitted appeal, signed authorization or collected fee. Verified revenue remains zero until supported by a payment-provider receipt.

State lives in `.claimos/company.sqlite`, excluded from Git. `CLAIMOS_OPERATOR_TOKEN` can protect the local API. The server accepts loopback requests and same-origin writes.

## Hosted workspace

The Vercel workspace uses a same-origin API gateway. `CLAIMOS_API_ORIGIN` selects an HTTPS backend with durable case storage; `CLAIMOS_OPERATOR_TOKEN` is required for hosted access. The gateway forwards approved operator requests and provider receipts. It never treats serverless temporary disk as a persistent case database. Provider keys belong on the execution backend, never in browser code.

## Team interfaces

`src/domain.ts` defines the case, stage handoff, tool request, correspondence and provider receipt contracts. Specialist implementations use the shared case ID and preserve source URLs. `src/naive.ts` defines the managed-agent execution policy. `src/providers.ts` supplies Monid and AgentMail adapters. `src/company.ts` coordinates sessions, costs and approval state.

## Verification

```sh
npm run verify
npm run build
npm run check:provenance
```

## Provider references

- https://usenaive.ai/docs/sdk/agents
- https://usenaive.ai/docs/sdk/sessions
- https://monid.ai/docs/guide/quickstart-api
- https://docs.agentmail.to/quickstart
