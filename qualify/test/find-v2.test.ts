/**
 * Find → Qualify translator (Find handoff contract v2). All data here is synthetic.
 */
import { describe, expect, it } from "vitest";
import { CandidateSchema, type DeskConfig } from "../src/types.js";
import { loadDeskConfig } from "../src/config.js";
import { qualifyAll } from "../src/pipeline.js";
import { deskConfigFor, parseCardBody, parseJsonl, translateRecord, translateRun, type FindRecord } from "../src/adapters/find-v2.js";

const TEMPLATE = (): DeskConfig => loadDeskConfig("config/desk.florida.json");

function findRecord(over: Partial<FindRecord> = {}): FindRecord {
  const sales = Array.from({ length: 6 }, (_, i) => ({
    parcel_id: `S-${i}`,
    address: `${i} Sample Ln`,
    sale_month: `2025-${String(6 + i).padStart(2, "0")}`,
    price: 300_000 + i * 2_000,
    price_adjusted_to_valuation_date: 302_000 + i * 2_000,
    sqft: 1_500 + i * 10,
    record: `R${i}`,
  }));
  return {
    schema_version: 2,
    case_id: "XX-99-2026-P-1",
    desk: "property_tax",
    status: "candidate",
    tier: "strong",
    jurisdiction: { state: "XX", county: "Sample", county_code: "99", tax_year: 2026, roll_stage: "final", county_check: { status: "validated" } },
    property: { parcel_id: "P-1", address: "1  SAMPLE   ST", unit: null, city: "TESTVILLE", zip: "00000", use: "single_family", sqft: 1_520, effective_year_built: 1990.0, homestead: false },
    values: { just_value: 400_000, assessed_value: 400_000, taxable_value: 400_000, land_value: 80_000 },
    signals: { neighbor_ratio: 1.3, neighbor_count: 40, sales_ratio: 1.35, comp_count: 6, own_sale: null, county_level: 0.9 },
    estimate: { defensible_value: 280_000, value_cut: 120_000, annual_savings: 1_500, annual_savings_range: [1_300, 2_600], millage: 0.015 },
    confidence: { evidence_quality: 0.9, evidence_label: "strong" },
    explanation: "Flagged because the county value is above both neighbors and sales.",
    assumptions: ["Millage is assumed."],
    warnings: [],
    needs_verification: ["Confirm the deadline."],
    owner: { owner_id: "own_1", name: "EXAMPLE PAT", type: "individual", mailing_address: { line1: "1 Sample St", line2: null, city: "Testville", state: "XX", zip: "00000" }, absentee: false, may_have_changed: false },
    portfolio: { portfolio_id: "pf_1", flagged_parcels: 1 },
    evidence: { neighbors: [], sales },
    filing_window: { opens: "2026-08-15", closes: "2026-09-09", status: "closed", verified: false, basis: "estimate" },
    outreach: { eligible: false, blocked_by: ["no_consent"], owner_suppressed: false },
    source: { roll_file: "roll.zip", sales_file: "sales.zip", run_id: "RUN-1", found_at: "2026-11-07T23:00:00Z" },
    ...over,
  };
}

describe("translateRecord", () => {
  it("produces a schema-valid Qualify candidate with comps, rate, and provenance", () => {
    const { candidate, notes } = translateRecord(findRecord(), { valuationDate: "2026-01-01" });
    expect(CandidateSchema.safeParse(candidate).success).toBe(true);
    expect(candidate).toMatchObject({
      parcelId: "P-1",
      jurisdictionId: "XX-99",
      situsAddress: "1 SAMPLE ST, TESTVILLE, 00000",
      propertyType: "SFR",
      owner: { names: ["EXAMPLE PAT"], type: "individual", ownerOccupied: false },
      assessment: { assessedValue: 400_000, valuationDate: "2026-01-01" },
      physical: { livingArea: 1_520, yearBuilt: 1990 },
      neighborhood: { medianAssessmentRatio: 0.9 },
      status: { appealOnFile: false },
    });
    expect(candidate.assessment.taxRate).toBeCloseTo(1_500 / 120_000, 6); // effective rate from Find's own savings
    expect(candidate.comps).toHaveLength(6);
    expect(candidate.comps![0]).toMatchObject({ compId: "S-0", price: 302_000, saleDate: "2025-06-15", livingArea: 1_500, propertyType: "SFR", armsLength: true });
    expect(candidate.provenance.sources).toMatchObject({ find_case_id: "XX-99-2026-P-1", find_run_id: "RUN-1" });
    expect(candidate.provenance.rawDocs.map((d) => d.kind)).toEqual(expect.arrayContaining(["find_explanation", "find_signals", "find_needs_verification"]));
    expect(notes.some((n) => n.includes("effective tax rate"))).toBe(true);
  });

  it("leaves comps absent (never fetched) when the record has no evidence, e.g. a compact card", () => {
    const { candidate, notes } = translateRecord(findRecord({ evidence: undefined }), { valuationDate: "2026-01-01" });
    expect(candidate.comps).toBeUndefined();
    expect(notes.join(" ")).toMatch(/no evidence\.sales/);
  });

  it("drops the subject's own sale and keeps duplicate comp parcels distinct", () => {
    const r = findRecord();
    r.evidence!.sales!.push({ ...r.evidence!.sales![0]!, record: "R-again" }, { ...r.evidence!.sales![1]!, parcel_id: "P-1" });
    const ids = translateRecord(r, { valuationDate: "2026-01-01" }).candidate.comps!.map((c) => c.compId);
    expect(ids).not.toContain("P-1");
    expect(ids).toContain("S-0#R-again");
  });

  it("maps owner kinds and flags joint owners", () => {
    const t = (type: string, name = "X") => translateRecord(findRecord({ owner: { name, type } }), { valuationDate: "2026-01-01" }).candidate.owner.type;
    expect(t("company")).toBe("entity");
    expect(t("trust")).toBe("trust");
    expect(t("government")).toBe("government");
    expect(t("something_new")).toBe("entity");
    expect(t("individual", "DOE JOHN & JANE")).toBe("joint");
  });

  it("marks Find-suppressed owners for suppression", () => {
    const r = findRecord({ outreach: { eligible: false, owner_suppressed: true } });
    expect(translateRecord(r, { valuationDate: "2026-01-01" }).suppressParcel).toBe(true);
  });

  it("replay: dates a later retrieval to as-of so intake accepts it", () => {
    const { candidate, notes } = translateRecord(findRecord(), { valuationDate: "2026-01-01", asOf: "2026-08-25" });
    expect(candidate.provenance.fetchedAt).toBe("2026-08-25");
    expect(candidate.provenance.sources.find_found_at).toBe("2026-11-07T23:00:00Z");
    expect(notes.join(" ")).toMatch(/dated to 2026-08-25/);
  });
});

describe("deskConfigFor / translateRun", () => {
  it("takes route windows from Find and names the jurisdiction from the data", () => {
    const cfg = deskConfigFor(TEMPLATE(), findRecord({ filing_window: { opens: "2026-08-20", closes: "2026-09-14" } }));
    expect(cfg.jurisdiction.id).toBe("XX-99");
    expect(cfg.routes.every((r) => r.opens === "2026-08-20" && r.closes === "2026-09-14")).toBe(true);
  });

  it("groups by jurisdiction and collects suppression", () => {
    const a = findRecord();
    const b = findRecord({ case_id: "XX-98-2026-P-2", jurisdiction: { ...a.jurisdiction, county_code: "98", county: "Other" }, property: { ...a.property, parcel_id: "P-2" }, outreach: { owner_suppressed: true } });
    const batches = translateRun([a, b], TEMPLATE());
    expect(batches.map((x) => x.jurisdictionId).sort()).toEqual(["XX-98", "XX-99"]);
    expect(batches.find((x) => x.jurisdictionId === "XX-98")!.suppression.dncParcels).toEqual(["P-2"]);
  });

  it("end to end: inside the window the case qualifies; after it, it waits for next cycle", async () => {
    const [batch] = translateRun([findRecord()], TEMPLATE(), { asOf: "2026-08-25" });
    const ctx = (today: string) => ({ config: batch!.config, today, suppression: batch!.suppression, priorResults: new Map(), llm: null });
    const inWindow = await qualifyAll(batch!.candidates, ctx("2026-08-25"));
    expect(inWindow.results[0]!.status).toBe("QUALIFIED");
    expect(inWindow.results[0]!.route?.formId).toBe("DR-486");
    const [late] = translateRun([findRecord()], TEMPLATE(), { asOf: "2026-11-07" });
    const after = await qualifyAll(late!.candidates, { ...ctx("2026-11-07"), config: late!.config });
    expect(after.results[0]!.status).toBe("NEXT_CYCLE");
    expect(after.results[0]!.reasonCodes).toContain("T_NO_ROUTE");
  });
});

describe("parsing", () => {
  it("reads the JSON block out of a card body", () => {
    const body = 'Find flagged this home.\n\n```json\n{"schema_version": 2, "case_id": "XX-99-2026-P-1"}\n```';
    expect(parseCardBody(body)).toEqual({ schema_version: 2, case_id: "XX-99-2026-P-1" });
    expect(parseCardBody("no json here")).toBeNull();
  });

  it("parses jsonl and reports bad lines", () => {
    const { records, bad } = parseJsonl(`${JSON.stringify(findRecord())}\n\nnot json\n`);
    expect(records).toHaveLength(1);
    expect(bad).toEqual([3]);
  });
});
