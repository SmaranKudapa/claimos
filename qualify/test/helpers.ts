import { loadDeskConfig } from "../src/config.js";
import type { QualifyContext } from "../src/draft.js";
import type { LlmClient } from "../src/llm/client.js";
import { MemoryLlmCache } from "../src/llm/client.js";
import { SuppressionSchema, type DeskConfig, type QualifyResult } from "../src/types.js";

export const TODAY = "2026-11-05";
export const NOW = "2026-11-05T12:00:00.000Z";

export function config(patch: (c: DeskConfig) => void = () => {}): DeskConfig {
  const c = structuredClone(loadDeskConfig("config/desk.placeholder.json"));
  patch(c);
  return c;
}

export function ctx(over: Partial<QualifyContext> = {}): QualifyContext {
  return {
    config: config(),
    today: TODAY,
    suppression: SuppressionSchema.parse({}),
    priorResults: new Map<string, QualifyResult>(),
    llm: null,
    llmCache: new MemoryLlmCache(),
    models: { primary: "test-model", escalation: null },
    ...over,
  };
}

export const withLlm = (llm: LlmClient, over: Partial<QualifyContext> = {}) => ctx({ llm, ...over });

/** Tight comps around a price per unit area — a clean, winnable lead by default. */
export function comps(ppa: number, area: number, n = 5, prefix = "K") {
  const sizes = [0.95, 1.0, 1.05, 0.9, 1.1, 0.97, 1.03, 1.08];
  const adj = [1.0, 0.98, 1.02, 0.99, 1.01, 1.0, 0.985, 1.015];
  const dates = ["2025-08-14", "2025-09-30", "2025-10-22", "2025-11-18", "2025-12-09", "2026-01-20", "2026-02-11", "2026-03-05"];
  return Array.from({ length: n }, (_, i) => {
    const a = Math.round(area * sizes[i % 8]!);
    return {
      compId: `${prefix}${i + 1}`,
      price: Math.round(a * ppa * adj[i % 8]!),
      saleDate: dates[i % 8]!,
      livingArea: a,
      propertyType: "SFR",
      yearBuilt: 1965,
      distance: 0.2 + 0.1 * i,
      armsLength: true,
    };
  });
}

export function candidate(over: Record<string, unknown> = {}): Record<string, unknown> {
  const base: Record<string, unknown> = {
    parcelId: "T-1",
    jurisdictionId: "placeholder",
    situsAddress: "1 Test Lane",
    propertyType: "SFR",
    owner: { names: ["Pat Example"], type: "individual", mailingAddress: "1 Test Lane", ownerOccupied: true },
    assessment: { assessedValue: 1_050_000, valuationDate: "2026-01-01", taxRate: 0.012, exemptions: [] },
    physical: { livingArea: 1400, lotArea: 4200, yearBuilt: 1965 },
    comps: comps(650, 1400),
    status: { appealOnFile: false },
    provenance: { fetchedAt: "2026-10-30", sources: {}, rawDocs: [] },
  };
  for (const [k, v] of Object.entries(over)) {
    const b = base[k];
    base[k] = v && typeof v === "object" && !Array.isArray(v) && b && typeof b === "object" && !Array.isArray(b) ? { ...(b as object), ...(v as object) } : v;
  }
  return base;
}

/** A valid review where everything passes. */
export function passReview(over: Record<string, unknown> = {}) {
  return {
    checks: ["C1", "C2", "C3", "C4", "C5", "C6", "C7"].map((id) => ({ id, verdict: "pass", evidence: ["subject.assessment.assessedValue"], note: "ok" })),
    recommended_action: "proceed",
    comps_to_exclude: [],
    p_win_adjustment: 0,
    summary: "All checks pass.",
    ...over,
  };
}

export function withCheck(review: ReturnType<typeof passReview>, id: string, verdict: string, evidence: string[]) {
  return { ...review, checks: review.checks.map((c) => (c.id === id ? { ...c, verdict, evidence } : c)) };
}
