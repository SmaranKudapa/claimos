# Evidence packet template

This page describes the packet Evidence generates for every case. It covers what goes in, in what order, when each
section appears, and what a jurisdiction can change. Where each part lives in the code:

- `claimevidence/report.py` decides the content.
- `render.py` lays out the PDF.
- `html.py` produces the HTML and Markdown copies.
- `validate.py` checks the result.

No packet text is written by hand for a particular case. Every sentence is built from the case record.

## Style defaults

These are Claim OS design choices, not Florida requirements. No Florida statute, rule or form sets fonts, margins or a
PDF standard for VAB evidence (rule CO-FMT-01 in the matrix).

| Element | Default |
|---|---|
| Page | US Letter, 8.5 × 11 in, 1 in margins on every generated page |
| Body | Helvetica 11 pt, 1.15 line spacing, 6 pt after each paragraph, left aligned, no first-line indent, black on white |
| Headings | Sections 14 pt bold and numbered; subsections and exhibit titles 11 pt bold; headings never end a page |
| Tables | 9 pt with thin grey rules and a shaded header row. A comparison grid holds at most three sales and repeats for more. A table of up to 14 rows stays with its heading and introductory sentence. Longer tables repeat their header on each page. |
| Notes | 9 pt |
| Footer | Centered, 9 pt: `Parcel <id> \| <year> \| Page X of Y`. While a release field is missing it is prefixed `DRAFT — NOT FOR SUBMISSION`. |
| Navigation | PDF bookmarks for the cover, each section and each exhibit. The evidence index gives the printed packet pages. |
| Numbers | `$571,444`. Adjustments are signed: `+$1,185`, `-$643`. Ratios are shown as `0.8609` or `84.8%`. Areas are `2,212 sq ft`. |
| Dates | `January 1, 2026` in sentences; `Oct 16, 2026` and `Dec 2025` in tables. An unknown date reads `Date not established`. |
| Branding | None. No logo, color, callout boxes or slogans. |

Helvetica stands in for Arial. Arial would have to be embedded as a licensed font file. Helvetica is a PDF standard
face with the same character widths, so line breaks are identical and nothing is embedded. If a board ever requires
Arial by name, that becomes a county rule (see "Jurisdiction overrides"), and the reason is recorded.

Source exhibits that the owner supplies are shown unaltered. They are scaled to fit the page and never cropped or
stretched. Generated margins do not apply to them.

The defaults are kept in `STYLE_DEFAULTS` in `render.py` and printed in each internal review record under "Template
defaults".

## Document order and when each part appears

Numbers are assigned at generation, so an omitted section never leaves a gap. Each omitted section is listed in the
internal record under "Sections omitted", with the reason.

| Order | Part | Appears when | What it contains |
|---|---|---|---|
| Cover | Identification page | Always | See "Cover page" below. |
| 1 | Statement of the case and requested determination | Always | With a supported value: *Property and issue*, *Principal evidence*, *Supported conclusion*, *Material qualification* and *Requested determination*, aimed at one page. Without one: *Property and issue* and *Result*. Both versions end with a *Related filings* table showing the status of the DR-486 petition and the authorization. |
| 2 | Evidence index | Always | Columns: Exhibit, Document or evidence, Date (the document's own date), Source (with the retrieval date), Packet pages. A missing document is never listed. |
| 3 | Subject property facts and disputed issues | Always | Columns: Characteristic, Official record, Verified contrary information, Source. Below the table, one paragraph per disputed fact. Owner statements are labelled as unverified. |
| 4 | Valuation framework | Always | One bullet per proposition, each with its citation and how it applies to this case. Citations come from rules marked `cite_in_packet`, using the version in force on the hearing date. |
| 5 | Comparable sales analysis | A value is supported | 5.1 Selection: search area, period, property type, sources, criteria, counts and exclusions. 5.2 Property comparison grid. 5.3 Adjustment grid with a sign convention, net, adjusted and gross rows, and a Basis or source column. 5.4 An explanation of each adjustment type that is not zero: Difference, Basis, Calculation (with a worked example), Result, Limitation. |
| 6 | Reconciliation and requested value | A value is supported | Which sales carry more weight and why. The weighted cross-check. The conversion to just value as a separate step. The Step / Input or calculation / Result / Supporting reference table. A breakdown of the gap between the county's value and the request. Sensitivity. |
| 7 | Material limitations and contrary evidence | Always | A five-point table (Item, Why it could matter, Comparability and relevance, Effect on the analysis, Unresolved) for each item that applies: the property's own sale, sales after January 1, the age of the comparable sales, new-construction sales, and the time adjustment. General limitations follow as bullets. |
| - | Condition evidence | The owner supplied condition documents for the county | Each document with its date, the date the condition existed, and a caption. |
| - | Witness evidence | A witness is named | Columns: Witness, Role or firsthand knowledge, Expected factual subjects, Related exhibits. Contact details are given where the exchange rule requires them. Testimony is never written as if confirmed. |
| Exhibits | Supporting exhibits | Always | See below. Lettered from A in order of appearance; they start on a new page. |

## Exhibits

| Exhibit content | Included when | Shows |
|---|---|---|
| Subject property record | Always | The county roll fields used, with field names, the file's publication date, the retrieval date and SHA-256. |
| Comparable-sale transaction records | Always | With a supported value: the sales used, with parcel, deed book and page, qualification code, county value and value-to-price ratio. Without one: the most similar sales found and why none supports a value. |
| Adjustment calculations | A value is supported | Each sale's adjustments, the formula with its inputs, gross adjustment, and the support for each adjustment type. |
| Time index, cost of sale and measured ratio | A value is supported | Each sale's time factor. The county-wide monthly index with sales counts, medians, smoothed values and factors, so every factor can be reproduced. The DR-493 rate with its page. The measured ratio with its basis. |
| Assessments of similar homes | Always | The subject's value per sq ft, the median and middle half for similar homes, and the closest homes by size and then age. |
| Sales considered and not used | Excluded sales exist | The nearest excluded sales and the rule each one failed. |
| Subject sale history | Always | The subject's sales in the current sales file, or a statement that there are none in that file. |
| Sales after January 1 | Similar later sales exist | Each later sale moved back to January 1 and put on the just-value basis, with what it indicates. |
| Owner documents | The owner supplied county-facing documents | The document as supplied, its date, and its SHA-256. |

## Cover page

The court line is `BEFORE THE <AUTHORITY>`, taken from the county adapter. When no value is supported, the authority
name appears alone and the title reads `EVIDENCE REVIEW — NOT FOR SUBMISSION`. The identification table always has these
fields:

| Field | Source | Blocks release when missing |
|---|---|---|
| Petitioner | Signed authorization | Yes |
| Property address, Parcel/folio number | County roll | Never missing; intake stops first |
| Petition number | `submission.petition_number`, from the clerk | Yes. Shown as `Pending (not yet assigned)`, never invented. |
| Assessment year, Valuation date | Appeal | - |
| Submitting party | `submission.submitting_party`: a verified name and role | Yes. Never an invented professional role. |
| Contact telephone | `submission.contact_phone` | Yes |
| Witness contact information | Witness list | Flagged by V-WITNESS |
| Value challenged, Value requested | Roll and valuation | A missing supported value blocks release |
| Report date and version | Generation date, version number and content fingerprint | - |

A 9 pt note under the table says that software prepared the packet, that it was not reviewed when generated, and that
no appraiser, broker or attorney prepared or reviewed it.

## Draft, review and release

- While any release field is missing, a boxed `DRAFT — NOT FOR SUBMISSION` notice names the missing items, the footer
  carries the same marking, and validation reports `V-RELEASE`.
- An approval is a card line naming the packet's SHA-256. The PDF is deterministic: the same content produces the same
  bytes. Any change to the content gives a new version and hash, which makes the earlier approval stale.
- No signatures, certificates of service, filing receipts or declarations are ever generated.
- Before approval, validation checks: identity and year consistency, arithmetic, conversion applied once, adjustment
  support, exhibit references and page ranges, citations from the rule set, language, placeholders, privacy and
  redaction, page size, bookmarks and file size. Presentation checks and substance checks are reported separately, and
  both must pass.

## Jurisdiction overrides

| Layer | File | What it may change |
|---|---|---|
| Registry | `claimevidence/jurisdictions/__init__.py` | Which states are supported. Florida only. Any other state returns `unsupported`, with no rules, no deadlines and no packet. |
| State rules | `jurisdictions/florida/rules.py` | Rules with source, section, effective dates, status and the check that enforces each. The rule in force on the hearing date applies. |
| County adapters | `jurisdictions/florida/forums.py` | Authority names for the court line, clerk, property appraiser, timezone, delivery addresses, upload size limit, whether remote hearings are offered, and the DR-493 cost-of-sale rate. |
| Hearing format | `appeal.hearing_format` | Which delivery obligations apply. Remote hearings add the cover-page and upload checks. |

A county adapter never changes the section order, the writing rules or the style. To override a style default, add a
rule with its official source and wire the check to it; the reason then appears in the matrix and the internal record. A
future state gets its own module, researched and tested separately. It inherits none of Florida's deadlines, valuation
steps, forms or hearing terms.

## Writing rules enforced by validation

- Never use "appraisal", "appraised", "certified" or "licensed" (s. 475.612).
- No outcome promises. Never say something was "filed", "served", "exchanged", "accepted" or "submitted" when
  generation cannot establish it.
- No overstated words: clearly, obviously, undeniably, irrefutably, grossly, dramatically, abundantly.
- No exclamation marks, emoji, chat filler, placeholders, `None`, `NaN` or unresolved exhibit references.
- No email addresses or telephone numbers other than the supplied contact number. Redacted text must be absent from
  the text layer.
- Reasoning runs in the order fact, source, explanation, implication, with the exhibit cited beside the claim.

## Tests that guard the template

From `tests/test_upgrade.py` and `tests/test_report.py`:

- `test_the_text_follows_the_data_and_carries_no_sample_specific_wording`: two different parcels produce different
  text with their own values, and no sample address or figure appears.
- `test_conditional_sections_are_omitted_with_a_recorded_reason`
- `test_presentation_and_substance_are_checked_separately`
- `test_a_no_value_review_is_not_addressed_to_the_board_and_lists_the_sales_it_rejected`
- `test_a_duplicated_conversion_or_an_unsupported_adjustment_fails_validation`
- The report tests for the cover fields, draft marking, index page ranges, bookmarks and footer.
