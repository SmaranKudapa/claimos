# Evidence → File → Chase

Preserve `candidate.case_id` from Find. File does not create a replacement ID or treat estimated savings as a result.

| Object | Required information |
|---|---|
| `candidate` | FindCandidate v1, including jurisdiction, parcel, owner, filing window and source |
| `qualification` | Matching `case_id`, `tax_year`, `status: eligible`, `route: vab_value_appeal` |
| `authorization` | Matching `case_id`, `tax_year`, `status: signed`, actual `signer_name`, representation mode and signed artifact |
| `evidence` | Matching `case_id`, `tax_year`, `status: complete`, evidence artifact |
| `filing` | Matching case/year; official `instructions_url`; verified `deadline`, `deadline_source_url`, `deadline_verified`; county method; verified `fee_usd`, `fee_verified`; representative name if applicable |

An artifact is `{ "path": "relative/path.pdf", "sha256": "actual SHA-256" }`, relative to the input handoff's directory. Path traversal, missing files and changed bytes are rejected.

Representation modes are `owner`, `licensed_representative`, `unlicensed_compensated`, and `unlicensed_uncompensated`. For compensated unlicensed representation, `authority_basis` must identify `taxpayer_signed_petition` or `compliant_power_of_attorney`, supported by the actual reviewed document.

File outputs `manifest.json`, `DRAFT-DR-486.pdf`, `petition-data.json` and `review.html`. State is `blocked` or `ready_for_operator_review`; `submitted` stays false. An official receipt can later produce `receipt_recorded` with its confirmation number, parcel, hash and notice-derived deadline. This is receipt custody, not an assertion that the clerk accepted the petition or the required fee cleared.

The Naïve File agent publishes generated artifacts and reports the real returned file IDs. Chase receives the same case ID plus the receipt and notice artifacts. Missing acceptance or deadline is an explicit follow-up task.

The final Evidence adapter awaits an actual native Evidence output. No upstream completion, signature or document may be inferred from a missing handoff.
