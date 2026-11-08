import type { BriefingInput } from './briefing.js';
import type { Parsed } from './parse.js';

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() && Number.isFinite(Number(v.replace(/[$,]/g, ''))) ? Number(v.replace(/[$,]/g, '')) : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v.trim() : null);

export function qualifyFromNote(note: string | null) {
  if (!note) return null;
  const verdict = note.match(/^(QUALIFIED|REJECTED|NEXT_CYCLE|INCOMPLETE|NEEDS_REVIEW|EVIDENCE)\b/)?.[1] ?? null;
  return {
    verdict,
    savings: num(note.match(/savings \$([\d,]+)\/yr/)?.[1]),
    fee: num(note.match(/fee \$([\d,]+)/)?.[1]),
    pWin: num(note.match(/P\(win\) ([\d.]+)/)?.[1]),
    deadline: note.match(/due (\d{4}-\d{2}-\d{2})/)?.[1] ?? null,
  };
}

export function briefingInput(find: Parsed, full: any | null, packet: any | null, feePct: number): BriefingInput {
  const j = full ?? find.json ?? {};
  const card = find.json ?? {};
  const p = { ...(card.property ?? {}), ...(j.property ?? {}) };
  const v = { ...(card.values ?? {}), ...(j.values ?? {}) };
  const est = { ...(card.estimate ?? {}), ...(j.estimate ?? {}) };
  const sig = j.signals ?? card.signals ?? {};
  const ev = j.evidence ?? {};
  const address = [str(p.address)?.replace(/\s+/g, ' '), str(p.city)].filter(Boolean).join(', ') || String(find.caseId);
  const q = qualifyFromNote(find.card.note);
  const range = Array.isArray(est.annual_savings_range) && est.annual_savings_range.length === 2 ? [num(est.annual_savings_range[0])!, num(est.annual_savings_range[1])!] as [number, number] : null;
  const warnings = [...(Array.isArray(j.warnings) ? j.warnings : []), ...(j.owner?.may_have_changed ? ['the owner of record may have changed since the roll was made'] : [])]
    .map((w: unknown) => (typeof w === 'string' ? w : str((w as any)?.message) ?? str((w as any)?.text) ?? null)).filter((w): w is string => !!w);
  return {
    caseId: String(find.caseId),
    address,
    county: str(j.jurisdiction?.county) ?? str(card.jurisdiction?.county),
    parcel: str(p.parcel_id),
    use: str(p.use),
    sqft: num(p.sqft) ?? num(packet?.subject?.sqft),
    yearBuilt: num(p.effective_year_built) ?? num(p.year_built) ?? num(packet?.subject?.year_built),
    justValue: num(v.just_value) ?? num(packet?.current_just_value) ?? 0,
    assessedValue: num(v.assessed_value),
    taxableValue: num(v.taxable_value),
    estimate: { defensibleValue: num(est.defensible_value), annualSavings: num(est.annual_savings), range, millage: num(est.millage) },
    neighbors: (Array.isArray(ev.neighbors) ? ev.neighbors : []).map((n: any) => ({ address: String(n.address ?? ''), sqft: num(n.sqft), justValue: num(n.just_value), perSqft: num(n.value_per_sqft) })),
    sales: (Array.isArray(ev.sales) ? ev.sales : []).map((s: any) => ({ address: String(s.address ?? ''), when: str(s.sale_month) ?? str(s.sale_date), price: num(s.price), adjusted: num(s.price_adjusted_to_valuation_date), sqft: num(s.sqft) })),
    ratios: { neighbor: num(sig.neighbor_ratio), neighborCount: num(sig.neighbor_count), sales: num(sig.sales_ratio), salesCount: num(sig.comp_count) },
    qualify: q && { verdict: q.verdict, pWin: q.pWin, fee: q.fee, savings: q.savings, deadline: q.deadline },
    evidence: packet && num(packet.requested_just_value) != null ? {
      requested: num(packet.requested_just_value)!,
      comps: (packet.sales_approach?.comps ?? []).filter((c: any) => c.arms_length !== false).map((c: any) => ({ address: String(c.address ?? ''), date: str(c.sale_date), price: num(c.sale_price), adjusted: num(c.adjusted_price ?? c.price_used), sqft: num(c.sqft), perSqft: num(c.per_sqft) })),
      equity: packet.equity_approach ? { peers: num(packet.equity_approach.peers), medianPerSqft: num(packet.equity_approach.median_per_sqft), subjectPerSqft: num(packet.equity_approach.subject_per_sqft), indicated: num(packet.equity_approach.indicated_just_value) } : null,
    } : null,
    filing: { closes: str(j.filing_window?.closes) ?? str(card.filing_window?.closes) ?? str(packet?.deadlines?.petition), status: str(j.filing_window?.status) ?? str(card.filing_window?.status) },
    warnings,
    feePct,
  };
}
