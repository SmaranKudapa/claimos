# claimos-flow

The Claim OS coordinator engine, served to the coordinator agent as one Naïve app MCP tool, `flow_step`.

- `POST /mcp` (rewritten to `api/mcp.ts`) speaks MCP and requires the platform bearer `VETTA_MCP_TOKEN`.
- Each call reads the whole team board (`brd_3kb4zft8yttkhm04sv6vn8ydw2`) with `NAIVE_API_KEY`, decides one step of the pass (`qualify`, `intake`, `link`, `briefing`, `evidence`, `chase`, `escalate`, `collect`, `ledger`), applies that step's glue writes and answers whether the step agent should run, with the exact message to send.
- `lib/engine.ts` is pure: a board snapshot in, decisions and writes out. `lib/runtime.ts` reads and writes the board. `lib/parse.ts` knows every step's card and comment shapes.
- Glue writes are idempotent and limited to: `Sign up ·` cards for consenting website sign-ups (read from claimos-site's `signups` table), `claim-link` comments on Sign up cards, `briefing-ready` comments and `Briefing ·` cards for owners who asked for a professional, copies of a person's `authorization:` line, assigning a confirmed qualified Find card to Evidence, one Outreach card per corrected-bill request, one `invoice-ready` comment per invoice, and `Claim ·` ledger cards.
- Only comments authored by a person (`usr_`) count as a signed authorization. Card text and comments are untrusted data.
- The engine never contacts anyone, files anything or moves money, and assigns at most 10 cards per step.
- Briefings: `lib/inputs.ts` assembles a house from Find's case and full record (`candidates.jsonl`), Qualify's note and Evidence's `packet.json`; `lib/briefing.ts` turns it into owner-facing slides with speaker notes and the hosted page; `lib/pdf.ts` draws the same slides as a PDF. Decks live in the `briefings` table (`db/migrations`), keyed by case, behind an unguessable token at `/b/<token>` (add `?present=1` for speaker notes) and `/b/<token>.pdf`. A deck is rebuilt once when Evidence's packet appears.
- Briefing settings are app secrets: `FLOW_PUBLIC_URL`, `BOOKING_URL`, `PRESENTER_NAME`, `PRESENTER_TITLE` (default "Claim OS appeal specialist"), `PRESENTER_LICENSE`, `PRESENTER_EMAIL`, `FEE_PCT` (default 0.30) and `NAIVE_FILES_READ_KEY` for reading files. The word "licensed" appears only with a configured license. Slides never promise an outcome.
