/**
 * Find → Qualify translator (Find handoff contract, schema v2).
 *
 * Find (the `taxfind` package) posts one compact card per parcel to Qualify's board. The card
 * carries triage fields and a pointer to the full record in that run's published
 * `candidates.jsonl`, keyed by `case_id`. This module turns a full Find record into a Qualify
 * Candidate, builds a per-jurisdiction desk config from a desk template plus the record's own
 * filing window, and collects the suppression Find asks us to respect.
 *
 * Engine rule: nothing here names a jurisdiction. Jurisdiction knowledge comes from the desk
 * template the caller passes in (e.g. config/desk.<state>.json) and from Find's own fields.
 */
import type { Candidate, DeskConfig, Suppression } from "../types.js";

// ─── Find record (only the fields we read; everything else is ignored) ──────

export interface FindSale {
  parcel_id: string;
  sale_month: string; // YYYY-MM
  price: number;
  price_adjusted_to_valuation_date?: number | null;
  sqft: number;
  record?: string | null;
}

export interface FindRecord {
  schema_version: number;
  case_id: string;
  desk?: string;
  status?: string;
  tier?: string;
  jurisdiction: { state: string; county: string; county_code: string; tax_year: number; roll_stage?: string; county_check?: { status?: string } };
  property: {
    parcel_id: string;
    address: string;
    unit?: string | null;
    city?: string | null;
    zip?: string | null;
    use: string;
    sqft?: number | null;
    effective_year_built?: number | null;
    homestead?: boolean | number | null;
  };
  values: { just_value?: number | null; assessed_value?: number | null; taxable_value?: number | null; land_value?: number | null };
  signals?: {
    neighbor_ratio?: number | null;
    neighbor_count?: number;
    sales_ratio?: number | null;
    comp_count?: number;
    own_sale?: { price?: number | null; month?: string | null } | null;
    county_level?: number | null;
  };
  estimate?: {
    defensible_value?: number | null;
    value_cut?: number | null;
    annual_savings?: number | null;
    annual_savings_range?: [number, number] | null;
    millage?: number | null;
  };
  confidence?: { evidence_quality?: number; evidence_label?: string };
  explanation?: string;
  assumptions?: string[];
  warnings?: string[];
  needs_verification?: string[];
  owner?: {
    owner_id?: string;
    name?: string | null;
    type?: string | null;
    mailing_address?: Record<string, string | null> | null;
    absentee?: boolean;
    may_have_changed?: boolean;
  };
  portfolio?: { portfolio_id?: string; flagged_parcels?: number };
  evidence?: { neighbors?: unknown[]; sales?: FindSale[] };
  filing_window?: { opens?: string; closes?: string; status?: string; verified?: boolean; basis?: string; source?: string | null };
  outreach?: { eligible?: boolean; blocked_by?: string[]; owner_suppressed?: boolean };
  source?: { roll_file?: string; sales_file?: string; run_id?: string; found_at?: string };
}

export const SUPPORTED_SCHEMA_VERSIONS = [1, 2];

export interface TranslateOptions {
  /** Desk valuation date (from the desk template), e.g. "2026-01-01". */
  valuationDate: string;
  /**
   * Find compares a home only with sales in its own neighborhood / building but gives no
   * coordinates. Each comp is given this distance (in the desk's distance unit). Recorded in
   * provenance so it is never mistaken for a measured distance.
   */
  sameGroupDistance?: number;
  /**
   * The date Qualify judges as of (a replay date, or today). Records fetched after it, e.g. by a
   * few hours across time zones, are dated to it so the intake check accepts them; the real
   * retrieval date stays in provenance.sources.
   */
  asOf?: string;
}

export interface Translated {
  candidate: Candidate;
  /** Parcel ids Find says must not be contacted (unreadable / confidential owner). */
  suppressParcel: boolean;
  notes: string[];
}

const USE_TO_TYPE: Record<string, string> = { single_family: "SFR", condo: "CONDO" };

/** Find owner kinds → Qualify owner types. Unknown kinds fall back to "entity" (the cautious bucket). */
const OWNER_KIND: Record<string, Candidate["owner"]["type"]> = {
  individual: "individual",
  joint: "joint",
  trust: "trust",
  estate: "estate",
  government: "government",
  company: "entity",
  association: "entity",
  bank: "entity",
  religious_charity: "entity",
};

const isoDay = (s: string | undefined | null): string | undefined => (s && /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : undefined);
const midMonth = (ym: string): string | undefined => (/^\d{4}-\d{2}$/.test(ym) ? `${ym}-15` : undefined);
const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);

/** The jurisdiction id a Find record belongs to: "<state>-<county code>". */
export const jurisdictionIdFor = (r: FindRecord): string => `${r.jurisdiction.state}-${r.jurisdiction.county_code}`;

export function translateRecord(r: FindRecord, opts: TranslateOptions): Translated {
  const notes: string[] = [];
  if (!SUPPORTED_SCHEMA_VERSIONS.includes(r.schema_version)) notes.push(`unexpected Find schema_version ${r.schema_version}`);
  const p = r.property;
  const sameGroupDistance = opts.sameGroupDistance ?? 0.5;

  // Owner
  const rawName = (r.owner?.name ?? "").trim();
  const names = rawName ? [rawName] : [];
  let ownerType = OWNER_KIND[String(r.owner?.type ?? "").toLowerCase()] ?? "entity";
  if (ownerType === "individual" && /\s&\s/.test(rawName)) ownerType = "joint";
  const mail = r.owner?.mailing_address;
  const mailingAddress = mail
    ? [mail.line1, mail.line2, [mail.city, mail.state].filter(Boolean).join(", "), mail.zip].filter(Boolean).join(", ") || undefined
    : undefined;
  const homestead = Boolean(p.homestead);

  // Values. Find's just value is the county's market value: the number a value petition argues.
  const assessed = num(r.values.just_value) ?? num(r.values.assessed_value);
  // Effective tax rate: Find's savings already respect caps and exemptions, so savings ÷ value cut
  // is the rate that turns a value cut into real dollars. Fall back to the assumed millage.
  const cut = num(r.estimate?.value_cut);
  const sav = num(r.estimate?.annual_savings);
  const millage = num(r.estimate?.millage);
  let taxRate = millage;
  if (cut && cut > 0 && sav !== undefined && sav >= 0) {
    taxRate = sav / cut;
    if (millage !== undefined && Math.abs(taxRate - millage) > 1e-4)
      notes.push(`effective tax rate ${(taxRate * 100).toFixed(3)}% (caps/exemptions) vs assumed millage ${(millage * 100).toFixed(2)}%`);
  }

  // Comps: Find's comparable sales, same neighborhood / building and property use as the subject.
  let comps: Candidate["comps"];
  const sales = r.evidence?.sales;
  if (Array.isArray(sales)) {
    const seen = new Set<string>();
    comps = [];
    for (const s of sales) {
      const saleDate = midMonth(String(s.sale_month ?? ""));
      const price = num(s.price_adjusted_to_valuation_date) ?? num(s.price);
      const area = num(s.sqft);
      if (!saleDate || !price || !area || s.parcel_id === p.parcel_id) continue;
      let id = String(s.parcel_id);
      if (seen.has(id)) id = `${id}#${s.record || s.sale_month}`;
      seen.add(id);
      comps.push({ compId: id, price, saleDate, livingArea: area, propertyType: USE_TO_TYPE[p.use] ?? p.use, distance: sameGroupDistance, armsLength: true });
    }
  } else {
    notes.push("record has no evidence.sales (compact card?) — comps not fetched");
  }

  // Own sale → transfer (lets Qualify flag recent transfers).
  const own = r.signals?.own_sale;
  const ownDate = own?.month ? midMonth(own.month) : undefined;
  const transfer = ownDate && num(own?.price) ? { date: ownDate, price: own!.price as number, armsLength: true } : undefined;

  // Provenance and the text the AI reviewer reads.
  let fetchedAt = isoDay(r.source?.found_at) ?? opts.asOf ?? opts.valuationDate;
  if (opts.asOf && fetchedAt > opts.asOf) {
    notes.push(`fetchedAt ${fetchedAt} dated to ${opts.asOf} (replay date, or a time-zone difference with Find)`);
    fetchedAt = opts.asOf;
  }
  const docs: { ref: string; kind: string; text: string }[] = [];
  const push = (ref: string, kind: string, text: string | undefined) => text && docs.push({ ref, kind, text });
  push(`find:${r.case_id}:explanation`, "find_explanation", r.explanation);
  push(`find:${r.case_id}:assumptions`, "find_assumptions", r.assumptions?.join("\n"));
  push(`find:${r.case_id}:warnings`, "find_warnings", r.warnings?.length ? r.warnings.join("\n") : undefined);
  push(`find:${r.case_id}:needs_verification`, "find_needs_verification", r.needs_verification?.join("\n"));
  const facts = [
    r.signals?.neighbor_ratio != null && `Neighbor ratio ${r.signals.neighbor_ratio.toFixed(2)} over ${r.signals.neighbor_count ?? "?"} similar homes (county value per sq ft vs peers).`,
    r.signals?.sales_ratio != null && `Sales ratio ${r.signals.sales_ratio.toFixed(2)} over ${r.signals.comp_count ?? "?"} comparable sales.`,
    r.confidence?.evidence_quality != null && `Find evidence quality ${r.confidence.evidence_quality} (${r.confidence.evidence_label ?? "?"}).`,
    r.jurisdiction.county_check?.status && `County self-check: ${r.jurisdiction.county_check.status}.`,
    r.filing_window?.verified === false && `Filing deadline is an unverified estimate: ${r.filing_window.basis ?? ""}`,
    r.owner?.may_have_changed && "A deed was recorded after the valuation date: the owner may have changed.",
    comps && `Comp distances are not measured: every comp is from the subject's own neighborhood/building and is given a nominal distance of ${sameGroupDistance}.`,
    comps && "Comp prices are Find's time-adjusted prices (to the valuation date).",
  ].filter(Boolean) as string[];
  push(`find:${r.case_id}:signals`, "find_signals", facts.join("\n"));
  if (r.owner?.may_have_changed) notes.push("owner may have changed since the roll");

  const suppressParcel = Boolean(r.outreach?.owner_suppressed);
  if (suppressParcel) notes.push("owner suppressed by Find (unreadable/confidential owner) — do not contact");

  const situs = [p.address.replace(/\s+/g, " ").trim() + (p.unit ? ` #${p.unit}` : ""), p.city, p.zip].filter(Boolean).join(", ");

  const candidate: Candidate = {
    parcelId: p.parcel_id,
    jurisdictionId: jurisdictionIdFor(r),
    situsAddress: situs,
    propertyType: USE_TO_TYPE[p.use] ?? p.use,
    useCode: p.use,
    owner: { names, type: ownerType, ...(mailingAddress ? { mailingAddress } : {}), ownerOccupied: homestead },
    assessment: {
      assessedValue: assessed as number,
      valuationDate: opts.valuationDate,
      taxRate: taxRate as number,
      exemptions: homestead ? [{ type: "homestead", fullyExempt: false }] : [],
    },
    physical: {
      livingArea: num(p.sqft) as number,
      ...(num(p.effective_year_built) ? { yearBuilt: Math.round(p.effective_year_built as number) } : {}),
      permitTypes: [],
    },
    ...(transfer ? { transfer } : {}),
    ...(num(r.signals?.county_level) ? { neighborhood: { medianAssessmentRatio: r.signals!.county_level as number } } : {}),
    ...(comps ? { comps } : {}),
    status: { appealOnFile: false },
    provenance: {
      fetchedAt,
      sources: Object.fromEntries(
        Object.entries({
          find_case_id: r.case_id,
          find_run_id: r.source?.run_id,
          find_found_at: r.source?.found_at,
          roll_file: r.source?.roll_file,
          sales_file: r.source?.sales_file,
          filing_window_source: r.filing_window?.source ?? undefined,
        }).filter(([, v]) => typeof v === "string" && v),
      ) as Record<string, string>,
      rawDocs: docs,
    },
  };
  return { candidate, suppressParcel, notes };
}

/**
 * Desk config for one jurisdiction: the desk template with every route's window replaced by the
 * filing window Find computed for that jurisdiction. Find's window is the deadline evidence we
 * have; the template supplies everything else.
 */
export function deskConfigFor(template: DeskConfig, sample: FindRecord): DeskConfig {
  const fw = sample.filing_window ?? {};
  const opens = isoDay(fw.opens);
  const closes = isoDay(fw.closes);
  const j = sample.jurisdiction;
  return {
    ...template,
    version: `${template.version}+${jurisdictionIdFor(sample)}`,
    jurisdiction: { ...template.jurisdiction, id: jurisdictionIdFor(sample), name: `${j.county} County, ${j.state} (${j.tax_year})` },
    routes: template.routes.map((r) => ({ ...r, ...(opens ? { opens } : {}), ...(closes ? { closes } : {}) })),
  };
}

/** Pull the JSON payload out of a Find card body (human summary + fenced ```json block). */
export function parseCardBody(body: string): Record<string, unknown> | null {
  const m = body.match(/```json\s*([\s\S]*?)```/);
  if (!m) return null;
  try {
    return JSON.parse(m[1]!) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** Parse a candidates.jsonl file (one Find record per line). Blank and malformed lines are reported, not thrown. */
export function parseJsonl(text: string): { records: FindRecord[]; bad: number[] } {
  const records: FindRecord[] = [];
  const bad: number[] = [];
  text.split(/\r?\n/).forEach((line, i) => {
    if (!line.trim()) return;
    try {
      records.push(JSON.parse(line) as FindRecord);
    } catch {
      bad.push(i + 1);
    }
  });
  return { records, bad };
}

export interface FindBatch {
  jurisdictionId: string;
  config: DeskConfig;
  candidates: Candidate[];
  suppression: Suppression;
  notes: Map<string, string[]>; // parcelId → notes
}

/** Translate a whole Find run, grouped by jurisdiction (one desk config each). */
export function translateRun(records: FindRecord[], template: DeskConfig, opts: Omit<TranslateOptions, "valuationDate"> = {}): FindBatch[] {
  const groups = new Map<string, FindRecord[]>();
  for (const r of records) {
    const id = jurisdictionIdFor(r);
    groups.set(id, [...(groups.get(id) ?? []), r]);
  }
  return [...groups.entries()].map(([jurisdictionId, recs]) => {
    const config = deskConfigFor(template, recs[0]!);
    const suppression: Suppression = { dncParcels: [], dncOwners: [], clientParcels: [], representedParcels: [], declined: [] } as Suppression;
    const notes = new Map<string, string[]>();
    const candidates = recs.map((r) => {
      const t = translateRecord(r, { ...opts, valuationDate: template.jurisdiction.valuationDate });
      if (t.suppressParcel) suppression.dncParcels.push(t.candidate.parcelId);
      notes.set(t.candidate.parcelId, t.notes);
      return t.candidate;
    });
    return { jurisdictionId, config, candidates, suppression, notes };
  });
}
