# File

The filing desk for Claim OS. `taxfile` accepts Nick's FindCandidate v1 JSON or its Naïve board-card JSON block, preserves the stable case ID, and prepares an unsigned draft of the current official Florida DR-486.

## Run

```sh
python3 -m pip install ./file
taxfile prepare case-handoff.json --out "$HOME/file-data/cases"
taxfile status
```

The output contains a filled petition draft, source-form revision and checksum, a review page, attachment hashes, and a manifest. The clerk-only fields and signatures remain blank. The form's instruction page is not included in the petition draft.

Preparation never submits a petition. Missing qualification, case-matched authorization, evidence, verified county instructions, fee or deadline produces a blocked manifest. Closed Find cases remain blocked even when Find used `--include-closed`. Compensated representation requires the appropriate reviewed signature/authorization route.

## Evidence → File

The candidate stays intact under `candidate`. Additional `qualification`, `authorization`, `evidence`, and `filing` objects supply the upstream decisions and documents. [Handoff contract](docs/HANDOFF.md) defines these fields. Evidence's final native handoff is still being developed; its adapter must be checked against an actual emitted packet before live filing.

## Receipts and deadlines

```sh
taxfile record-receipt manifest.json clerk-receipt.pdf --confirmation ACTUAL_CONFIRMATION --parcel ACTUAL_PARCEL
```

A subsequent notice can be attached with `taxfile record-notice manifest.json notice.pdf --response-due YYYY-MM-DD`. Save receipt and notice files inside the case directory.

The receipt must contain both identifiers. File saves its bytes and hash and avoids duplicate entries. A response deadline stays unknown until a notice is supplied; optional `--notice notice.pdf --response-due YYYY-MM-DD` requires the date to appear in that notice. A recorded receipt still requires clerk acceptance and fee verification before downstream work treats filing as complete.

Hendry supports mail, email and fax according to its clerk's instructions. Lee supports online, mail and in-person filing. Transmission and payment require a verified county route and the authorized operator's final approval. No transmission adapter is enabled automatically.

## Official sources

- [Current Florida VAB forms](https://floridarevenue.com/property/Pages/Forms.aspx)
- [DR-486](https://floridarevenue.com/property/Documents/dr486.pdf)
- [Lee filing instructions](https://www.leeclerk.org/departments/value-adjustment-board-vab/filing-a-petition)
- [Hendry filing instructions](https://www.hendryclerk.org/clerk-services/value-adjustment-board/)

```sh
python3 -m unittest discover -s file/tests -v
```

## Sample verification

```sh
PYTHONPATH=file python3 -m unittest discover -s file/tests -v
PYTHONPATH=file python3 file/tests/exercise_sample.py --out /tmp/file-verification-unique-run
```

Use a new output directory for every run. The exercise generates explicitly synthetic evidence, authorization, receipt and notice PDFs, fills the official DR-486, validates its fields, checks blocked cases, and tests receipt replay and deadline custody. Its report is verification only: no real signature, filing, payment, homeowner contact or recovery. `--template /path/to/dr486.pdf` uses an already downloaded official form.

Receipt and notice inputs are validated before case state is changed. Notices supplied with receipts require an explicit response date. A later notice updates the case's current receipt view; receipt ledger entries preserve their original capture history. Missing mailing addresses and non-finite fees require review.
