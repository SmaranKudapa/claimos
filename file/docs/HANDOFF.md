# Evidence → File → Chase

Preserve `candidate.case_id` from Find. File does not create a replacement ID or treat estimated savings as a result.

| Object | Required information |
|---|---|
| `candidate` | FindCandidate v1/v2, including jurisdiction, parcel, owner, filing window and source |
| `qualification` | Matching `case_id`, `tax_year`, `status: eligible`, `route: vab_value_appeal` |
| `authorization` | Matching `case_id`, `tax_year`, `status: signed`, actual `signer_name`, representation mode and signed artifact |
| `evidence` | Matching `case_id`, `tax_year`, `status: complete`, evidence artifact |
| `filing` | Matching case/year; official `instructions_url`; verified `deadline`, `deadline_source_url`, `deadline_verified`; county method; verified `fee_usd`, `fee_verified`; representative name if applicable |

An artifact is `{ "path": "relative/path.pdf", "sha256": "actual SHA-256" }`, relative to the input handoff's directory. Path traversal, missing files and changed bytes are rejected.

Representation modes are `owner`, `licensed_representative`, `unlicensed_compensated`, and `unlicensed_uncompensated`. For compensated unlicensed representation, `authority_basis` must identify `taxpayer_signed_petition` or `compliant_power_of_attorney`, supported by the actual reviewed document.

File outputs `manifest.json`, `DRAFT-DR-486.pdf`, `petition-data.json` and `review.html`. State is `blocked` or `ready_for_operator_review`; `submitted` stays false. An official receipt can later produce `receipt_recorded` with its confirmation number, parcel, hash and notice-derived deadline. This is receipt custody, not an assertion that the clerk accepted the petition or the required fee cleared.

The Naïve File agent publishes generated artifacts and reports the real returned file IDs. Chase receives the same case ID plus the receipt and notice artifacts. Missing acceptance or deadline is an explicit follow-up task.

The Evidence bridge consumes the published claimos.evidence.result/1 result plus its file-handoff/evidence.json and actual hashed files. No upstream completion, signature or document is inferred from a missing handoff.

## Find schema 2

Preserve the complete candidate unchanged, including its `status: candidate`, `confidence`, `explanation`, `assumptions`, `warnings`, `needs_verification`, `portfolio`, `outreach` and source fields. File accepts versions 1 and 2; unknown versions require review. Portfolio grouping never replaces parcel-level case IDs or creates a joint petition. Find's `outreach.eligible: false` is retained and never interpreted as consent.

For each exact string in `candidate.needs_verification`, supply one `evidence.verifications` entry:

```json
{"check": "Exact original verification requirement", "status": "verified", "artifact": {"path": "record-card-review.pdf", "sha256": "actual SHA-256"}}
```

The parent Evidence object must match the case and tax year and be complete. Every supporting artifact is checked and copied into the packet. Missing, duplicated or unverified resolutions keep the case blocked. Suppressed owners also remain blocked for authorized review.

The manifest preserves `candidate_schema_version` and the full `candidate`; `candidate.json` is the same original object. Its estimates are not recovered revenue. Condo units and property locality are included in the draft address. Bay candidates can be ingested and reviewed, but remain blocked because the currently reviewed filing adapters cover Lee and Hendry only.

A Find run summary, flattened CSV, `handoff.status: delivered`, or retry-file path is not a completed Evidence packet. Supply one actual candidate JSON object (or its board JSON block) within the case-matched handoff. Board cards omit Find's raw comparable arrays; the Evidence desk needs the full candidate data or separately obtained supporting records.

## Qualify → Evidence → File bridge

`taxfile evidence-input --candidate candidate.json --qualify handoff.json --out evidence-input.json` selects exactly one matching `find_case_id`, preserves the original Qualify entry, and translates `QUALIFIED` to Evidence's `decision: qualified`. A changed case, county, year, duplicate decision, non-qualified status or unsupported route is rejected. Historical judgment dates and replay translator notes remain replay markers even if a batch flag is cleared. This command creates no owner authorization or contact consent.

`taxfile evidence-handoff --candidate candidate.json --qualify handoff.json --result result.json --evidence file-handoff/evidence.json --out file-input/case-handoff.json` copies the packet and verified supporting artifacts into an isolated directory, retaining their hashes and the complete original result. Optional `--context filing-context.json` supplies independently obtained authorization and filing details; it never comes from a guessed deadline or a replay assumption.

Native Evidence handoffs require the matching original result. The run must have completed, validation must have passed, the packet must support a reduction and be complete, and a recorded reviewer must approve that exact hash for `file_handoff`. Synthetic, replay, missing authorization, stale review, changed packet and unresolved verification states remain holds. Evidence review is separate from approval to submit the petition.
