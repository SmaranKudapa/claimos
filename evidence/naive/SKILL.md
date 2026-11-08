---
name: claimos-evidence
description: How to run and read the Claim OS Evidence program (claimevidence) for a Florida property-tax appeal.
---

# claimevidence

## Commands
- `claimevidence build-input --case-id ID --find-jsonl FILE --county-code CC --tax-year YYYY --parcel PID [--qualification F] [--authorization F] [--consent F]`
- `claimevidence run --input input.json --out DIR [--summary]` — exit 0 completed, 1 failed (retryable), 3 busy
- `claimevidence step-result result.json` — the coordinator's StepResult JSON
- `claimevidence check-handoff result.json` — what File checks before using a packet (exit 0 only when usable)
- `claimevidence rules` — every jurisdiction rule applied, with its source and date checked

## Reading a result
- `conclusions.package_complete` — every required item is present
- `conclusions.argument_support` — supports_reduction | insufficient_evidence | does_not_support | contradicted | not_analyzed
- `conclusions.filing_readiness` — ready_for_human_review or not_ready, with `not_ready_reasons`
- These are three separate questions. A complete packet can still support a weak claim.
- `next_action` — who acts next and why
- `review.stale` — the evidence changed after the last human review
