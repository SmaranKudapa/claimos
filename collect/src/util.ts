/** Small helpers copied from escalate/src/util.ts (itself from qualify; the repo has no shared package). */
import { createHash } from "node:crypto";

const DAY = 86_400_000;
const toUtc = (d: string) => Date.parse(`${d}T00:00:00Z`);

/** Whole days from a to b (b − a). */
export function daysBetween(a: string, b: string): number {
  return Math.round((toUtc(b) - toUtc(a)) / DAY);
}
export function addDays(d: string, n: number): string {
  return new Date(toUtc(d) + n * DAY).toISOString().slice(0, 10);
}
export function todayIn(timeZone?: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: timeZone || undefined, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}
export const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));
export const round = (x: number, dp = 0) => {
  const f = 10 ** dp;
  return Math.round(x * f) / f;
};
export function stableStringify(v: unknown): string {
  if (v === null || typeof v !== "object") return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(stableStringify).join(",")}]`;
  const o = v as Record<string, unknown>;
  return `{${Object.keys(o)
    .filter((k) => o[k] !== undefined)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${stableStringify(o[k])}`)
    .join(",")}}`;
}
export const sha256 = (s: string) => createHash("sha256").update(s).digest("hex");
export const money = (n: number) => "$" + Math.round(n).toLocaleString("en-US");
export const minDate = (a: string, b: string) => (a <= b ? a : b);
