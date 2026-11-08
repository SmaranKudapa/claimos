---
name: claimos-evidence
description: How to run and read the Claim OS Evidence program (claimevidence) for a Florida property-tax appeal.
---

# claimevidence

## Commands
- `claimevidence resolve-address --address TEXT --county-code CC --tax-year YYYY [--data-dir DIR]` — resolved, ambiguous or unresolved
- `claimevidence build-input --case-id ID --county-code CC --tax-year YYYY --parcel PID [--find-jsonl F] [--entry-policy full|free_check] [--qualification F] [--authorization F] [--prior-review F] [--submission F] [--hearing-date YYYY-MM-DD] [--synthetic]`
- `claimevidence run --input input.json --out DIR [--data-dir DIR] [--as-of YYYY-MM-DD] [--summary]` — exit 0 completed, 1 failed (retryable), 3 busy
- `claimevidence approvals --card card.txt [--sha256 SHA]` — reads `APPROVE EVIDENCE <sha256> FOR <deliveries> BY <name>`
- `claimevidence card-note result.json [--published JSON]` — the board status and note
- `claimevidence step-result result.json` — the coordinator's StepResult JSON
- `claimevidence check-handoff result.json` — what File checks before using a packet (exit 0 only when usable)
- `claimevidence rules [--matrix]` — every requirement applied, with source, status and how it is checked

## Outputs of one run (one folder per input)
- `packet.pdf` the county-facing packet; `packet.html`, `packet.md` the same content
- `internal_review.md` staff only: intake, requirements, estimates, validation
- `result.json` the full structured result; `delivery.json` what goes to whom, when, and its status
- `file-handoff/evidence.json` the `evidence` object for File's case handoff, with the packet and verification artifacts

## Reading a result
- `readiness` keeps the stages apart: collection, analytical_sufficiency, evidence_completeness, generation,
  format_validation, human_review, approval (bound to the packet SHA-256), authorization, delivery
- `validation.checks` every automated check with pass, warn or fail and the rule behind it
- `conclusions.argument_support` supports_reduction | insufficient_evidence | does_not_support | contradicted | not_analyzed
- Generating a packet never marks anything sent, exchanged, filed or accepted
