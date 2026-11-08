# Florida county coverage matrix

Generated 2026-11-08 from the statewide run (`output/county_summary.csv`, 2026 rolls).
Every number is from that run, except memory: six counties are **measured**, the rest modelled from them.

## Data source — identical for all 67 counties

| | |
|---|---|
| Publisher | Florida Department of Revenue property tax data portal |
| Access | Public HTTPS download, no key, no scraping |
| Files | **NAL** (every parcel: values, exemptions, owner, characteristics) and **SDF** (every recorded sale) |
| Vintage | 2026 roll; stage `preliminary` or `final` per county |
| Valuation date | 1 January of the tax year (statutory) |
| Licence | Florida public records; no reuse restriction found. See `docs/LEGAL.md` for the confidential-owner exemptions that must be suppressed |

## Ingested, screened and validated are three different things

- **Ingested** — NAL and SDF downloaded and parsed. **All 67.**
- **Screened** — the detection rule ran and produced tiers. **All 67.**
- **Validated** — the holdout self-check passed: on sales *after* the valuation date, which the screen never saw, flagged homes sold below the county's value at least 1.25x more often than unflagged ones, over at least 30 such sales. **Only 11.**

Screening a county says nothing about whether its estimates are trustworthy. `weak` counties are held automatically; `untested` counties flow but every payload carries a `needs_verification` entry saying the screen is unproven there.

## Validated — 11 counties

Cards flow.

| County | Code | Stage | Homes | Coverage | Strong | Possible | Savings/yr | Lift | Holdout n | Runtime | Peak MB | Basis | Fits |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Dade | 23 | final | 773,428 | 100% | 23,190 | 5,321 | $38,755,265 | 1.50 | 723 | 124s | 4,505 | modelled | no |
| Palm Beach | 60 | final | 570,445 | 100% | 7,649 | 3,925 | $12,313,471 | 1.66 | 546 | 89s | 3,382 | modelled | no |
| Broward | 16 | final | 643,826 | 100% | 6,402 | 1,526 | $10,235,081 | 1.47 | 381 | 123s | 3,788 | modelled | no |
| Lee | 46 | final | 362,290 | 100% | 2,968 | 1,237 | $4,489,737 | 1.81 | 189 | 81s | 2,200 | measured | no |
| Orange | 58 | final | 399,418 | 100% | 2,787 | 1,238 | $3,778,695 | 1.57 | 164 | 60s | 2,435 | modelled | no |
| Charlotte | 18 | final | 108,514 | 100% | 3,267 | 1,138 | $3,637,071 | 1.43 | 206 | 21s | 976 | measured | no |
| Bay | 13 | final | 86,114 | 99% | 1,495 | 391 | $1,941,421 | 1.83 | 100 | 15s | 636 | measured | yes |
| Volusia | 74 | final | 221,526 | 100% | 1,318 | 746 | $1,370,315 | 1.73 | 117 | 39s | 1,450 | modelled | no |
| Duval | 26 | final | 322,270 | 99% | 868 | 983 | $956,894 | 1.28 | 78 | 48s | 2,008 | modelled | no |
| Martin | 53 | final | 66,288 | 99% | 551 | 472 | $649,655 | 3.38 | 56 | 11s | 518 | measured | yes |
| Pasco | 61 | final | 216,250 | 100% | 477 | 443 | $567,280 | 1.63 | 44 | 34s | 1,441 | measured | no |

## Weak — 17 counties

**Held automatically.** The screen did not beat chance here.

| County | Code | Stage | Homes | Coverage | Strong | Possible | Savings/yr | Lift | Holdout n | Runtime | Peak MB | Basis | Fits |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Sarasota | 68 | final | 222,758 | 100% | 5,248 | 1,253 | $7,627,424 | 0.39 | 335 | 36s | 1,457 | modelled | no |
| Hillsborough | 39 | final | 432,110 | 100% | 5,780 | 2,046 | $6,606,132 | 0.80 | 403 | 64s | 2,616 | modelled | no |
| Pinellas | 62 | final | 356,390 | 100% | 4,591 | 1,598 | $5,784,634 | 0.91 | 392 | 74s | 2,196 | modelled | no |
| Collier | 21 | final | 212,232 | 99% | 2,515 | 209 | $4,889,595 | 1.06 | 114 | 50s | 1,398 | modelled | no |
| Brevard | 15 | final | 248,112 | 99% | 2,154 | 1,209 | $2,450,126 | 1.14 | 148 | 44s | 1,597 | modelled | no |
| Manatee | 51 | final | 170,321 | 100% | 1,509 | 450 | $2,345,510 | 1.00 | 87 | 30s | 1,166 | modelled | no |
| Indian River | 41 | final | 75,146 | 99% | 1,300 | 274 | $2,119,234 | 1.24 | 104 | 14s | 639 | modelled | yes |
| Monroe | 54 | final | 36,714 | 99% | 690 | 21 | $1,817,140 | 0.00 | 35 | 8s | 427 | modelled | yes |
| Sumter | 70 | final | 78,055 | 100% | 1,268 | 414 | $1,527,563 | 0.86 | 84 | 12s | 655 | modelled | yes |
| Saint Lucie | 66 | final | 144,725 | 100% | 1,462 | 350 | $1,495,024 | 0.75 | 95 | 22s | 1,025 | modelled | no |
| Saint Johns | 65 | final | 128,812 | 100% | 1,083 | 175 | $1,452,423 | 0.00 | 107 | 27s | 936 | modelled | yes |
| Escambia | 27 | final | 115,786 | 100% | 960 | 681 | $1,290,946 | 0.84 | 71 | 18s | 864 | modelled | yes |
| Okaloosa | 56 | final | 85,352 | 99% | 773 | 166 | $1,106,953 | 0.98 | 57 | 14s | 696 | modelled | yes |
| Seminole | 69 | final | 149,958 | 100% | 1,006 | 344 | $1,010,688 | 1.11 | 92 | 23s | 1,053 | modelled | no |
| Lake | 45 | final | 139,651 | 100% | 825 | 369 | $906,407 | 0.74 | 43 | 22s | 996 | modelled | no |
| Polk | 63 | final | 245,190 | 100% | 1,096 | 945 | $890,625 | 0.54 | 85 | 40s | 1,581 | modelled | no |
| Flagler | 28 | preliminary | 59,092 | 100% | 798 | 189 | $817,542 | 0.00 | 50 | 11s | 550 | modelled | yes |

## Untested — 39 counties

Too few post-valuation sales to judge. Cards flow, marked unproven.

| County | Code | Stage | Homes | Coverage | Strong | Possible | Savings/yr | Lift | Holdout n | Runtime | Peak MB | Basis | Fits |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Walton | 76 | final | 51,689 | 99% | 863 | 80 | $2,377,537 | 1.29 | 27 | 12s | 509 | modelled | yes |
| Santa Rosa | 67 | final | 70,466 | 98% | 349 | 126 | $484,172 | 4.99 | 18 | 10s | 613 | modelled | yes |
| Nassau | 55 | final | 37,227 | 100% | 231 | 50 | $452,853 | 1.00 | 18 | 8s | 429 | modelled | yes |
| Citrus | 19 | final | 64,441 | 100% | 365 | 262 | $405,236 | 0.91 | 28 | 13s | 580 | modelled | yes |
| Marion | 52 | final | 145,455 | 100% | 408 | 339 | $362,320 | 1.43 | 26 | 31s | 1,029 | modelled | no |
| Hernando | 37 | final | 73,806 | 100% | 387 | 119 | $351,151 | 1.73 | 23 | 16s | 632 | modelled | yes |
| Clay | 20 | final | 72,441 | 100% | 282 | 153 | $252,118 | 3.52 | 15 | 14s | 624 | modelled | yes |
| Alachua | 11 | final | 72,770 | 100% | 143 | 93 | $152,384 | 1.69 | 17 | 15s | 626 | modelled | yes |
| Osceola | 59 | final | 154,904 | 100% | 154 | 87 | $150,407 | 2.36 | 9 | 21s | 1,081 | modelled | no |
| Highlands | 38 | final | 37,293 | 100% | 142 | 90 | $117,899 | 1.18 | 13 | 9s | 430 | modelled | yes |
| Gulf | 33 | final | 7,890 | 97% | 63 | 9 | $103,690 | 0.00 | 7 | 3s | 267 | modelled | yes |
| Franklin | 29 | final | 7,546 | 100% | 39 | 8 | $99,223 | 2.41 | 2 | 4s | 265 | modelled | yes |
| Putnam | 64 | final | 17,717 | 99% | 66 | 58 | $71,895 | 0.62 | 9 | 8s | 321 | modelled | yes |
| Leon | 47 | final | 79,735 | 100% | 76 | 63 | $67,821 | 2.19 | 6 | 20s | 665 | modelled | yes |
| Hendry | 36 | final | 8,998 | 96% | 72 | 25 | $65,609 | 0.00 | 3 | 3s | 266 | measured | yes |
| Gadsden | 30 | final | 11,271 | 98% | 32 | 40 | $31,469 | 0.00 | 3 | 4s | 286 | modelled | yes |
| Jackson | 42 | final | 10,302 | 99% | 30 | 60 | $24,432 | 2.05 | 4 | 3s | 280 | modelled | yes |
| Holmes | 40 | final | 3,401 | 97% | 26 | 44 | $22,811 | 1.60 | 2 | 2s | 242 | modelled | yes |
| Columbia | 22 | final | 13,997 | 100% | 26 | 31 | $19,911 | 8.93 | 1 | 8s | 301 | modelled | yes |
| Washington | 77 | final | 5,588 | 100% | 24 | 28 | $18,868 | 0.00 | 2 | 3s | 254 | modelled | yes |
| Levy | 48 | final | 8,719 | 99% | 23 | 8 | $17,808 | 0.00 | 1 | 16s | 272 | modelled | yes |
| Wakulla | 75 | final | 10,770 | 99% | 16 | 9 | $16,332 | — | 0 | 4s | 283 | modelled | yes |
| Bradford | 14 | final | 6,121 | 100% | 15 | 16 | $12,953 | 0.00 | 2 | 3s | 257 | modelled | yes |
| Okeechobee | 57 | final | 8,033 | 100% | 16 | 16 | $11,825 | — | 0 | 3s | 268 | modelled | yes |
| DeSoto | 24 | preliminary | 6,781 | 99% | 9 | 25 | $11,111 | — | 0 | 3s | 261 | modelled | yes |
| Suwannee | 71 | final | 6,508 | 100% | 8 | 16 | $7,842 | — | 0 | 5s | 259 | modelled | yes |
| Taylor | 72 | final | 5,094 | 95% | 6 | 7 | $6,294 | 0.00 | 1 | 3s | 251 | modelled | yes |
| Dixie | 25 | final | 2,904 | 97% | 6 | 17 | $4,835 | — | 0 | 2s | 239 | modelled | yes |
| Madison | 50 | final | 3,270 | 99% | 5 | 11 | $3,903 | — | 0 | 2s | 241 | modelled | yes |
| Gilchrist | 31 | final | 3,133 | 100% | 6 | 1 | $3,861 | — | 0 | 2s | 241 | modelled | yes |
| Lafayette | 44 | final | 1,072 | 99% | 4 | 3 | $3,653 | — | 0 | 2s | 229 | modelled | yes |
| Hardee | 35 | final | 4,462 | 100% | 3 | 0 | $2,742 | — | 0 | 4s | 248 | modelled | yes |
| Calhoun | 17 | final | 2,555 | 96% | 4 | 11 | $2,341 | — | 0 | 2s | 237 | modelled | yes |
| Baker | 12 | final | 5,181 | 100% | 3 | 7 | $1,826 | — | 0 | 3s | 252 | modelled | yes |
| Hamilton | 34 | final | 2,007 | 99% | 2 | 0 | $1,688 | — | 0 | 2s | 234 | modelled | yes |
| Union | 73 | final | 1,496 | 99% | 0 | 3 | $0 | — | 0 | 2s | 232 | modelled | yes |
| Liberty | 49 | preliminary | 1,338 | 94% | 0 | 0 | $0 | — | 0 | 2s | 231 | modelled | yes |
| Jefferson | 43 | final | 2,945 | 99% | 0 | 4 | $0 | — | 0 | 2s | 240 | modelled | yes |
| Glades | 32 | final | 2,233 | 99% | 0 | 2 | $0 | — | 0 | 2s | 236 | modelled | yes |

## Memory — measured, not guessed

Six counties run end to end, peak RSS recorded 2026-11-08 after the Arrow-string and column-drop changes:

| County | Homes | Peak RSS | Fits ~958 MB sandbox |
|---|---:|---:|---|
| Hendry | 8,998 | **266 MB** | yes |
| Martin | 66,288 | **518 MB** | yes |
| Bay | 86,114 | **636 MB** | yes |
| Charlotte | 108,514 | **976 MB** | NO |
| Pasco | 216,250 | **1,441 MB** | NO |
| Lee | 362,290 | **2,200 MB** | NO |

Model for the other 61: `peak_mb ≈ 223 + 0.00554 × homes`. Indicative only — Charlotte landed ~20% above the line because condo-heavy counties build larger peer groups.

**The ceiling is roughly 100,000 homes.** Of the 11 validated counties only **Martin** and **Bay** fit comfortably; Charlotte is marginal. Lee was 2,606 MB before these changes and is 2,200 MB now — the rest is structural, because the roll and the screened frame are both held in full. Fixing that means streaming peer groups and never materialising a whole county: a real refactor, not tuning.

## Blockers

**Memory — 21 counties do not fit.** Includes every large validated county: Dade, Broward, Palm Beach, Orange, Duval, Lee, Pasco, Volusia.

**Validation — 17 counties are `weak`**, mostly storm-affected Gulf-coast markets where post-hurricane sales break the comparison. Cards held. A data problem, not a bug.

**Validation — 39 counties are `untested`**: too few post-valuation arm's-length sales for a holdout at n>=30.

**Filing windows** verified for Volusia, Miami-Dade and Broward only. All others carry `verified: false`.

## Read before quoting any number here

1. **Savings use an assumed 1.5% millage**, not billed rates. Payloads carry `annual_savings_range` over a 1.1–2.2% band.
2. **Coverage** is the share of house/condo parcels that got a peer group. Parcels with no neighbourhood code, under 300 sq ft or under $20k just value are excluded by design.
3. **`lift` is one roll year.** Passing once is not passing repeatedly.
4. **Bay re-ran at 1,496 strong / $1,942,582** vs 1,495 / $1,941,421 in the statewide run — the roll file changed between runs. Small, expected, and a reminder these are snapshots.
