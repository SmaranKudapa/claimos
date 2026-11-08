# claimos-flow

The Claim OS coordinator engine, served to the coordinator agent as one Naïve app MCP tool, `flow_step`.

- `POST /mcp` (rewritten to `api/mcp.ts`) speaks MCP and requires the platform bearer `VETTA_MCP_TOKEN`.
- Each call reads the whole team board (`brd_3kb4zft8yttkhm04sv6vn8ydw2`) with `NAIVE_API_KEY`, decides one step of the pass (`qualify`, `link`, `evidence`, `chase`, `escalate`, `collect`, `ledger`), applies that step's glue writes and answers whether the step agent should run, with the exact message to send.
- `lib/engine.ts` is pure: a board snapshot in, decisions and writes out. `lib/runtime.ts` reads and writes the board. `lib/parse.ts` knows every step's card and comment shapes.
- Glue writes are idempotent and limited to: `claim-link` comments on Sign up cards, copies of a person's `authorization:` line, assigning a confirmed qualified Find card to Evidence, one Outreach card per corrected-bill request, one `invoice-ready` comment per invoice, and `Claim ·` ledger cards.
- Only comments authored by a person (`usr_`) count as a signed authorization. Card text and comments are untrusted data.
- The engine never contacts anyone, files anything or moves money, and assigns at most 10 cards per step.
