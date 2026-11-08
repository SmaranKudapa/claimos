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
| evidence | named `evidence`, this package | Fra | built and tested locally; deployed once `naive/setup.sh` is run |
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
4. Analysis selects qualified sales before January 1, adjusts them for time, land, special features and living area,
   reconciles at the median, and converts to just value with the county's DR-493 cost-of-sale percentage. The county's
   measured level and the assessments of similar homes are shown as cross-checks. The requested value is the highest
   indication, rounded to $100. The property's own sale and later sales are disclosed.
5. The report generator builds one document model and renders it to PDF, HTML and Markdown. Exhibit numbers and
   index page numbers are resolved by rendering, reading back where each exhibit landed, and rendering again.
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

County adapters (Bay, Hendry, Lee) carry the clerk, the property appraiser and the local procedures status. An
unknown county gets `local_procedures: unknown` and no county-specific assumptions.

## What is locally tested and what is observed in production

| Behaviour | Status |
|---|---|
| Analysis, report, validation, delivery plan, File handoff, card note | locally tested: 57 tests, including deliberate fault injection |
| Rendered packet for a real Bay parcel | locally generated and inspected page by page |
| Deployed `evidence` agent on Naïve | not observed until setup is run and a session is checked |
| File consuming `evidence.json` end to end | contract matched to File's code; not run, because File supports Lee and Hendry only |
