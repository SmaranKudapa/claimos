import { createHash } from "node:crypto";

const DAY = 86_400_000;

/** Whole days from a to b (b − a). Both are YYYY-MM-DD, treated as UTC. */
export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / DAY);
}

export function addDays(d: string, n: number): string {
  return new Date(Date.parse(d + "T00:00:00Z") + n * DAY).toISOString().slice(0, 10);
}

/** Today's date in the given IANA time zone (defaults to the machine's). */
export function todayIn(timeZone?: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(),
  );
}

export const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));
export const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
export const round = (x: number, dp = 0) => {
  const f = 10 ** dp;
  return Math.round(x * f) / f;
};

/** Linear-interpolated quantile of an unsorted array. */
export function quantile(xs: number[], q: number): number {
  const s = [...xs].sort((a, b) => a - b);
  if (s.length === 0) return NaN;
  const pos = (s.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return s[lo]! + (s[hi]! - s[lo]!) * (pos - lo);
}

export const median = (xs: number[]) => quantile(xs, 0.5);
export const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
export const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0);

/** Stable JSON (sorted keys) so hashes don't depend on key order. */
export function stableStringify(v: unknown): string {
  if (Array.isArray(v)) return "[" + v.map(stableStringify).join(",") + "]";
  if (v && typeof v === "object") {
    return (
      "{" +
      Object.keys(v as object)
        .sort()
        .filter((k) => (v as Record<string, unknown>)[k] !== undefined)
        .map((k) => JSON.stringify(k) + ":" + stableStringify((v as Record<string, unknown>)[k]))
        .join(",") +
      "}"
    );
  }
  return JSON.stringify(v);
}

export const sha256 = (s: string) => createHash("sha256").update(s).digest("hex");

/** Read a dotted path like "a.b.0.c" from an object. */
export function getPath(obj: unknown, path: (string | number)[] | string): unknown {
  const parts = typeof path === "string" ? path.split(".") : path;
  let cur: unknown = obj;
  for (const p of parts) {
    if (cur === null || cur === undefined || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[String(p)];
  }
  return cur;
}

export const normName = (s: string) => s.trim().replace(/\s+/g, " ").toUpperCase();

export const money = (n: number) => "$" + Math.round(n).toLocaleString("en-US");
export const pct = (n: number, dp = 1) => (n * 100).toFixed(dp) + "%";
