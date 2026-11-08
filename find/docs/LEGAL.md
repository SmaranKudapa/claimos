# Legal requirements affecting Find and later outreach

**Every finding below was checked on 2026-11-07 against the source linked beside it.**
This is sourced research, not legal advice, and nobody here is a lawyer. Sections C and D exist
precisely because some questions cannot be answered without one.

Nothing in this document says the system is "compliant". It says what was verified, what was not,
and what must not happen until it is.

---

## 1. Who may represent an owner before a VAB — and the fee question that follows

Fla. Stat. [§ 194.034(1)](https://m.flsenate.gov/Statutes/194.034) gives three routes:

| Route | Who | Instrument needed |
|---|---|---|
| (1)(a) | Taxpayer's employee; Florida Bar attorney; ch. 475 licensed appraiser or broker; ch. 473 CPA | None at filing — may certify authorization under penalty of perjury |
| (1)(b) | **Any other person** | **Power of attorney** conforming to ch. 709 pt. II |
| (1)(c) | Any other person **receiving no compensation** | Written authorization |

**This business is compensated, so (1)(c) is not available to it.** A compensated unlicensed agent
must hold a power of attorney — [DR-486POA](https://www.manateepao.gov/data/downloads/dr486poa.pdf),
or any ch. 709 pt. II instrument. The POA is valid for **one taxpayer, one assessment year, enumerated
parcels**, needs two witnesses and a notary, and must be with the clerk **at filing**.
[DR-486A](https://floridarevenue.com/property/Documents/dr486a.pdf) is the uncompensated form and
should not be built into any workflow here.

Florida AGO [2002-58](https://www.myfloridalegal.com/node/2223) holds a VAB cannot impose licensing
requirements on agents by rule — but expressly declined to analyse unauthorized practice of law.

Employing a ch. 475 licensee or a Bar attorney as the signing representative removes the per-petition
POA burden entirely. That is a structural business decision with large compliance consequences.

> County VAB pages are unreliable restatements. Broward's omits the compensated/POA distinction and
> miscites the CPA chapter. Follow the statute, Rule 12D-9.018 and DR-486.

## 2. Filing deadlines differ by county — this one changed the code

[§ 194.011(3)](https://www.flsenate.gov/Laws/Statutes/2026/Chapter194/All): petitions are due on or
before the **25th day after the county mails its TRIM notice**. Counties mail on their own dates.

| County | 2026 deadline | Source |
|---|---|---|
| Volusia | **11 Sep 2026** | [volusia.org notice](https://www.volusia.org/file/7903/ADA_Petition_Deadline_2026_-_publication_date_08042026.pdf) |
| Miami-Dade | **18 Sep 2026** | [Miami-Dade Clerk](https://www.miamidadeclerk.gov/clerk/value-adjustment-board.page) |
| Broward | **18 Sep 2026** | [BCPA](https://bcpa.net/value.asp) |

A **7-day spread in one tax year.** Find previously applied one statewide estimate to all 67
counties. It now carries verified per-county dates where they have been read, and marks everything
else `verified: false`. The date printed on the owner's own TRIM notice stays authoritative.

Two deadline classes must not share a code path: valuation = 25 days from TRIM; exemption or
classification **denial** = 30 days from the denial notice. Rule 12D-9.015(14) also lets a board
accept a late petition for good cause, so "late" is not the same as "dead".

**Filing fee: up to $50 per parcel since 1 July 2025**, raised from $15 by ch. 2025-208
([PTO Bulletin 26-01](https://floridarevenue.com/TaxLaw/Documents/PTO%20BUL%2026-01%20Value%20Adjustment%20Board%20Petition%20Filing%20Fees.pdf)).
Boards set the actual figure by resolution, so it is per-county config. **An unpaid fee makes the
petition invalid.** Any $15 figure in older notes is out of date.

## 3. Using the roll — and the owners who must never be contacted

No general restriction on commercial reuse was found. DOR's portal carries no licence or reuse terms,
and a Florida AG informal opinion (27 May 2011) holds that a requester's purpose — including
commercial purpose — does not affect the right of access.

**But [§ 119.071(4)(d)](https://law.justia.com/codes/florida/title-x/chapter-119/section-119-071)
exempts the home address of a long list of people** — police, corrections and civilian law
enforcement staff, judges and judicial assistants, prosecutors, firefighters, code enforcement
officers, guardians ad litem, public defenders, EMTs and paramedics, child advocacy staff, domestic
violence advocates, county and city attorneys, clerk personnel and more — **usually extending to
spouses and children**. Victims of domestic violence, aggravated stalking and sexual battery are
covered separately under § 119.071(2)(j), with the exemption lapsing 5 years after request.

The mechanic that matters: under **§ 119.071(4)(d)4.a. the appraiser removes the NAME** while the
parcel address may legitimately remain public. So a suppressed owner shows up in a public roll as a
**blank or placeholder owner name against a real address**.

**Implemented in Find:** `SUPPRESSED_NAME_TOKENS` in `engine/people.py` treats an unreadable owner
name as **do-not-contact**, fails closed, and never tries to recover the name from another source.
Every payload carries `outreach.owner_suppressed`.

§ 119.105 restricts commercial solicitation from **police and accident reports only**. It does not
reach tax roll data, and no Florida statute was found restricting solicitation from the roll.

## 4. Email — CAN-SPAM ([FTC guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business))

**Prior consent is not required.** It is an opt-out regime. Mandatory: truthful headers, honest
subject line, identify the message as an ad, a **valid physical postal address**, a working opt-out,
honoured **within 10 business days**, with the mechanism live **at least 30 days**. Opting out must
cost nothing and require nothing beyond an email address, reachable by reply or a **single** web page.
After opt-out the address **may not be sold or transferred**. Up to **$53,088 per non-compliant
email**, and liability **cannot be contracted away** — both the promoted company and the sender can
be liable.

## 5. Calls and texts — the expensive part

**TCPA** ([47 U.S.C. § 227](https://www.law.cornell.edu/uscode/text/47/227)): marketing texts to
mobiles need prior express written consent. **$500 per violation**, trebled for willful. SMS counts
as a call.

**Florida FTSA** ([§ 501.059](https://www.flsenate.gov/laws/statutes/2024/501.059), as amended by
ch. 2023-150): prior express written consent for calls using an automated system for the selection
**and** dialing of numbers — the 2023 amendment made that conjunctive, narrowing it. **$500 per
violation, trebled for willful, with prevailing-party attorney fees** and an express class-action
pathway. Before suing over texts a consumer must reply STOP and give **15 days** to cease.

**Suppression obligations:**

| List | Cadence | Duration |
|---|---|---|
| National DNC | scrub every **31 days** | EBR 18 months (purchase) / 3 months (inquiry) |
| Florida FDACS list | then-current **quarterly** listing | consumer registration indefinite |
| Internal opt-out (§ 501.059(5)) | immediate | **no expiry — treat as permanent** |
| Confidential owners (§ 119.071) | each roll year | re-check every roll |

Revocation must be honoured by **any reasonable means** — stop, quit, end, revoke, opt out, cancel,
unsubscribe, or anything a reasonable person would read as revocation — within **10 business days**,
across all channels regardless of how it arrived. TSR requires **5-year** retention of consent and
opt-out records, including a copy of the consent request **as the consumer saw it**.

---

## A. Implemented in Find now

1. **Per-county verified deadlines** with source URL and check date; everything else `verified: false`.
2. **Confidential-owner suppression**, fail-closed, with the statutory reason recorded.
3. **Provenance on every record** — source file URL, roll stage, publication date, run id, timestamp.
4. **`outreach.eligible` is always `false`** and carries `blocked_by`. Candidate quality, contact
   verification and outreach eligibility are three separate concepts in the schema.
5. **Savings as a range**, never a bare promise, with every assumption listed.

## B. Operational, before any outreach

Per-county deadline collection each season · POA execution per taxpayer per year ·
decide the licensing posture (ch. 475 / Bar employee vs POA at volume) · National DNC subscription
and 31-day scrubs with the registry version recorded · FDACS quarterly listing · written consent
capture preserved as presented · 5-year retention · vendor oversight · a real physical postal address.

## C. Needs a Florida attorney

1. **Are contingency fees permissible for a non-attorney tax representative?** No Florida source
   found either way. Absence of a prohibition is not permission.
2. **Is this UPL?** Soliciting owners, selecting the appeal theory and arguing valuation for a fee.
   AGO 2002-58 declined to reach it. **This is the largest unresolved risk in the business.**
3. Is the calling pattern "telemarketing" under the TSR, and are the calls interstate?
4. Which § 501.604 exemption, if any, applies.
5. Does the intended SMS stack trigger the conjunctive § 501.059(8)(a) test?

## D. Blockers — these stop specific actions until answered

| # | Unresolved | Blocks |
|---|---|---|
| D1 | **Whether DOR's NAL actually suppresses § 119.071 owners, and how.** DOR says the files exclude them; the 2026 user guide documents no confidentiality flag and does not say whether names are blanked or rows omitted. | Any outbound contact against NAL owner names. Bay County returned **0 suppressed rows**, which is consistent either with real suppression upstream or with our heuristic never firing — it does not prove either. |
| D2 | Whether county-sourced files carry the same suppression | Ingesting any county file as a contact source |
| D3 | UPL (C2) | Filing any petition as representative; marketing representation |
| D4 | Compensated/uncompensated classification | Any DR-486A workflow. Build only the POA path |
| D5 | Whether the SMS stack triggers FTSA | Any SMS outreach |
| D6 | FDACS quarterly list access | Any Florida calling or texting |
