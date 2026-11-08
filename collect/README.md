# collect: the Collect step

Step 8 of the claims engine (Find → Qualify → Sign up → Evidence → File → Chase → Escalate → **Collect**). When the county lowers a home's value, Escalate creates a `Collect · <address> · <case_id>` card. Collect waits for the county's corrected tax bill, works out the real first-year savings and the agreed fee, issues the invoice (with an exact Stripe payment request), and follows up until it is paid or written off.

**Fully autonomous.** No result waits on a person. Collect never contacts anyone: it writes the owner message and another desk sends it.

## How it decides

| Stage | Does | Ends with |
|---|---|---|
| K0 Intake | The won case (from Escalate's `collect-handoff` line), values from Qualify's handoff, fee % from Sign up's authorization line (30% default, flagged) | `I_SCHEMA`, `I_BILL_MISMATCH` |
| K1 Follow-up | An invoice already exists: paid, reminder due, write-off, or wait | `D_PAID`, `V_REMINDER`, `C_WRITTEN_OFF`, `P_AWAIT_PAYMENT` |
| K2 Proof | Waits for the corrected bill (the customer portal promises "our invoice follows the county's corrected bill"); every number read off the bill must quote it | `P_AWAIT_BILL`, `C_NO_PROOF`, `C_NO_REDUCTION_ON_BILL` |
| K3 Savings and fee | Tax difference on the bill (or value cut × tax rate, flagged); fee = fee % × first-year savings, capped | `C_NO_SAVINGS`, `C_FEE_BELOW_MIN` |
| K4 Invoice | Invoice number, due date, payment request (cents, currency, description, reference) | `V_INVOICE_ISSUED` |

Statuses: WAITING, INVOICED, PAID, CLOSED, INCOMPLETE. The code prefix decides (I_ > D_ > C_ > V_ > P_); `F_` codes are flags.

## Run

```bash
cd collect && npm install
npm run verify                     # typecheck + tests + demo (16 synthetic cases, offline)
npm run collect -- run --cases data/cases.sample.json --config config/collect.placeholder.json --today 2026-12-15
npm run collect -- from-board --card <id> --card-body <file> --qualify-handoff <handoff.json> --config config/collect.florida.json [--bill <file> --bill-reading <file>] [--invoice-state '<json>'] [--payment-link <url>] [--paid-on <date> --payment-ref <id>]
npm run collect -- cases --results out/collect-results.json --export out/cases.json   # "Collect" beats for the site
```

## Board formats

- Handoff (Escalate writes it on the Collect card): `collect-handoff · case <id> · old <value> · won <value> · decided <YYYY-MM-DD> · letter <id> · code <W_…>`
- Corrected bill (comment on the Collect card): `tax-bill · case <id> · received <YYYY-MM-DD> · <document id>` then the bill's full text
- Results: a `collect-result · <STATUS> · <code> · <invoice>` comment carrying `invoice-state: {…}`, and the card note `WAITING · …`, `INVOICED · $… · due …`, `PAID · …` or `CLOSED · …`
- Payment link (the agent): `payment-link · <invoice number> · <url> · <id>`, or `… · unavailable · <reason>`

## Before real use

Everything in `data/` is synthetic. Florida fee bounds, due dates, reminders and wait limits are team assumptions. Payment links need Stripe set up on a Naïve app and the agent's `payments` / `payments_request` tools enabled. Someone (Chase or a person) must post the corrected bill as a `tax-bill` comment.
