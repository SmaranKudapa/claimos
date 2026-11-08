# Calculation audit: Weekend Dr and Redfish Cir

This audit re-runs both sample cases with the current code and checks every figure the packets report. Inputs:

- Bay County 2026 final roll (NAL), published Oct 16, 2026, SHA-256 `75c878606ef27bdb…`.
- Bay County sales file (SDF), published Oct 16, 2026, SHA-256 `4e29b0b026f12d84…`.
- Bay's 2026 Form DR-493, PDF p. 8.

Both runs use replay mode, as of Sep 1, 2026. Each figure below can be reproduced from the packet's exhibits. The
arithmetic was rerun independently of the generator.

## Weekend Dr: 8645 Weekend Dr, parcel 32503400208

### Earlier claims, checked

| Claim | Result |
|---|---|
| County just value $571,444 | Confirmed. Assessed and taxable values are the same, with no homestead exemption. |
| Requested just value $476,100 | Confirmed, and now derived step by step (below). |
| Later nearby sales of $545,000 to $605,000 | Partly. Six later sales within 10% of the subject's size range from $505,000 to $605,000. Five of them fall in $545,000 to $605,000. All six are analysed in Section 7 and Exhibit H. |
| "Adjustments are at most 6%" | True for the comparable adjustments alone: gross is 0.3% to 6.0% of price. That figure leaves out the separate conversion from market value to just value, which lowers the value by 13.9%. The packet now shows the two steps apart. |

### The six sales

Every sale is in the subject's neighborhood (177100), has the same 2,212 sq ft of living area, is qualified by the
county (code 01) and was effectively built between 2023 and 2025. The subject was built in 2023.

| Sale | Address | Sold | Price | Time | Features | Net | Adjusted | Gross | Weight |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 9335 Cool Breeze Dr | Dec 2025 | $570,000 | -$643 | +$1,185 | +$542 | $570,542 | 0.3% | 0.300 |
| 2 | 9480 Puffer Fish Pl | Nov 2025 | $603,600 | -$28,542 | +$2,435 | -$26,107 | $577,493 | 5.1% | 0.117 |
| 3 | 8409 Dockside Pl | Jul 2025 | $550,000 | -$4,440 | +$7,856 | +$3,416 | $553,416 | 2.2% | 0.268 |
| 4 | 9464 Puffer Fish Pl | Oct 2025 | $574,900 | -$27,185 | +$4,970 | -$22,215 | $552,685 | 5.6% | 0.107 |
| 5 | 9460 Puffer Fish Pl | Oct 2025 | $524,400 | -$24,797 | +$6,454 | -$18,343 | $506,057 | 6.0% | 0.101 |
| 6 | 9444 Puffer Fish Pl | Oct 2025 | $540,500 | -$25,558 | +$4,951 | -$20,607 | $519,893 | 5.6% | 0.106 |

The land and living-area adjustments are $0 for every sale, because the county's land values and living areas are
identical.

How each adjustment is calculated:

- **Time:** price × (factor - 1). The factor is the January 1 level of the county-wide monthly index ($180.43 per sq ft)
  divided by the sale month's smoothed median. For October 2025: $180.43 / $189.38 = 0.9527. All 21 months of the index
  are printed in Exhibit D.
- **Special features:** (subject's county feature value - sale's) / 0.8609. For Sale 3: ($7,698 - $935) / 0.8609 =
  +$7,856.

### From the sales to the request

| Step | Calculation | Result |
|---|---|---|
| Market indication | Median of six adjusted prices | $553,050 |
| Cross-check | Mean weighted by 1 / gross adjustment | $552,957 |
| Just value at DR-493 cost of sale | $553,050 × (1 - 15%) | $470,092 |
| Just value at the measured ratio | $553,050 × 0.8609 (4,384 qualified sales, Jan to Dec 2025) | $476,121 |
| Request | The higher of the two conversions, rounded to $100 | $476,100 |

Conversion audit:

- Recorded prices carry no cost-of-sale deduction, so the deduction is applied once.
- The DR-493 rate and the measured ratio are alternative conversions. They are never applied together.
- Land and feature adjustments are moved into market terms by dividing by 0.8609, so no deduction is hidden in them.
- Exemptions and caps do not apply. The subject has no homestead exemption, and assessed value equals just value.

### What explains the $95,344 gap

| Part | Amount | Explanation |
|---|---|---|
| County value above the market indication | $18,394 | The county's $571,444 is 103.3% of the indicated market value. Its own measured ratio is 86.1%, and the six sold homes have a median of 83.6%. |
| Conversion from market value to just value | $76,929 | One conversion at the county's own ratio. |
| Rounding | $21 | |

The factors behind the gap, checked one by one:

| Factor | Finding |
|---|---|
| Comparable selection | 625 qualified sales were considered and 387 met the criteria. The six used were ranked by similarity, never by price. The nearest excluded sales were smaller homes that sold for less ($360,000 to $468,071), so the exclusions did not lower the result. |
| Transaction terms | Five of the six were new-construction sales. Builder incentives are not in public records. After adjustment, the five builder sales have a median of $552,685, against $553,416 for the one resale. |
| Physical differences | Only special features differ. Land, size and age are matched. Condition is not in public data and is disclosed as a limitation. |
| Market timing | The county-wide index fell over 2025, so the time adjustments are negative. Without them, the median adjusted price would be $564,520, which converts to about $485,974. That is still below $571,444, so the conclusion does not depend on the index. |
| Statutory adjustment | Applied once, as shown above. |
| Weighting | The median and the weighted mean differ by $93. |
| Possible error | The arithmetic reconciles. The subject is valued at $258.34 per sq ft, while the 512 similar homes have a median of $196.04 and a middle half of $179.40 to $207.18. The data cannot say why. One possibility is a recent purchase of the subject that is not in this sales file, so the internal record now asks a reviewer to check the property appraiser's sale history (MV-10). |

### The later sales

The six sales after January 1 were moved back to January 1 with the same index and put on the just-value basis at
0.8609. That gives $435,369 to $519,316. Every result is below the county's $571,444 and within 10% of the request.

Seen the other way, the county's $571,444 corresponds to a market value of $663,775 at its own ratio. Every later price,
including the highest at $605,000, is below that.

The later sales are evidence consistent with the request, not against it. They remain a check rather than the basis for
the value, as DOR bulletin PTO 08-02 describes.

### Verdict

The $476,100 request holds up on re-examination. It is a smaller reduction than Find's screen estimated ($443,935), so
the case record routes it back to Qualify to reconfirm the economics before File.

Qualifications that stay in the packet:

- Five builder sales.
- The county-wide time index.
- Condition and interior not inspected.
- The subject's earlier sale history not yet checked.

## Redfish Cir: 1120 Redfish Cir, parcel 30933354000

| Item | Result |
|---|---|
| County just value | $1,648,898. Land is $589,619 of it. |
| Subject | 3,581 sq ft, built 1982, effective year 2017. |
| Sales considered and usable | 1,266 considered; 21 met the criteria. 1,208 were excluded on land value and 1,043 on size; a sale can fail more than one rule. |
| Six most similar | Sold $790,000 to $1,425,000, with effective years 2003 to 2014. |
| Age screen | Five of the six are more than 3 years older than the subject by effective year. Age is not adjusted, so a value built on them would be biased low. The 3-year screen is an internal Claim OS threshold. |
| Outcome | `insufficient_evidence`. No value is requested. The packet is titled an evidence review and is marked `DRAFT — NOT FOR SUBMISSION`. |
| Indication withheld | The median adjusted price, $1,196,155, would imply about $1.03 million. It is not used because of the age bias. |
| Later sales | Five, from $700,000 to $1,879,000. Their just-value equivalents are $582,802 to $1,619,918, all below the county value. The highest, 1507 Trout Ln in Feb 2026, is within 2% of it. |

Earlier versions requested a value for Redfish. That request is withdrawn. The case returns for review, and either newer
comparable sales or a supported age adjustment would be needed to go further.

## Reproducing this audit

```bash
claimevidence run --input weekend.json --out evidence-out --data-dir $FIND_DATA_DIR --as-of 2026-09-01 --summary
```

The figures above appear in `result.json` at these keys:

- `valuation.bridge`
- `valuation.conversion`
- `valuation.later_sales`
- `analysis.selected`
- `analysis.reconciliation`
- `analysis.time_index_table`
