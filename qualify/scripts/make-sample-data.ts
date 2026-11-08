/**
 * Generates synthetic candidates that exercise every outcome of the pipeline.
 * Deterministic (seeded) so tests and demos are repeatable. Nothing here is real data.
 *
 *   npx tsx scripts/make-sample-data.ts
 */
import { mkdirSync, writeFileSync } from "node:fs";

let seed = 20261105;
const rand = () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const between = (lo: number, hi: number) => lo + (hi - lo) * rand();

const SALE_DATES = ["2025-07-14", "2025-08-30", "2025-09-22", "2025-10-18", "2025-11-09", "2025-12-05", "2026-01-20", "2026-02-11", "2026-03-05"];
const FETCHED = "2026-10-30";

interface CompOpts {
  n: number;
  spread?: number;
  type?: string;
  far?: number;
  old?: number;
  outlier?: number; // multiplier for one extra outlier comp
  yearBuilt?: number;
}

function comps(id: string, ppa: number, area: number, o: CompOpts) {
  const out: Record<string, unknown>[] = [];
  const spread = o.spread ?? 0.05;
  for (let i = 0; i < o.n; i++) {
    const a = Math.round(area * between(0.85, 1.15));
    out.push({
      compId: `${id}-C${i + 1}`,
      price: Math.round((a * ppa * between(1 - spread, 1 + spread)) / 1000) * 1000,
      saleDate: SALE_DATES[i % SALE_DATES.length],
      livingArea: a,
      propertyType: o.type ?? "SFR",
      yearBuilt: o.yearBuilt ? o.yearBuilt + Math.round(between(-8, 8)) : undefined,
      distance: Math.round(between(0.1, 0.8) * 100) / 100,
      armsLength: true,
    });
  }
  for (let i = 0; i < (o.far ?? 0); i++)
    out.push({ compId: `${id}-F${i + 1}`, price: Math.round(area * ppa * 1.1), saleDate: "2025-11-01", livingArea: area, propertyType: o.type ?? "SFR", distance: 2 + i, armsLength: true });
  for (let i = 0; i < (o.old ?? 0); i++)
    out.push({ compId: `${id}-O${i + 1}`, price: Math.round(area * ppa * 1.2), saleDate: "2024-05-10", livingArea: area, propertyType: o.type ?? "SFR", distance: 0.3, armsLength: true });
  if (o.outlier)
    out.push({ compId: `${id}-X1`, price: Math.round(area * ppa * o.outlier), saleDate: "2025-12-15", livingArea: area, propertyType: o.type ?? "SFR", distance: 0.4, armsLength: true });
  return out;
}

let n = 100;
function cand(id: string, p: Partial<Record<string, unknown>> & { area: number; assessed: number; ppa?: number; compOpts?: CompOpts }) {
  const { area, assessed, ppa, compOpts, ...over } = p;
  n++;
  const base: Record<string, unknown> = {
    parcelId: id,
    jurisdictionId: "placeholder",
    situsAddress: `${n} Sample Street`,
    propertyType: "SFR",
    owner: { names: [`Owner ${id}`], type: "individual", mailingAddress: `${n} Sample Street`, ownerOccupied: true },
    assessment: {
      assessedValue: assessed,
      valuationDate: "2026-01-01",
      taxRate: 0.012,
      history: [{ valuationDate: "2025-01-01", assessedValue: Math.round(assessed * 0.98) }],
      exemptions: [],
    },
    physical: { livingArea: area, lotArea: Math.round(area * 3), yearBuilt: 1965 },
    status: { appealOnFile: false },
    provenance: { fetchedAt: FETCHED, sources: { assessment: "assessor-roll", comps: "sales-feed" }, rawDocs: [] },
    ...(ppa ? { comps: comps(id, ppa, area, compOpts ?? { n: 5, yearBuilt: 1965 }) } : {}),
  };
  for (const [k, v] of Object.entries(over)) {
    const b = base[k];
    base[k] = v && typeof v === "object" && !Array.isArray(v) && b && typeof b === "object" ? { ...(b as object), ...(v as object) } : v;
  }
  return base;
}

const C = [
  // Qualified
  cand("P-1001", { area: 1400, assessed: 1_050_000, ppa: 650, provenance: { fetchedAt: FETCHED, sources: {}, rawDocs: [{ ref: "roll-1001", kind: "assessment_record", text: "Parcel P-1001. Single family, 1,400 sq ft, built 1965. No permits on file." }] } }),
  cand("P-1003", { area: 950, assessed: 720_000, ppa: 670, propertyType: "CONDOMINIUM", compOpts: { n: 5, type: "CONDO", yearBuilt: 1965 } }),
  cand("P-1023", { area: 1250, assessed: 880_000, ppa: 610 }),
  cand("P-1026", { area: 1500, assessed: 960_000, ppa: 560 }),

  // Needs review
  cand("P-1002", { area: 2100, assessed: 2_050_000, ppa: 760, compOpts: { n: 6, spread: 0.04, yearBuilt: 1965 } }), // high value
  cand("P-1006", { area: 1800, assessed: 1_275_000, ppa: 620, transfer: { date: "2025-06-15", price: 1_240_000, armsLength: true } }), // recent sale
  cand("P-1007", { area: 1650, assessed: 1_150_000, ppa: 590, physical: { livingArea: 1650, lotArea: 5000, yearBuilt: 1965, lastPermitDate: "2025-08-01", permitTypes: ["ADDITION"] } }),
  cand("P-1008", { area: 1500, assessed: 1_060_000, ppa: 580, owner: { names: ["Hill Family Trust"], type: "trust", mailingAddress: "PO Box 12", ownerOccupied: false } }),
  cand("P-1020", { area: 1400, assessed: 1_000_000, ppa: 640, compOpts: { n: 5, spread: 0.03, yearBuilt: 1965, outlier: 0.55 } }), // outlier comp
  cand("P-1022", {
    area: 1350,
    assessed: 940_000,
    ppa: 600,
    provenance: { fetchedAt: FETCHED, sources: {}, rawDocs: [{ ref: "permit-1022", kind: "permit_record", text: "Kitchen remodel and rear addition, finaled 2025-09." }] },
  }),

  // Next cycle (uniformity basis only fileable on a closed route)
  cand("P-1021", { area: 1600, assessed: 900_000, ppa: 545, neighborhood: { medianAssessmentRatio: 0.82 } }),

  // Rejected
  cand("P-1004", { area: 1600, assessed: 820_000, ppa: 500 }), // gap too small
  cand("P-1005", { area: 1700, assessed: 310_000, ppa: 760 }), // long-held, below market
  cand("P-1009", { area: 3200, assessed: 2_400_000, ppa: 650, compOpts: { n: 2, far: 3, old: 2 } }), // too few usable comps
  cand("P-1012", { area: 1500, assessed: 1_100_000, ppa: 600, status: { appealOnFile: true } }),
  cand("P-1013", { area: 12_000, assessed: 6_800_000, ppa: 450, propertyType: "COMMERCIAL" }),
  cand("P-1014", { area: 4000, assessed: 3_000_000, ppa: 500, owner: { names: ["City Parks Department"], type: "government", mailingAddress: "1 Civic Way" } }),
  cand("P-1015", { area: 1400, assessed: 1_000_000, ppa: 600 }), // on DNC list
  cand("P-1018", { area: 1400, assessed: 1_020_000, ppa: 520, compOpts: { n: 3, spread: 0.35 } }), // noisy comps
  cand("P-1019", { area: 600, assessed: 160_000, ppa: 230 }), // savings too small
  cand("P-1024", { area: 1100, assessed: 600_000, ppa: 505 }), // EV too low
  cand("P-1025", { area: 1450, assessed: 1_020_000, ppa: 600 }), // declined recently

  // Incomplete
  cand("P-1010", { area: 1500, assessed: 1_000_000 }), // comps never fetched
  (() => {
    const c = cand("P-1011", { area: 1500, assessed: 1_000_000, ppa: 600 });
    delete (c.assessment as Record<string, unknown>).taxRate;
    return c;
  })(),
  cand("P-1016", { area: 1500, assessed: 1_000_000, ppa: 600, provenance: { fetchedAt: "2026-07-01", sources: {}, rawDocs: [] } }), // stale

  // Duplicate of P-1001, older fetch — merged away by dedupe
  cand("P-1001", { area: 1400, assessed: 1_040_000, ppa: 650, provenance: { fetchedAt: "2026-10-01", sources: {}, rawDocs: [] } }),
];

const suppression = {
  dncParcels: ["P-1015"],
  dncOwners: [],
  clientParcels: [],
  representedParcels: [],
  declined: [{ parcelId: "P-1025", date: "2026-08-01" }],
};

mkdirSync("data", { recursive: true });
writeFileSync("data/candidates.sample.json", JSON.stringify(C, null, 2) + "\n");
writeFileSync("data/suppression.sample.json", JSON.stringify(suppression, null, 2) + "\n");
console.log(`wrote ${C.length} candidates and a suppression list to data/`);
