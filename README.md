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

Activate the company to create the managed agents and AgentMail inbox. Add a sourced property case, then run its agent. The coordinator polls real Naïve sessions and follows ready handoffs. Autonomous public research permits up to 12 free TinyFish fetches from official LEEPA record pages per case. The coordinator validates the destination and current price, sends a fixed public-record request, and requires non-empty extraction results. Other Monid requests and all email drafts wait for exact-input approval. Source text and inbound messages are treated as evidence, never as instructions.

No filing or payment adapter is enabled by default. An agent-produced draft is not a submitted appeal, signed authorization or collected fee. Verified revenue remains zero until supported by a payment-provider receipt.

Configure `DATABASE_URL` to use Neon for shared cases, provider evidence, workspace settings and worker leases. Without it, local state lives in `.claimos/company.sqlite`, excluded from Git. `CLAIMOS_OPERATOR_TOKEN` can protect the local API. The server accepts loopback requests and same-origin writes.

## Hosted workspace

The Vercel workspace runs the same company API against Neon. `DATABASE_URL`, the three provider keys and `CLAIMOS_OPERATOR_TOKEN` belong in the project’s server environment. The API requires authentication before reading private cases or running agents. Worker leases and version checks prevent concurrent requests from replacing newer case evidence.

Run `npm run worker` on a continuously running Node 24 host for coordination independent of browser activity. The local workspace includes this coordinator. Naïve sessions persist in the managed runtime; the worker reads results and dispatches ready handoffs. Vercel request handlers serve the workspace and do not provide a continuous background timer.

`AGENTMAIL_POD_ID` selects a pod when using a pod-scoped AgentMail key. The company creates its inbox through that pod’s official SDK endpoint.

Monid phone-call endpoints have been inspected. Calls remain unconfigured. A dedicated line, recipient consent, reviewed call instructions and a metered spending policy are required before telephony activation.

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
