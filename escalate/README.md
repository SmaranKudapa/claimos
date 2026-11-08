# escalate: the Escalate step ("Appeal again")

Step 7 of the claims engine (Find → Qualify → Sign up → Evidence → File → Chase → **Escalate** → Collect), for the property-tax desk. After the county answers an appeal, Chase hands Escalate the case and the county's decision letter. Escalate reads the letter and decides, on its own, what happens next: collect the win, appeal at the next level, fix and refile, wait, or close the case with a reason.

**Escalate is fully autonomous.** No result waits on a person. Every case that would normally need a human gets an automatic, conservative resolution defined in config. Escalate never files or sends anything itself; the next agent acts on its result automatically.

**How it works, end to end: [ESCALATE.md](ESCALATE.md).**

## Setup

A standalone TypeScript package. Requires Node 20+.

```bash
cd escalate
npm install
npm run verify            # typecheck + tests + demo; no network or API key needed
```

For the real AI letter reader, set `ESCALATE_MODEL` (and optionally `ESCALATE_ESCALATION_MODEL`) in `escalate/.env` (copy `.env.example`). The API key can sit there as `NAIVE_API_KEY`, or in the repo-root `.env` as `VETTA_API_KEY`.

## Run

```bash
npm run demo                                                          # 17 synthetic letters, offline reader
npm run escalate -- run --cases <file> --decisions <file> --config <config> [--today YYYY-MM-DD] [--llm mock|naive]
npm run escalate -- show --results out/escalate-results.json --case <caseId>
npm run escalate -- cases --results out/escalate-results.json --export out/cases.json   # "Appeal again" beats for the site
npm run escalate -- validate-config --config config/escalate.florida.json
npm run escalate -- codes
```

Configs: `config/escalate.placeholder.json` (made up; what the samples and tests use) and `config/escalate.florida.json` (Florida: Value Adjustment Board petition, then a circuit-court suit that ClaimOS refers out).

Other steps import it from `escalate/src/index.ts`: `escalateAll()` for decisions, `toAppealBeat()` / `toCaseRecordPatch()` for the Claim OS site.

## Before real use

Everything in `data/` is synthetic. The Florida config's cure window for incomplete petitions, fees, work days and economics are team assumptions to confirm. Sign up must collect the owner's authorization scope and escalation preferences (see ESCALATE.md).
