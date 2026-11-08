# qualify: the Qualify step

Step 2 of the claims engine (Find → **Qualify** → Sign up → Evidence → File → Chase → Escalate → Collect), for the **property-tax desk**. It takes the candidate properties Find produces and decides, with reasons, which ones are worth pursuing, by which filing route, and in what order. Qualified leads go on to Sign up, and from there to Evidence (`taxappeal-evidence/`). It never contacts anyone and never files anything.

**How it works, end to end: [QUALIFY.md](QUALIFY.md).**

## Setup

A standalone TypeScript package. Requires Node 20+ (the repo root targets Node 24).

```bash
cd qualify
npm install
npm run verify            # typecheck + 61 tests + demo; no network or API key needed
```

For the real LLM review, set `QUALIFY_MODEL` in `qualify/.env` (copy `.env.example`). The API key can sit there as `NAIVE_API_KEY`, or in the repo-root `.env` as `VETTA_API_KEY`, which the rest of the repo already uses. Pick a model with `vetta models list --human`.

## Run

```bash
npm run demo                                                                 # synthetic data + offline reviewer
npm run qualify -- run --candidates <file> --config <desk config> [--suppression <file>] [--llm naive|mock|off]
npm run qualify -- show --results out/results.json --case <caseId>
npm run qualify -- review --results out/results.json --case <caseId> --by <name> --approve
npm run qualify -- cases --results out/results.json --config <desk config> --export out/cases.json   # for the UI
npm run qualify -- codes
```

Other steps import it from `qualify/src/index.ts`: `qualifyAll()` for decisions, `toCaseRecord()` / `toQualifyBeat()` for the Claim OS dossier UI.

## Qualifying a Find run

`find/` (Nick's Find agent) posts one compact card per home to the `qualify` agent's board and publishes the full records as `candidates.jsonl` (Find handoff contract v2, see `find/docs/QUALIFY_HANDOFF.md`). `src/adapters/find-v2.ts` translates those records into Qualify candidates, one desk config per county: the desk template plus that county's filing window from Find.

```bash
npm run qualify -- find-run --find <candidates.jsonl> --template config/desk.florida.json [--case-ids <file>] [--replay] [--llm off|mock|naive] [--out-dir out/find-run]
```

- `config/desk.florida.json`: Florida desk template (Jan 1 valuation, VAB petition DR-486, cost-of-sale assessment level). Fee, work days and thresholds are team assumptions.
- `--replay`: judges each county as of a date inside its own filing window. The 2026 windows have closed, so this is the demo mode.
- Output: `out/find-run/handoff.json` (one entry per case, keyed by Find's `case_id`) and `results.json`.

## The Naïve agents

- `naive/qualify.system.md`: instructions for the `qualify` agent. Each run it downloads the bundled program (`npm run bundle:agent`, uploaded as `qualify-agent.tar.gz`), reads its board, pulls Find's full records, runs `find-run --replay`, and marks each card with its decision. Inside the agent the AI check is off, because Naïve does not expose API keys to agent computers.
- `naive/coordinator.system.md`: the `coordinator` agent. It discovers step agents by name and moves only `QUALIFIED` cards on to Sign-up.

## Before real use

`config/desk.placeholder.json` and everything in `data/` are made up. Write a desk config with your jurisdiction's real valuation date, filing routes, fees and comp rules, and feed it real candidates from Find.
