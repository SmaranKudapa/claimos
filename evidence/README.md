# Claim OS Evidence

Evidence turns one Florida property-tax case into a sourced evidence packet a person can review, validate and approve
for a specific use. It runs as the Naïve agent `evidence` on the shared board. Everything it states comes from public
county records and fixed code; nothing is written by a language model, and nothing is sent, exchanged or filed by it.

## What one run produces

| File | Who it is for |
|---|---|
| `packet.pdf` | The receiving authority. Identification page, summary, evidence index with page numbers, subject facts, valuation, comparable sales, witnesses, limitations and numbered exhibits. Letter size, every page numbered, bookmarks per section and exhibit. |
| `packet.html`, `packet.md` | The same content for the portal and the board card. |
| `internal_review.md` | Staff only. Intake checks, requirement status, estimates, deadlines, rules applied and every validation result. |
| `delivery.json` | What goes to whom, by when and how, with a status that only a recorded event with proof can change. |
| `file-handoff/evidence.json` | The `evidence` object for File's case handoff, with the packet and one entry per Find verification. |
| `result.json` | Everything above as structured data, including the separate readiness stages. |

## Quick start

```bash
cd evidence
pip install -e ../find -e .
export FIND_DATA_DIR=$HOME/find-data
claimevidence build-input --case-id FL-13-2026-30933354000 --county-code 13 --tax-year 2026 --parcel 30933354000 --entry-policy free_check > input.json
claimevidence run --input input.json --out evidence-out --data-dir $FIND_DATA_DIR --summary
python -m pytest -q
```

## Documents

- [Architecture](docs/ARCHITECTURE.md): how Evidence sits in the Naïve workflow, what is deployed and what is not
- [Requirements matrix](docs/REQUIREMENTS_MATRIX.md): every Florida and county requirement, its source, status and check
- [Operating guide](docs/OPERATING_GUIDE.md): running, reviewing, approving and changing Evidence
- [File integration](docs/FILE_INTEGRATION.md): the handoff contract File consumes
- [Open items](docs/OPEN_ITEMS.md): what is unsupported, unverified or needs counsel
