# Open items

What Evidence does not do yet, what could not be verified, and what needs a decision. Each item says what happens
meanwhile.

## Needs counsel

| Item | Meanwhile |
|---|---|
| Whether a paid, unlicensed company may present its own value opinion without breaching s. 475.612 (an "appraisal report" covers any communication of a value opinion about identified property) | The packet is framed as the petitioner's evidence, never uses "appraisal", "appraised", "certified" or "licensed", and says no appraiser, broker or attorney prepared it. Compensated use should wait for a Florida attorney's view. |
| What happens if a petitioner does not exchange evidence (the 2026 amendments removed the old protection) | Exchange is treated as mandatory and appears in every delivery plan. |
| Whether VAB exhibits are public records | Treated as public: no owner contact data or comparable owners' names in any packet. |

## Not verified

| Item | Meanwhile |
|---|---|
| Bay and Hendry: the property appraiser's exchange method, hearing copies and any upload limits; Bay's JustAppraised evidence upload and 2026 hearing schedule | Shown as unknown in the delivery plan; a person confirms before the first exchange. |
| Lee's conflicting local numbers (64 MB vs 60 MB; one copy vs two for an absent petitioner) | The stricter size is checked; the copy count is marked unresolved. |
| DR-486RMT (remote request attachment) is provisional; DOR's rule workshop is November 12, 2026 | Recorded for the operator; Evidence sends no requests. |
| Hendry and Lee petition deadlines for 2026 | The petition deadline stays unverified and blocks filing readiness. Hendry's board opted out of remote hearings for 2026, so no remote upload is planned there. |
| Florida legal holidays for the 15-day count | A conservative calendar (federal holidays plus the day after Thanksgiving) moves due dates earlier, never later. |
| Font, margin, PDF-standard or AI-disclosure rules | None found. Our defaults are labelled as ours in the matrix. |

## Not built

| Item | Meanwhile |
|---|---|
| Fetching the property record card from the property appraiser (Bay's qPublic needs a terms click-through) | Recommended, not required; the appraiser must send it after a petition is filed (s. 194.032(2)(a)). |
| Homeowner photo and document upload through the portal | Owner documents can be passed in `homeowner_submissions` with their stored file and SHA-256; they are shown unaltered and dated. |
| Recording deliveries and approvals in the app | Approval is a line on the card; delivery events are passed in the input. Both are bound to the packet SHA-256. |
| Distance between properties | Location is compared by the county's neighbourhood and market-area codes, stated as a limitation. |
| Billed millage | Savings estimates use assumed rates and stay in the internal record only. |
| Counties beyond Bay, Hendry and Lee | Other counties run with `local_procedures: unknown` and no cost-of-sale rate, which the validation reports. |
| Lee in the agent sandbox | Lee's roll is large; running it in a Naïve session is untested. |

## Decisions for the team

- Fra's earlier README says DR-486A works for an unlicensed agent. It is for uncompensated representatives only; a paid
  agent needs a power of attorney (DR-486POA or chapter 709). Evidence's intake enforces this.
- The demo runs in replay mode because every Florida 2026 petition deadline has passed. Replay results never reach File.
- File supports Lee and Hendry; Find and Evidence run on Bay. An end-to-end File demo needs a Bay adapter in File or a
  Hendry case through Find and Evidence.
- Late petitions need a written good-cause explanation decided by the board (R. 12D-9.015(14)). Evidence reports a passed
  deadline and stops there.
