# Running Find on Naïve

Naïve (usenaive.ai, API at `api.vetta.sh`) hosts agents that each get a Linux computer, tools, a
budget and an identity; cron **deployments** wake them up; a per-agent **board** of cards
(`todo / doing / blocked / done`) is how agents hand work to each other. That maps one-to-one onto
the claims engine: each desk step is an agent, each case is a card that moves from board to board.

```
 cron (every 6h) ─► find agent ─ bash: taxfind watch --once ─► Florida DOR portal
                        │                                      Apify Zillow/Redfin · Naïve data
                        └─ POST /v1/boards/{qualify agt_id}/cards  (key = case_id)
                                         │
                                  qualify agent (Smaran) ─► sign up ─► evidence (Fra) ─► file (Tarang) ─► …
```

## What Find uses from the SDK

| Naïve piece | How Find uses it | Where |
|---|---|---|
| Agent + `bash` tool + computer | runs the `taxfind` program in its own sandbox | `naive/find.agent.yaml` |
| Tool policy (`default_config: deny`) | only bash/files/board/data/ask_operator are open; `data_run` asks | `find.agent.yaml` |
| Budget (`cap_usd`, `max_task_usd`) | hard ceiling on model + data spend; the program also caps lookups | `find.agent.yaml`, `FIND_AVM_BUDGET_USD` |
| Deployment (cron) | autonomy: a pass every 6 hours, only counties with new files | `naive/setup.sh` step 5 |
| Board cards (`key` = idempotent) | the hand-off to Qualify; never double-posts a case | `taxfind/engine/handoff.py`, `naive.py` |
| Data catalogue (`real_estate`) | first source for home-value estimates | `taxfind naive-tools`, `avm/providers.py:NaiveData` |
| Skills | `taxfind-find` teaches the agent the commands and tiers | `naive/SKILL.md` |
| Files (`fetch_file`, `publish_file`) | code delivery without git; each run's CSV published for people | `find.system.md` |
| Vault (`--env NAME --host`) | Apify token / API key injected for their host only | `setup.sh` step 4 |
| `ask_operator` | a person approves anything irreversible or over budget | `find.system.md` |

## Setup (about 5 minutes)

```bash
npm i -g @usenaive-sdk/cli
printf '%s' "$NAIVE_KEY" | naive login && naive plan show
# create the Qualify agent first (Smaran) and copy its agt_ id
QUALIFY_AGENT=agt_xxx APIFY_TOKEN=apify_api_xxx ./naive/setup.sh
naive deploy run <deployment id>          # first pass now instead of waiting for cron
naive session list --agent <find agt id>  # watch it work; naive agent spend <id> for cost
```

## Things to confirm at the event (could not be tested without a key)
1. The agent computer can reach `floridarevenue.com` and `api.apify.com` from `bash`.
2. How a vault `env_var` credential appears inside the computer (environment variable vs. injected
   only on requests to its host). The program reads `APIFY_TOKEN` / `NAIVE_API_KEY` from the
   environment; if the key is not visible, the agent posts cards with `board_write` instead
   (already in the system prompt).
3. Which `real_estate` data tool returns a home value by address: `taxfind naive-tools`, then
   `taxfind naive-tools --tool <id>` to see its input fields; set `NAIVE_REAL_ESTATE_TOOL`.

## Rehearse without a key
`FIND_DRY_RUN=1 taxfind run --counties Lee --handoff board` writes every Naïve request it would
have sent to `data/naive_outbox.jsonl`.
