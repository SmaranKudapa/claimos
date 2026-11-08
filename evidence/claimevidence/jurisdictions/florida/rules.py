from __future__ import annotations

import datetime as dt

RETRIEVED = "2026-11-07"

FS = "https://www.flsenate.gov/Laws/Statutes/2026/Chapter194/All"
OLR = "https://floridarevenue.com/property/Documents/OtherLegalResources2025.pdf"
UPPM = "https://floridarevenue.com/property/Documents/UniformPoliciesManual2025.pdf"
CAB = "https://floridarevenue.com/rules/pdf/cabinet_agenda_092926.pdf"
R9 = "https://floridarevenue.com/rules/pdf/codedtext12d9.pdf"
TRN = "https://floridarevenue.com/property/Documents/2026VABTrainingAllModules.pdf"
DR486 = "https://floridarevenue.com/property/Documents/dr486.pdf"
DR493 = "https://floridarevenue.com/property/Documents/2026%20All-County%20DR-493.pdf"
S475 = "https://flsenate.gov/Laws/Statutes/2025/0475.611"
S194171 = "https://flsenate.gov/Laws/Statutes/2025/194.171"
BAY_VAB = "https://www.baycoclerk.com/clerk-services/value-adjustment-board/"
PTO2501 = "https://floridarevenue.com/property/Documents/PTO_BUL_25-02.pdf"
PTO2601 = "https://floridarevenue.com/property/Documents/PTO_BUL_26-01.pdf"
CERT26 = "https://floridarevenue.com/rules/pdf/Certification%20for%2012D-9.014,%20.019,%20.%20020,%20.026.pdf"
DR486POA = "https://floridarevenue.com/property/Documents/dr486poa.pdf"
DR486A = "https://floridarevenue.com/property/Documents/dr486a.pdf"
DR481 = "https://floridarevenue.com/property/Documents/dr481.pdf"
FORMS = "https://floridarevenue.com/property/Pages/Forms.aspx"
BAY_SITE = "https://baycountyvab.com/"
HENDRY_VAB = "https://www.hendryclerk.org/value-adjustment-board/"
HENDRY_ORG = "https://hendry-county.s3.amazonaws.com/uploads/2026/11/05125124/Hendry-VAB-2026-O-Mtg-Agenda-Packet-V4-FINAL-FINAL_ada.pdf"
LEE_UP = "https://www.leeclerk.org/departments/value-adjustment-board/evidence-upload-1818"
LEE_LPP = "https://www.leeclerk.org/home/showpublisheddocument/17424/639264752250670000"
LEE_NCI = "https://www.leeclerk.org/home/showpublisheddocument/4921/638253586171500000"
PB_FAQ = "https://www.mypalmbeachclerk.com/about-us/frequently-asked-questions-faq/value-adjustment-board-vab-faq"
AOSC = "https://www.circuit5.org/wp-content/uploads/2026/06/aosc26-12.pdf"

VAB = ("fl_vab_value_petition",)
ALLP = ("fl_vab_value_petition", "fl_informal_conference", "fl_circuit_court_value")


EFFECTIVE = {"FL-EVX-01": "2025-09-01", "FL-EVX-02": "2025-09-01", "FL-EVX-03": "2026-11-02", "FL-EVX-04": "2026-11-02",
             "FL-EVX-05": "2026-08-27", "FL-EVX-08": "2026-11-02", "FL-HRG-02": "2026-11-02", "FL-HRG-04": "2026-11-02",
             "FL-SCOPE-04": "2026-08-27", "FL-ADM-02": "2026-08-27", "FL-FEE-01": "2025-07-01", "FL-FORM-01": "2026-11-02",
             "FL-EVX-07": "2026-01-01", "HENDRY-REM-01": "2026-08-12", "BAY-PET-01": "2026-09-24"}
ENDS = {"HENDRY-REM-01": "2027-06-01", "BAY-PET-01": "2027-06-01"}


def R(id, jurisdiction, topic, summary, status, source, section, effective=None, proceedings=VAB, appeal_types=None,
      applied_as="", automated=None, human_review=None, implementation="implemented", cite_in_packet=False, effective_from=None, effective_to=None):
    return {"id": id, "jurisdiction": jurisdiction, "topic": topic, "summary": summary, "status": status, "source": source,
            "section": section, "effective": effective, "effective_from": effective_from or EFFECTIVE.get(id),
            "effective_to": effective_to or ENDS.get(id), "retrieved": RETRIEVED, "proceedings": list(proceedings),
            "appeal_types": list(appeal_types) if appeal_types else None, "applied_as": applied_as, "automated": automated,
            "human_review": human_review, "implementation": implementation, "cite_in_packet": cite_in_packet}


RULES: list[dict] = [
    R("FL-VAL-01", "FL", "valuation_date", "Real property is valued as of January 1 of the tax year.", "mandatory", OLR, "s. 192.042(1)",
      applied_as="All sales are time-adjusted to January 1; later sales are disclosed and not used.", automated="V-CALC-TIME", cite_in_packet=True),
    R("FL-VAL-03", "FL", "just_value_standard", "The property appraiser must consider eight factors, including arm's-length sale price net of purchase costs and condition.",
      "mandatory", OLR, "s. 193.011", applied_as="Sales comparison with condition disclosed as a limitation.", cite_in_packet=True),
    R("FL-VAL-05", "FL", "cost_of_sale", "Apply the county's DR-493 eighth-criterion percentage to comparable-sales evidence not already adjusted; show the arithmetic; never deduct twice.",
      "recommended", TRN, "Module 6, pp. 154-166", effective="2026",
      applied_as="Just value indication = market indication x (1 - DR-493 percentage). The county's measured level is shown as a cross-check only.",
      automated="V-CALC-COS", cite_in_packet=True),
    R("BAY-VAL-01", "FL:Bay", "cost_of_sale_rate", "Bay's 2026 DR-493 reports a 15 percent adjustment to recorded sale prices for every use-code group.",
      "mandatory", DR493, "PDF p. 8", effective="signed 2026-06-29", applied_as="15 percent for use codes 01 and 04.", automated="V-CALC-COS"),
    R("HENDRY-VAL-01", "FL:Hendry", "cost_of_sale_rate", "Hendry's 2026 DR-493 reports a 15 percent adjustment for every listed use-code group.",
      "mandatory", DR493, "PDF p. 41", effective="2026 roll", applied_as="15 percent for use codes 01 and 04.", automated="V-CALC-COS"),
    R("LEE-VAL-01", "FL:Lee", "cost_of_sale_rate", "Lee's 2026 DR-493 reports a 15 percent adjustment for every listed use-code group.",
      "mandatory", DR493, "PDF p. 54", effective="signed 2026-06-30", applied_as="15 percent for use codes 01 and 04.", automated="V-CALC-COS"),
    R("FL-SCOPE-01", "FL", "board_scope", "The board may set a revised just value only from competent, substantial evidence in the record; it is not bound to either party's number.",
      "mandatory", UPPM, "R. 12D-9.027(2)", applied_as="The requested value is stated with its full derivation; no outcome is promised.", automated="V-TEXT-CLAIMS"),
    R("FL-SCOPE-02", "FL", "assessment_cap", "A just-value reduction changes a capped assessed value only where the new just value falls below it.",
      "mandatory", OLR, "s. 193.155(1)-(2); R. 12D-9.027(3)", applied_as="Homestead cap effect stated on the subject page and in the internal record."),
    R("FL-SCOPE-03", "FL", "one_reason_per_petition", "One reason per petition on DR-486; portability and deferral use other forms; exemption and classification petitions carry a different burden.",
      "mandatory", DR486, "DR-486 R. 11/26, p. 1; s. 194.301(2)(d)", effective="DR-486 eff. 11/26", applied_as="Only vab_just_value is supported; other appeal types are blocked at intake.",
      automated="I04"),
    R("FL-SCOPE-04", "FL", "no_increase", "In a petition to decrease, the board may not raise value above the property appraiser's presented value, except to correct a physical-attribute error after new notice and hearing.",
      "mandatory", R9, "R. 12D-9.025(6)(c)", effective="2026-08-27", applied_as="Recorded for reviewer risk assessment; not argued in the packet.", implementation="documented"),
    R("FL-BUR-02", "FL", "burden", "The petitioner must show by a preponderance of the evidence that the value is not just value, or is arbitrarily based on practices different from comparable property.",
      "mandatory", FS, "s. 194.301(2)", applied_as="Packet language never claims a higher or lower standard.", automated="V-TEXT-CLAIMS"),
    R("FL-EVX-01", "FL", "evidence_exchange", "At least 15 days before the hearing the petitioner must provide the property appraiser a list of evidence, a summary of witness testimony, and copies of all documents.",
      "mandatory", FS, "s. 194.011(4)(a); R. 12D-9.020(1)(a)1", effective="statute 2025-09-01; rule 2026-11-02",
      applied_as="Delivery manifest lists the exchange copy with its computed due date once a hearing date exists. The packet carries the evidence index and a witness section.",
      automated="D-EXCHANGE", human_review="Operator sends the copy and records proof of receipt.", cite_in_packet=True),
    R("FL-EVX-02", "FL", "evidence_exchange_appraiser", "At least 15 days before the hearing the property appraiser must give the petitioner its evidence, including the property record card, without a request. If late, the hearing is rescheduled unless the petitioner waives.",
      "mandatory", FS, "s. 194.011(4)(b); R. 12D-9.020(1)(a)2; PTO 25-02", effective="2025-09-01; rule 2026-11-02",
      applied_as="Tracked as an expected incoming delivery; a missing appraiser exchange is flagged for the reviewer.", implementation="partial"),
    R("FL-EVX-02-PRE2025", "FL", "evidence_exchange_appraiser", "Before September 1, 2025 the property appraiser had to provide its evidence only on the petitioner's written request, 7 days before the hearing.",
      "superseded", UPPM, "former R. 12D-9.020(2)-(3)", effective="through 2025-08-31", effective_to="2025-09-01",
      applied_as="Applies only to hearings before September 1, 2025; kept so older cases are judged by the rule then in force.", implementation="documented"),
    R("FL-EVX-03", "FL", "exchange_counting", "Count calendar days backward from the hearing, the day before the hearing being day 1. If day 15 is a Saturday, Sunday or legal holiday, use the previous non-holiday weekday. Provided means received.",
      "mandatory", CAB, "R. 12D-9.020(1)(b), (2)", effective="2026-11-02",
      applied_as="exchange_due() implements the count with a conservative holiday list; the date is a receipt date, so mail time must be added.", automated="D-EXCHANGE"),
    R("FL-EVX-04", "FL", "exchange_method", "Exchange by mail, hand delivery, overnight, fax, or email by agreement; parties may agree to different timing.",
      "mandatory", UPPM, "R. 12D-9.020(2) (renumbered 2026)", applied_as="Delivery method stays 'to be agreed with the property appraiser' unless configured for the county.",
      automated="D-METHOD", human_review="Operator confirms the method with the property appraiser."),
    R("FL-EVX-05", "FL", "requested_evidence", "If the property appraiser asks in writing for specific evidence the petitioner has and withholds, the petitioner cannot use it at the hearing.",
      "mandatory", FS, "s. 194.034(1)(h); R. 12D-9.020(1)(c)", effective="2026-08-27 / 2026-11-02",
      applied_as="Any written evidence request is an operator task; nothing is withheld by design.", human_review="Answer every written request in full and on time.", implementation="documented"),
    R("FL-EVX-06", "FL", "exchange_failure", "The 2026 amendments removed the statements that a petitioner may still present evidence without exchanging. The effect of not exchanging is unresolved.",
      "unresolved", CAB, "pp. 337-338; R. 12D-9.025(4)(a)", effective="2026", applied_as="Exchange is treated as mandatory."),
    R("FL-EVX-07", "FL", "property_record_card", "On receiving a petition the property appraiser must send the property record card or say where it is online.",
      "mandatory", FS, "s. 194.032(2)(a); R. 12D-9.015(16)", effective="2026-01-01",
      applied_as="The record card is recommended before review and expected from the property appraiser after the petition is filed.", implementation="partial"),
    R("FL-ADM-01", "FL", "admissibility", "Formal rules of evidence do not apply; relevant evidence is anything reasonably related to the statutory criteria. The magistrate rules on admissibility.",
      "mandatory", UPPM, "R. 12D-9.025(2)", applied_as="Every exhibit states its source; nothing claims admissibility.", automated="V-TEXT-CLAIMS"),
    R("FL-ADM-02", "FL", "present_at_hearing", "Nothing is considered unless presented and admitted at the hearing. Evidence filed with the clerk is not reviewed beforehand and copies must be brought to an in-person hearing.",
      "mandatory", R9, "R. 12D-9.025(4)(b)-(e)", effective="2026-08-27", applied_as="Hearing presentation is a separate delivery item; generating the packet is never treated as presentation."),
    R("FL-ADM-04", "FL", "comparable_sales", "No rule requires qualified sales, but the appraiser records qualification and s. 193.011(1) uses an arm's-length standard.",
      "recommended", OLR, "s. 193.114(2)(n); s. 193.011(1)", applied_as="Only sales qualified by the county (codes 01, 02) are used; unqualified sales are excluded and counted.",
      automated="V-CALC-COMPS", cite_in_packet=True),
    R("FL-ADM-05", "FL", "appraisal_report", "An appraisal report is inadmissible in a year its author serves as a magistrate for that county. No rule requires an appraisal.",
      "mandatory", FS, "s. 194.035(1); R. 12D-9.025(4)(g)", applied_as="No appraisal is produced. An owner-supplied appraisal is flagged for review.", human_review="Check the author against the county's magistrate list."),
    R("FL-ADM-06", "FL", "owner_testimony", "An owner is generally qualified to testify to the value of their own property.", "recommended", TRN, "Module 6, p. 147",
      applied_as="The witness section lists the owner only when the owner has agreed to testify.", implementation="implemented"),
    R("FL-ADM-07", "FL", "equity_evidence", "The board may consider assessments of comparable properties in homogeneous areas.", "mandatory", FS, "s. 194.034(5)",
      applied_as="The assessment comparison exhibit is offered as support only.", cite_in_packet=True),
    R("FL-ADM-08", "FL", "photographs", "Photographs, repair estimates, appraisals and closing statements are admissible if relevant; condition is a statutory factor.",
      "recommended", UPPM, "R. 12D-9.025(2)(b); TRN Module 4 p. 93", applied_as="Owner documents are included unaltered with document date and condition date shown separately."),
    R("FL-POST-01", "FL", "post_valuation_sales", "No statute or rule addresses sales after January 1. A 2008 DOR bulletin allows them only as support for January 1 value alongside earlier sales; case law is mixed.",
      "recommended", "https://bcpa.net/forms/DOR-PTO-08-02-PostDateSales.pdf", "PTO 08-02 (2008), currency unresolved",
      applied_as="Later sales are disclosed and not used to set the value.", automated="V-CALC-COMPS", human_review="Reviewer looks at every later sale."),
    R("BAY-POST-01", "FL:Bay", "post_valuation_sales_local", "Bay VAB's 2020 booklet: sales nearer January 1 carry more weight; later sales only if they show January 1 value.",
      "recommended", BAY_VAB, "2020 Information Guide, p. 4", effective="2020 (outdated document)", applied_as="Consistent with the statewide handling."),
    R("FL-SM-01", "FL", "magistrate", "Counties over 75,000 people use special magistrates; residential value magistrates are state-certified appraisers.",
      "mandatory", FS, "s. 194.035(1); R. 12D-9.010", applied_as="Packet is written for a certified-appraiser magistrate: method and arithmetic shown in full."),
    R("FL-HRG-01", "FL", "hearing_notice", "Hearing notice at least 25 calendar days before; 15 if rescheduled. One reschedule per party for good cause.",
      "mandatory", FS, "s. 194.032(2)(a), (d); R. 12D-9.019", applied_as="Deadlines are recomputed from the hearing date whenever it changes.", automated="D-RECOMPUTE"),
    R("FL-HRG-02", "FL", "remote_hearing_upload", "Counties of 75,000 or more must allow remote appearance on written request at least 10 days before. Remote evidence goes to the VAB by 9:00 a.m. at least two non-holiday workdays before the hearing, as PDF, with a cover page (petition number, parcel, name, party, phone, off-site witnesses) and sequential page numbers.",
      "mandatory", CAB, "s. 194.032(2)(b); R. 12D-9.026(2), (6), (7)", effective="statute 2026-01-01; rule 2026-11-02",
      applied_as="The identification page doubles as the cover page; every page is numbered; a remote upload is a separate delivery with its own due time.",
      automated="V-FMT-COVER", human_review="Operator adds petition number and phone before upload."),
    R("FL-HRG-03", "FL", "absent_petitioner", "A petitioner who will not attend must file evidence with the clerk before the hearing (DR-486: two copies) and still exchange with the appraiser.",
      "mandatory", DR486, "R. 12D-9.024(9)(b); DR-486 pp. 1, 3", applied_as="Conditional delivery item when the petitioner will not appear."),
    R("FL-REP-01", "FL", "representation", "A compensated unlicensed representative needs a power of attorney (DR-486POA); DR-486A is for uncompensated representatives only.",
      "mandatory", FS, "s. 194.034(1)(a)-(c); R. 12D-9.018(3)", applied_as="Intake blocks DR-486A for compensated use.", automated="I11"),
    R("FL-475-01", "FL", "appraisal_terms", "Only a certified or licensed appraiser may issue an appraisal report, which covers any communication of a value opinion about identified property regardless of title.",
      "mandatory", S475, "ss. 475.611(1)(a), 475.612, 475.626", proceedings=ALLP,
      applied_as="The packet never uses 'appraisal', 'appraised', 'certified' or 'licensed' and is framed as the petitioner's evidence.", automated="V-TEXT-CLAIMS"),
    R("FL-475-02", "FL", "paid_value_opinion", "Whether a paid unlicensed agent or software vendor may present its own value opinion without violating s. 475.612 is unresolved.",
      "unresolved", S475, "s. 475.612; s. 194.034(1)(b)", proceedings=ALLP, applied_as="Counsel review is required before compensated use.",
      human_review="Florida counsel"),
    R("FL-CONF-01", "FL", "confidentiality", "Tax returns, SSNs, financial records produced by the taxpayer, DR-219 data and income statements are confidential.",
      "mandatory", OLR, "s. 192.0105(4); s. 195.027(3), (6)", proceedings=ALLP, applied_as="County-facing text is scanned for identifiers and contact data; redactions remove text before rendering.",
      automated="V-PRIVACY"),
    R("FL-CONF-02", "FL", "record_retention", "Every exhibit becomes part of the board's record and is not returned. Whether exhibits are public records is not stated.",
      "unresolved", UPPM, "R. 12D-9.034; DR-481", applied_as="Treated as public: no owner contact data or comparable owner names in the packet.", automated="V-PRIVACY"),
    R("FL-INF-01", "FL", "informal_conference", "The informal conference is optional and does not extend the petition deadline.", "mandatory", FS, "s. 194.011(2); R. 12D-9.002",
      proceedings=("fl_informal_conference",), applied_as="Informal-conference packets say they do not stop the petition deadline."),
    R("FL-ERR-01", "FL", "characteristics_correction", "The property appraiser can correct measurement, clerical and material factual errors outside the VAB; there is no separate VAB characteristics petition.",
      "mandatory", OLR, "R. 12D-8.021; s. 197.122(3)", proceedings=("fl_informal_conference", "fl_vab_value_petition"),
      applied_as="A characteristics error is routed to the informal conference and also argued in the value petition."),
    R("FL-FEE-01", "FL", "filing_fee", "The VAB filing fee is set by the board up to $50 per parcel; an unpaid fee invalidates the petition.", "mandatory", PTO2601, "s. 194.013",
      effective="2025-07-01", applied_as="Owned by File; not part of the packet.", implementation="not_applicable"),
    R("FL-PAY-01", "FL", "partial_payment", "Pay non-ad valorem assessments and at least 75 percent of ad valorem taxes before delinquency or the petition is denied.",
      "mandatory", FS, "s. 194.014(1)", applied_as="Recorded for Chase; not part of the packet.", implementation="not_applicable"),
    R("FL-CC-01", "FL", "circuit_court", "A circuit court action is due within 60 days after certification for collection (or after a late board decision); the tax admitted in good faith must be paid first.",
      "mandatory", S194171, "s. 194.171(2)-(3); s. 193.122(2)", proceedings=("fl_circuit_court_value",),
      applied_as="Circuit court is legal_review_only. Claim OS does not generate court documents.", automated="F-FORUM"),
    R("FL-EVX-08", "FL", "witness_summary", "Witness summaries give each witness's name and address and the general subject of the testimony.",
      "mandatory", CERT26, "R. 12D-9.020(3) (formerly (5))", effective="2026-11-02",
      applied_as="The witnesses section is a table of name, address and subject; a missing address blocks the exchange delivery.", automated="V-WITNESS"),
    R("FL-HRG-04", "FL", "remote_request", "A remote-appearance request gives the petition number, parcel, name and a reply email, sent to the VAB address on DR-481, unless DR-486RMT was checked on the petition.",
      "mandatory", CERT26, "R. 12D-9.026(2)(a); DR-486RMT N. 08/26 (provisional)", effective="2026-11-02",
      applied_as="Recorded for the operator; Evidence does not send requests.", implementation="documented"),
    R("FL-FORM-01", "FL", "petition_form", "DR-486 (R. 11/26) is signed under penalty of perjury, with no notary; whoever signs becomes the taxpayer's agent for service.",
      "mandatory", DR486, "DR-486 Parts 3-5; R. 12D-9.018(2)", effective="R. 11/26", applied_as="File's form. Evidence never fills or signs it.",
      implementation="not_applicable"),
    R("FL-FORM-02", "FL", "power_of_attorney", "DR-486POA (R. 12/20) must be signed by the taxpayer with two witnesses and a notary.",
      "mandatory", DR486POA, "DR-486POA", effective="R. 12/20", applied_as="Intake accepts a compensated authorization only with a signed document reference and checksum; Sign up must collect witnesses and notarization.",
      automated="I11", human_review="Check the witnesses and notary on the signed document."),
    R("FL-FORM-03", "FL", "written_authorization", "DR-486A (N. 01/17) authorizes an uncompensated representative only; no notary or witness.",
      "mandatory", DR486A, "DR-486A", effective="N. 01/17", applied_as="Intake blocks DR-486A for compensated representation.", automated="I11"),
    R("FL-FORM-04", "FL", "evidence_format", "DOR prescribes no form or format for the petitioner's evidence, evidence list or witness list for in-person hearings.",
      "unknown", FORMS, "Forms page; none found", applied_as="Our template is labelled as our default.", implementation="documented"),
    R("FL-EV-01", "FL", "evidence_signature", "No statute or rule found that requires evidence to be signed, sworn, notarized or certified.",
      "unknown", UPPM, "none found", applied_as="The packet carries no signature block and never shows an unsigned form as signed.", automated="V-TEXT-PREPARER"),
    R("FL-FIL-01", "FL", "filing_with_clerk", "Filing means received by the clerk during open hours; electronic filing only where the board and clerk accept it; documents filed with the board are served on all parties.",
      "mandatory", UPPM, "R. 12D-9.016(1)-(4) (manual text partly garbled)", applied_as="Delivery statuses change only on a recorded receipt.", automated="D-EVENTS"),
    R("FL-AI-02", "FL", "court_ai", "In circuit court, Rule 2.515 makes the signer vouch that cited authorities exist and are accurate; AI use need not be disclosed and circuits may not add AI rules (AOSC26-12).",
      "mandatory", AOSC, "Rule 2.515(d)(2); AOSC26-12", effective="2026-06-15", proceedings=("fl_circuit_court_value",),
      applied_as="Court work is legal review only; Evidence generates nothing for court.", automated="F-FORUM"),
    R("BAY-PET-01", "FL:Bay", "petition_channel", "Bay's 2026 petitions go through the JustAppraised portal via baycountyvab.com, in person or by mail; $50 per petition, $5 per added parcel; the 2026 deadline was September 8, received by the clerk.",
      "mandatory", BAY_SITE, "VAB page and FAQ; Resolution 2026-001", effective="2026-09-24", applied_as="Petition deadline configured as verified; channel and fee are File's."),
    R("BAY-REM-01", "FL:Bay", "remote_hearings", "Bay's population is over 75,000, so remote appearance must be offered on request.", "mandatory", FS, "s. 194.032(2)(b)",
      applied_as="The remote upload stays in Bay's delivery plan."),
    R("BAY-EVX-01", "FL:Bay", "local_evidence_rules", "Bay publishes nothing on evidence delivery, formats, size limits, copies or remote procedures.", "unknown", BAY_VAB,
      "VAB page; 2026 organizational packet", applied_as="Method, copies and upload limits show as unknown in the delivery plan.",
      human_review="Confirm with the Bay clerk and property appraiser before the first exchange."),
    R("HENDRY-REM-01", "FL:Hendry", "remote_hearings", "Hendry's 2026 board opted out of remote hearings (Resolution No. 2, August 12, 2026).", "mandatory", HENDRY_ORG,
      "organizational packet pp. 133-134, 199", effective="2026-08-12", applied_as="The remote upload is marked not applicable for Hendry."),
    R("HENDRY-EVX-01", "FL:Hendry", "local_evidence_rules", "Hendry publishes no county-specific evidence delivery or format rules.", "unknown", HENDRY_VAB, "VAB page",
      applied_as="Statewide defaults only.", human_review="Confirm with the clerk before the first exchange."),
    R("LEE-EVX-01", "FL:Lee", "exchange_channel", "Lee: send the exchange to the property appraiser at vabmail@leepa.org or 239-533-6100; uploading to the clerk does not count as the exchange.",
      "mandatory", LEE_UP, "Evidence Upload page", effective="2026", applied_as="Configured as Lee's exchange method."),
    R("LEE-UP-01", "FL:Lee", "upload_format", "Lee uploads are PDF only. The upload page allows 64 MB per file; the local procedures say under 60 MB. Email fallback under 10 MB.",
      "mandatory", LEE_LPP, "LPP s. 3.E.3", effective="rev. 08/26/2026", applied_as="The stricter 60 MB limit is checked.", automated="V-FMT-COUNTY-SIZE"),
    R("LEE-ABS-01", "FL:Lee", "absent_petitioner_local", "Lee asks a non-attending petitioner to upload, or deliver one copy at least 15 business days before; DR-486 says two copies.",
      "unresolved", LEE_LPP, "LPP s. 3.E.2", effective="rev. 08/26/2026", applied_as="The delivery plan shows both and asks a person to confirm."),
    R("LEE-FMT-01", "FL:Lee", "page_numbers_local", "Lee asks that every page of multipage evidence be numbered (required for remote hearings); paper evidence unbound, no staples, photos on letter pages with captions.",
      "recommended", LEE_LPP, "LPP s. 3.E.4-5, 3.G.3(d)", effective="rev. 08/26/2026", applied_as="Every page is numbered; the packet is letter size.", automated="V-FMT-PAGENUM"),
    R("LEE-CONF-01", "FL:Lee", "confidential_local", "Lee uses Form NCI to request that confidential material be held separately.", "mandatory", LEE_NCI, "LPP s. 3.E.7; Form NCI",
      applied_as="No confidential material goes into the packet; an owner document needing protection is flagged for review.", implementation="documented"),
    R("PB-EVX-01", "FL:Palm Beach", "exchange_channel_local", "Palm Beach treats an AXIA upload as delivery to the property appraiser and tells petitioners not to send evidence to the VAB.",
      "mandatory", PB_FAQ, "FAQ s. 05", applied_as="Local to Palm Beach only; never applied to another county.", implementation="not_applicable"),
    R("CO-FMT-01", "ClaimOS", "page_format", "US Letter, 11 pt body, 8.5-9 pt tables, numbered pages with the case and version in the footer, bookmarks per section and exhibit, grayscale-safe.",
      "internal", "ClaimOS template", "-", proceedings=ALLP, applied_as="Our defaults. No Florida rule on fonts, margins or PDF standard was found.", automated="V-FMT"),
    R("CO-FMT-02", "ClaimOS", "file_size", "Keep each packet under 20 MB and 60 pages so it fits common email and portal limits.", "internal", "ClaimOS template", "-",
      proceedings=ALLP, applied_as="A larger packet fails format validation for review. County portal limits are unknown.", automated="V-FMT"),
    R("CO-AI-01", "ClaimOS", "ai_disclosure", "No AI-disclosure rule, guidance or order was found for VAB proceedings (DOR rules, forms, bulletins, the 2025 manual, Bay, Hendry, Lee and Palm Beach). The packet still states that software prepared it and that no appraiser, broker or attorney reviewed it.",
      "internal", "ClaimOS policy", "-", proceedings=ALLP, applied_as="Preparer line on the identification page.", automated="V-TEXT-PREPARER"),
]

COST_OF_SALE = {
    ("bay", 2026): {"rate": 0.15, "uses": ("001", "004"), "source": DR493, "section": "PDF p. 8", "rule": "BAY-VAL-01"},
    ("hendry", 2026): {"rate": 0.15, "uses": ("001", "004"), "source": DR493, "section": "PDF p. 41", "rule": "HENDRY-VAL-01"},
    ("lee", 2026): {"rate": 0.15, "uses": ("001", "004"), "source": DR493, "section": "PDF p. 54", "rule": "LEE-VAL-01"},
}


def _norm(county: str | None) -> str:
    return (county or "").strip().lower().replace(" county", "").replace("-", " ").replace(".", "")


def cost_of_sale(county: str | None, year: int | None, use: str | None) -> dict | None:
    c = COST_OF_SALE.get((_norm(county), year))
    if c and (use is None or str(use).zfill(3) in c["uses"]):
        return c
    return None


def rules_for(county: str | None, appeal_type: str | None, proceeding: str | None = None, on: dt.date | str | None = None) -> list[dict]:
    c = _norm(county)
    day = on.isoformat() if isinstance(on, dt.date) else on
    out = []
    for r in RULES:
        if day and ((r.get("effective_from") and day < r["effective_from"]) or (r.get("effective_to") and day >= r["effective_to"])):
            continue
        j = r["jurisdiction"]
        if j not in ("FL", "ClaimOS") and _norm(j.split(":", 1)[-1]) != c:
            continue
        if r.get("appeal_types") and appeal_type not in r["appeal_types"]:
            continue
        if proceeding and proceeding not in r["proceedings"]:
            continue
        out.append(r)
    return out


def _holidays(year: int) -> set[dt.date]:
    def nth(month, weekday, n):
        d = dt.date(year, month, 1)
        d += dt.timedelta(days=(weekday - d.weekday()) % 7)
        return d + dt.timedelta(weeks=n - 1)

    def last(month, weekday):
        d = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
        return d - dt.timedelta(days=(d.weekday() - weekday) % 7)

    def observed(d):
        return d - dt.timedelta(days=1) if d.weekday() == 5 else d + dt.timedelta(days=1) if d.weekday() == 6 else d

    thanks = nth(11, 3, 4)
    fixed = [dt.date(year, 1, 1), dt.date(year, 6, 19), dt.date(year, 7, 4), dt.date(year, 11, 11), dt.date(year, 12, 25)]
    days = {nth(1, 0, 3), nth(2, 0, 3), last(5, 0), nth(9, 0, 1), nth(10, 0, 2), thanks, thanks + dt.timedelta(days=1)}
    for f in fixed:
        days.add(f)
        days.add(observed(f))
    return days


def is_business_day(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in _holidays(d.year)


def exchange_due(hearing: dt.date, days: int = 15) -> dt.date:
    d = hearing - dt.timedelta(days=days)
    while not is_business_day(d):
        d -= dt.timedelta(days=1)
    return d


def remote_upload_due(hearing: dt.date) -> dt.datetime:
    d, n = hearing, 0
    while n < 2:
        d -= dt.timedelta(days=1)
        if is_business_day(d):
            n += 1
    return dt.datetime(d.year, d.month, d.day, 9, 0)


def remote_request_due(hearing: dt.date) -> dt.date:
    return exchange_due(hearing, 10)


DEADLINE_KEYS = ("petition_filing", "evidence_exchange_petitioner", "evidence_exchange_appraiser", "remote_appearance_request",
                 "remote_evidence_upload", "hearing_notice", "hearing", "written_decision", "circuit_court")

DEADLINE_SPECS = {
    "petition_filing": {"rule": "s. 194.011(3)(d); R. 12D-9.015(13)", "trigger": "TRIM notice mailing", "source": FS,
                        "computation": "on or before the 25th day after the TRIM notice is mailed; use the clerk's published date",
                        "basis": "county-specific; unverified unless the county's own publication is configured"},
    "evidence_exchange_petitioner": {"rule": "s. 194.011(4)(a); R. 12D-9.020(1)", "trigger": "hearing date", "source": CAB,
                                     "computation": "received by the property appraiser by day 15 counting back from the day before the hearing; rolls back over weekends and holidays",
                                     "basis": "set once the hearing is scheduled"},
    "evidence_exchange_appraiser": {"rule": "s. 194.011(4)(b); R. 12D-9.020(1)", "trigger": "hearing date", "source": CAB,
                                    "computation": "same count as the petitioner", "basis": "set once the hearing is scheduled"},
    "remote_appearance_request": {"rule": "s. 194.032(2)(b); R. 12D-9.026(2)", "trigger": "hearing date", "source": CAB,
                                  "computation": "written request at least 10 days before the hearing, same counting method",
                                  "basis": "only if appearing remotely"},
    "remote_evidence_upload": {"rule": "R. 12D-9.026(6), (7)", "trigger": "hearing date", "source": CAB,
                               "computation": "to the VAB by 9:00 a.m. at least two non-holiday workdays before the hearing",
                               "basis": "only if appearing remotely"},
    "hearing_notice": {"rule": "s. 194.032(2)(a)", "trigger": "hearing date", "source": FS,
                       "computation": "notice received at least 25 calendar days before (15 if rescheduled)", "basis": "set by the clerk"},
    "hearing": {"rule": "s. 194.032", "trigger": "clerk's notice", "source": FS, "computation": "from the hearing notice", "basis": "set by the clerk"},
    "written_decision": {"rule": "s. 194.034(2)", "trigger": "board's last day in session", "source": FS,
                         "computation": "within 20 calendar days after the board's last day in session", "basis": "set by the board"},
    "circuit_court": {"rule": "s. 194.171(2)", "trigger": "certification for collection", "source": S194171,
                      "computation": "within 60 days after the assessment is certified for collection, or after a late board decision",
                      "basis": "legal review only"},
}

COUNTY_DEADLINES = {
    ("bay", 2026): {"petition_filing": {"date": "2026-09-08", "verified": True, "source": BAY_VAB,
                                        "basis": "Bay County Clerk VAB page and baycountyvab.com; the petition must be received by the clerk",
                                        "checked": RETRIEVED}},
}


RECIPIENT = {"petition_filing": "VAB clerk", "evidence_exchange_petitioner": "property appraiser", "evidence_exchange_appraiser": "petitioner",
             "remote_appearance_request": "VAB clerk", "remote_evidence_upload": "VAB clerk", "hearing_notice": "petitioner",
             "hearing": "special magistrate", "written_decision": "petitioner", "circuit_court": "circuit court clerk"}
HOLIDAYS = ("counted back in calendar days; a day that falls on a Saturday, Sunday or legal holiday moves to the previous working day. "
            "Legal holidays are not defined in the rule; Claim OS uses federal holidays plus the day after Thanksgiving, which can only move a date earlier")


def deadlines_for(county: str | None, year: int, hearing: str | None = None, today: dt.date | None = None) -> dict:
    from .forums import forum
    tz = ((forum("vab_just_value", county) or {}).get("county") or {}).get("timezone")
    out = {}
    for k in DEADLINE_KEYS:
        spec = DEADLINE_SPECS.get(k, {})
        out[k] = {"date": None, "verified": False, "source": spec.get("source"), "rule": spec.get("rule"),
                  "trigger": spec.get("trigger"), "computation": spec.get("computation"), "basis": spec.get("basis"),
                  "recipient": RECIPIENT.get(k), "timezone": tz or "unknown: county not configured", "legal": True,
                  "holiday_treatment": HOLIDAYS if k in ("evidence_exchange_petitioner", "evidence_exchange_appraiser", "remote_appearance_request",
                                                         "remote_evidence_upload") else None}
    for k, v in COUNTY_DEADLINES.get((_norm(county), year), {}).items():
        out[k].update(v)
    if hearing:
        h = dt.date.fromisoformat(hearing)
        out["hearing"].update({"date": h.isoformat(), "verified": True, "basis": "hearing date supplied from the clerk's notice"})
        ex = exchange_due(h).isoformat()
        for k in ("evidence_exchange_petitioner", "evidence_exchange_appraiser"):
            out[k].update({"date": ex, "verified": True, "basis": f"computed from the {h.isoformat()} hearing; a receipt date, so allow for delivery time"})
        target = dt.date.fromisoformat(ex)
        n = 0
        while n < 3:
            target -= dt.timedelta(days=1)
            if is_business_day(target):
                n += 1
        out["evidence_exchange_petitioner"]["internal_target"] = {"date": target.isoformat(), "legal": False,
                                                                   "basis": "Claim OS target: three working days before the legal date, to allow for delivery; never a substitute for it"}
        out["remote_appearance_request"].update({"date": remote_request_due(h).isoformat(), "verified": True, "basis": "computed; only if appearing remotely"})
        up = remote_upload_due(h)
        out["remote_evidence_upload"].update({"date": up.date().isoformat(), "time": "09:00", "verified": True,
                                              "basis": "computed; only if appearing remotely"})
        out["hearing_notice"].update({"date": (h - dt.timedelta(days=25)).isoformat(), "verified": True,
                                      "basis": "latest date the notice should have arrived for an original hearing"})
    t = (today or dt.date.today()).isoformat()
    for v in out.values():
        v["status"] = ("passed" if v["date"] < t else "upcoming") if v.get("date") else "unknown"
    return out


def matrix_markdown() -> str:
    head = "| ID | Requirement | Jurisdiction / proceeding | Source | Effective | Status | Applies | Automated check | Human review | Implementation |\n|---|---|---|---|---|---|---|---|---|---|\n"
    rows = []
    for r in RULES:
        eff = (r.get("effective_from") or "") + (" to " + r["effective_to"] if r.get("effective_to") else (" onward" if r.get("effective_from") else ""))
        rows.append("| {id} | {summary} | {j} / {p} | [{sec}]({src}) | {eff} | {status} | {applied} | {auto} | {hr} | {impl} |".format(eff=eff or (r.get("effective") or "-"),
            id=r["id"], summary=r["summary"].replace("|", "/"), j=r["jurisdiction"], p=", ".join(r["proceedings"]),
            sec=r["section"], src=r["source"] if str(r["source"]).startswith("http") else "#", status=r["status"],
            applied=r["applied_as"].replace("|", "/"), auto=r["automated"] or "-", hr=r["human_review"] or "-", impl=r["implementation"]))
    return head + "\n".join(rows) + "\n"
