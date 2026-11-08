/**
 * S0 · Intake & validation — is the record complete and trustworthy enough to judge?
 * Stops with INCOMPLETE (I_*) so Find can enrich and resend.
 */
import { CandidateSchema, type Candidate, type DeskConfig } from "../types.js";
import { daysBetween, getPath, normName } from "../util.js";

export type IntakeResult =
  | { ok: true; cand: Candidate; notes: string[] }
  | { ok: false; codes: string[]; detail: string; parcelId: string; jurisdictionId: string; address: string };

const MAX_PLAUSIBLE_AREA = 1_000_000;
const MAX_PLAUSIBLE_RATE = 0.2;

export function intake(raw: unknown, cfg: DeskConfig, today: string): IntakeResult {
  const id = {
    parcelId: String(getPath(raw, "parcelId") ?? "unknown"),
    jurisdictionId: String(getPath(raw, "jurisdictionId") ?? "unknown"),
    address: String(getPath(raw, "situsAddress") ?? ""),
  };

  // Schema: separate "missing" from "wrong type".
  const parsed = CandidateSchema.safeParse(raw);
  if (!parsed.success) {
    const missing: string[] = [];
    const wrong: string[] = [];
    for (const issue of parsed.error.issues) {
      const path = issue.path.map(String);
      (getPath(raw, path) === undefined ? missing : wrong).push(path.join(".") + (getPath(raw, path) === undefined ? "" : `: ${issue.message}`));
    }
    if (missing.length) return { ok: false, codes: ["I_MISSING"], detail: `missing ${missing.join(", ")}`, ...id };
    return { ok: false, codes: ["I_SCHEMA"], detail: wrong.join("; "), ...id };
  }
  const c = normalize(parsed.data, cfg);
  const notes: string[] = [];

  // Sanity.
  const bad: string[] = [];
  if (!(c.assessment.assessedValue > 0)) bad.push("assessedValue must be > 0");
  if (!(c.physical.livingArea > 0 && c.physical.livingArea < MAX_PLAUSIBLE_AREA)) bad.push("livingArea out of range");
  if (!(c.assessment.taxRate > 0 && c.assessment.taxRate < MAX_PLAUSIBLE_RATE)) bad.push("taxRate out of range");
  for (const [label, d] of [
    ["valuationDate", c.assessment.valuationDate],
    ["fetchedAt", c.provenance.fetchedAt],
    ["transfer.date", c.transfer?.date],
    ["lastPermitDate", c.physical.lastPermitDate],
  ] as const) {
    if (d && d > today) bad.push(`${label} is in the future`);
  }
  if (bad.length) return { ok: false, codes: ["I_INVALID"], detail: bad.join("; "), ...id };

  // Comps with impossible values are dropped, not fatal.
  if (c.comps) {
    const before = c.comps.length;
    c.comps = c.comps.filter((k) => k.price > 0 && k.livingArea > 0 && k.distance >= 0 && k.saleDate <= today);
    if (c.comps.length < before) notes.push(`dropped ${before - c.comps.length} invalid comp(s)`);
  }

  // Freshness.
  if (c.assessment.valuationDate !== cfg.jurisdiction.valuationDate)
    return {
      ok: false,
      codes: ["I_STALE"],
      detail: `assessment is for ${c.assessment.valuationDate}, desk is for ${cfg.jurisdiction.valuationDate}`,
      ...id,
    };
  const age = daysBetween(c.provenance.fetchedAt, today);
  if (age > cfg.thresholds.maxSourceAgeDays)
    return { ok: false, codes: ["I_STALE"], detail: `data fetched ${age} days ago (max ${cfg.thresholds.maxSourceAgeDays})`, ...id };

  return { ok: true, cand: c, notes };
}

/** Standardize addresses, names, and property-type codes to the engine vocabulary. */
export function normalize(c: Candidate, cfg: DeskConfig): Candidate {
  const aliases = cfg.jurisdiction.propertyTypeAliases;
  const type = (t: string) => {
    const u = t.trim().toUpperCase();
    return (aliases[u] ?? u).toUpperCase();
  };
  return {
    ...c,
    situsAddress: c.situsAddress.trim().replace(/\s+/g, " "),
    propertyType: type(c.propertyType),
    owner: {
      ...c.owner,
      names: c.owner.names.map(normName).filter(Boolean),
      mailingAddress: c.owner.mailingAddress?.trim().replace(/\s+/g, " ") || undefined,
    },
    comps: c.comps?.map((k) => ({ ...k, propertyType: type(k.propertyType) })),
  };
}

/**
 * Dedupe: one record per (jurisdictionId, parcelId). Records are merged oldest → newest,
 * so the newest value wins field group by field group.
 */
export function dedupe(raws: unknown[]): { records: unknown[]; merged: number } {
  const groups = new Map<string, Record<string, unknown>[]>();
  const passthrough: unknown[] = [];
  for (const r of raws) {
    const p = getPath(r, "parcelId");
    const j = getPath(r, "jurisdictionId");
    if (typeof p !== "string" || typeof j !== "string") {
      passthrough.push(r);
      continue;
    }
    const k = `${j}::${p}`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(r as Record<string, unknown>);
  }
  let merged = 0;
  const out: unknown[] = [...passthrough];
  for (const recs of groups.values()) {
    if (recs.length === 1) {
      out.push(recs[0]);
      continue;
    }
    merged += recs.length - 1;
    recs.sort((a, b) => String(getPath(a, "provenance.fetchedAt") ?? "").localeCompare(String(getPath(b, "provenance.fetchedAt") ?? "")));
    const m: Record<string, unknown> = {};
    for (const r of recs) {
      for (const [k, v] of Object.entries(r)) {
        if (v === undefined) continue;
        const prev = m[k];
        m[k] =
          v && typeof v === "object" && !Array.isArray(v) && prev && typeof prev === "object" && !Array.isArray(prev)
            ? { ...(prev as object), ...(v as object) }
            : v;
      }
    }
    out.push(m);
  }
  return { records: out, merged };
}
