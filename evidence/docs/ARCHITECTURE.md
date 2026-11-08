# Evidence in the Claim OS workflow

## The workflow as deployed on Naïve

Claim OS runs as agents in the Naïve org "Claim OS". All of them share one board, `brd_3kb4zft8yttkhm04sv6vn8ydw2`.
Every case is a card. The coordinator (`agt_65gzd8vt6s6rcjcxpj11x8x4jv`) hands a card to a step by assigning it to the
agent whose name is exactly that step's name. Assigning starts a paid session for that agent.

```
find ──cards──▶ qualify ──QUALIFIED, released──▶ signup ──done──▶ evidence ──done──▶ file ──▶ chase ▶ escalate ▶ collect
                                                    │                 ▲   │
                                                    └─ Sign up card ──┘   └─ blocked: waits for a person (review, signature)
                                                       (a person assigns)
```

| Step | Agent | Owner | State |
|---|---|---|---|
| find | `agt_xy70yv97k94f0zwt0h552gj486`, scheduled every 6 hours for Bay | Nick | deployed, observed |
| qualify | `agt_6ywz65vd5mp3emm3nh3xqcv26v`, replay mode | Smaran | deployed, observed |
| signup | `agt_69tr31n7bdmpqxdfcyakssds08`, inbox claimos@agentmail.to | team | deployed, observed |
| evidence | `agt_2rn8zx8963y3r54z8gx5mh0bk9`, named `evidence`, this package | Fra | deployed, version 6 (bundle `fil_ehvt07rwhfez151ptdk71h0t3v`, commit 57615af), observed |
| file | `agt_s813nxfpebzvvkbdnfz9zn5kdj`, Lee and Hendry adapters | Tarang | deployed, observed |

The coordinator moves a card forward only when the current step marks it `done` with a result note. It never creates
or deletes cards. A new agent named `evidence` joins the roster automatically, so deploying it starts the hand-offs.

## How Evidence works on a card

1. A card arrives in one of two shapes: a qualified case (Find's JSON block plus Qualify's `QUALIFIED` handoff), or a
   `Sign up · <address>` card from an owner who wrote in. Sign up cards are resolved from the address to exactly one
   parcel on the county roll, or stopped with `EVIDENCE NEEDS ADDRESS`.
2. Intake checks the case, year, parcel, county, Qualify's decision and any authorization. Preparing evidence from
   public records needs no authorization; filing does. A free check from a Sign up card is allowed without Qualify.
3. Collection loads the county roll (NAL) and sales file (SDF) from the Florida Department of Revenue, with the same
   cache Find uses, and checkpoints what it collected. A download failure is a retryable processing failure, never a
   finding on the merits.
4. Analysis selects qualified sales before January 1, ranked by similarity and never by price, and records why each
   nearby sale was excluded. It adjusts them for time (the county-wide monthly index, printed in the packet), land,
   special features and living area, each with its formula and support, and reconciles at the median, with a weighted
   mean as a cross-check. Market value is converted to just value once, either at the county's DR-493 cost-of-sale rate
   or at the county's measured ratio; the request uses the higher of the two, rounded to $100. The comparables' own
   assessment ratio and the assessments of similar homes are cross-checks and never raise or lower the request. If half
   or more of the sales are more than three years older than the subject (an internal screen), or the subject's own
   sale contradicts the result, no value is requested. Later sales are moved back to January 1 and compared.
5. The report generator builds one document model and renders it to PDF, HTML and Markdown, following
   `docs/TEMPLATE_SPEC.md`. Exhibit letters and index page ranges are resolved by rendering, reading back where each
   exhibit landed, and rendering again until they agree.
6. Validation recomputes the arithmetic, checks every exhibit is on the page the index gives, scans the text for
   appraisal language, outcome promises, placeholders, internal identifiers and contact data, confirms redactions
   are gone from the text layer, and checks page size, numbering, bookmarks and file size.
7. Delivery planning lists the petition (File's), the exchange copy for the property appraiser, hearing copies, a
   remote-hearing upload and the filing for an absent petitioner, each with its due date and status `not_sent`.
8. The File handoff writes `evidence.json` with one entry for each of Find's verification strings.
9. The card is written `blocked` with a fixed note until a reviewer approves the exact packet and the owner's
   authorization is valid. Only then does the note say `EVIDENCE COMPLETE` and the status become `done`.

## Readiness is several questions, kept apart

| Stage | Values |
|---|---|
| collection | complete, blocked, failed |
| analytical_sufficiency | supports_reduction, insufficient_evidence, does_not_support, contradicted |
| evidence_completeness | complete, incomplete |
| generation | generated, not_generated |
| format_validation | validated_against_configured_requirements, failed, not_run |
| human_review | not_reviewed, reviewed, rejected, stale |
| approval | approved_for_the_specified_submission (with the list of deliveries), not_approved |
| authorization | valid_for_filing, not_signed, test_only, invalid |
| delivery | per item: not_sent, not_filed, sent, acknowledged, blocked_synthetic |

An approval names the packet's SHA-256. Any change to the evidence produces a new fingerprint, a new version and a new
hash, which makes the earlier review stale. Rescheduling a hearing recomputes deadlines without changing the packet.

## Proceedings are configured separately

| Proceeding | Receiving authority | What Evidence produces |
|---|---|---|
| Informal conference with the property appraiser | `<County> County Property Appraiser` | an evidence summary; it never extends the petition deadline |
| VAB petition, special magistrate hearing | `<County> County Value Adjustment Board` | the petitioner's evidence packet; the DR-486 petition is File's |
| Circuit court (s. 194.171) | none | nothing; legal review only. No captions or pleadings are generated |

## Jurisdictions are a separate layer

```
claimevidence/
  jurisdictions/__init__.py      registry: state -> configuration; anything but FL is unsupported
  jurisdictions/florida/rules.py versioned rules (effective_from / effective_to), sources, deadlines
  jurisdictions/florida/forums.py county adapters: authorities, clerk, timezone, delivery, upload limits, DR-493
  comps.py valuation.py          shared calculations and audit records
  report.py render.py html.py    shared document assembly
  validate.py                    shared presentation and substance checks
```

County adapters (Bay, Hendry, Lee) carry the clerk, the property appraiser, the timezone, delivery details and the local
procedures status. An unknown Florida county gets `local_procedures: unknown` and no county-specific assumptions. A
state other than Florida returns `unsupported` with no rules, deadlines or packet; a future state is added as its own
researched and tested module and inherits nothing from Florida.

## What is locally tested and what is observed in production

| Behaviour | Status |
|---|---|
| Analysis, report, validation, delivery plan, File handoff, card note | locally tested: 75 tests, including deliberate fault injection |
| Rendered packets for two real Bay parcels (Weekend Dr supports a value; Redfish Cir does not) | locally generated and inspected page by page; see `docs/CALCULATION_AUDIT.md` |
| Deployed `evidence` agent on Naïve | version 6 observed in test session `ses_b76z36n3990x2b7vzkmhjrd2ab`: installed 0.3.0, ran Weekend Dr in replay as a test fixture, $476,100 requested against $571,444, 14 pages, validated, card note `EVIDENCE TEST FIXTURE (replay)`, no board reads or writes, 40 active seconds |
| File consuming `evidence.json` end to end | contract matched to File's code; not run, because File supports Lee and Hendry only |
