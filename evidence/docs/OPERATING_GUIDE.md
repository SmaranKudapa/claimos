# Operating Evidence

For Fra, who owns the Evidence step.

## Deploy or update the agent

From the repository root on a machine with the Naïve CLI signed in to the Claim OS org:

```bash
VETTA_PROFILE=team ./evidence/naive/setup.sh
```

It bundles Find's and Evidence's code, uploads it, pushes the `claimos-evidence` skill and applies the agent named
`evidence` (override with `EVIDENCE_AGENT_NAME`). The last line shows the agent id, its version, whether it points at the
new bundle and its enabled tools, which must include `board_read` and `board_write`. The budget is $20 a month and $1
per card. Once the agent exists the coordinator starts assigning it cards.

## What arrives and what you see

Each assigned card ends with a note that starts with one status word:

| Note starts with | Card status | What it means | What you do |
|---|---|---|---|
| `EVIDENCE READY FOR REVIEW` | blocked | packet generated and validated; nobody has reviewed it | review it (below) |
| `EVIDENCE APPROVED, AWAITING SIGNATURE` | blocked | you approved it; the owner has not signed the DR-486POA | Sign up sends the agreement; when signed, assign the card back to `evidence` |
| `EVIDENCE COMPLETE` | done | approved packet, valid authorization, File handoff complete | nothing; the coordinator moves it to File |
| `EVIDENCE INSUFFICIENT EVIDENCE`, `DOES NOT SUPPORT`, `CONTRADICTED` | blocked | the sales do not support a reduction | send back to Qualify or close |
| `EVIDENCE NEEDS ADDRESS` | blocked | a Sign up address matched no parcel or several | confirm the address with the owner through Sign up |
| `EVIDENCE BLOCKED` | blocked | intake stopped it; the note says why | fix the named input |
| `EVIDENCE VALIDATION FAILED` | blocked | the packet failed an automated check | read `internal_review.md`, section "Packet validation" |
| `EVIDENCE RETRY` | blocked | a county file could not be downloaded | assign the card back to `evidence` later |
| `EVIDENCE TEST FIXTURE` | blocked | synthetic test case | nothing; it never moves |

During the demo the agent runs in replay mode (`--as-of 2026-09-01`) and every note says `(replay)`. A replay result
never becomes `EVIDENCE COMPLETE`.

## Reviewing a packet

Open the published `packet.pdf` and `internal_review.md` for the card. Check, at least:

1. The identification page names the right property, parcel, county board and tax year.
2. The comparable sales are genuinely similar homes. Look at the "Why each sale was used" table and the flags.
3. Nothing in the subject facts conflicts with what the owner told us. Owner statements are labelled as unverified.
4. The contrary evidence exhibit: a recent sale of the subject or strong later sales are reasons to stop.
5. `internal_review.md` shows no failed validation check and lists the open items you accept.

To approve, add this line to the card, with the packet's full SHA-256 from the note, then assign the card back to `evidence`:

```
APPROVE EVIDENCE <sha256> FOR file_handoff BY <your name>
```

Use `exchange_property_appraiser` or `remote_vab_upload` instead of, or as well as, `file_handoff` to approve a specific
delivery (separate them with commas). To reject: `REJECT EVIDENCE <sha256> BY <your name>: <reason>`.

An approval covers one exact packet. If anything about the evidence changes, the packet gets a new version and hash and
must be reviewed again. Approval lines are read from card text, so anyone who can write on the board can write one;
keep board access to the team.

## Recording a delivery

Evidence never marks anything sent. When a person has actually sent the exchange copy or uploaded the remote-hearing
PDF, record it in the next input as a `delivery_events` entry with the delivery id, `sent` or `acknowledged`, who, when,
a proof reference (receipt, tracking number, upload confirmation) and the packet SHA-256. It is accepted only for a
packet approved for that delivery.

## Running a case by hand

```bash
export FIND_DATA_DIR=$HOME/find-data
claimevidence resolve-address --address "1120 Redfish Circle, Panama City Beach, FL 32408" --county-code 13 --tax-year 2026
claimevidence build-input --case-id FL-13-2026-30933354000 --county-code 13 --tax-year 2026 --parcel 30933354000 --entry-policy free_check > input.json
claimevidence run --input input.json --out evidence-out --data-dir $FIND_DATA_DIR --summary
claimevidence card-note evidence-out/<cycle>/<run>/result.json
```

Add `--submission submission.json` with `{"petition_number": "...", "contact_phone": "..."}` once the clerk assigns a
petition number, and `--hearing-date YYYY-MM-DD` once the hearing notice arrives. Both change what the deadlines and the
cover page say; neither is ever guessed.

## Changing rules, counties and wording

- A requirement: edit `claimevidence/rules.py`. Each rule carries its source, section, effective date, status, how it is
  applied and which check enforces it. Regenerate the matrix with
  `claimevidence rules --matrix` and paste it under "Matrix" in `docs/REQUIREMENTS_MATRIX.md`.
- A county's cost-of-sale rate: `COST_OF_SALE` in `rules.py`, from that county's DR-493 for the roll year.
- A verified petition deadline: `COUNTY_DEADLINES` in `rules.py`, only from the clerk's own publication.
- A new county: add it to `COUNTY_ADAPTERS` in `claimevidence/forums.py`; its local procedures start as `pending`.
- Packet wording: `claimevidence/report.py`. Keep sentences plain, cite the exhibit beside each claim, and run the tests:
  validation fails on appraisal language, outcome promises, placeholders and internal identifiers.

Run `python -m pytest -q` in `evidence/` after any change.
