/**
 * Offline reader: keyword and pattern rules, good enough for the sample letters. No network, no
 * cost. Every fact it returns quotes the exact text it matched.
 */
import type { CountyDecision, DecisionReading, EscalateCase, EscalateConfig } from "../types.js";
import type { ReadOutcome, Reader } from "./types.js";

const DATE = String.raw`(\d{4}-\d{2}-\d{2})`;
const MONEY = String.raw`\$\s?([\d,]+(?:\.\d{2})?)`;

function first(text: string, re: RegExp): RegExpMatchArray | null {
  return text.match(re);
}

export class MockReader implements Reader {
  readonly name = "mock";

  async read(decision: CountyDecision, _c: EscalateCase, cfg: EscalateConfig): Promise<ReadOutcome> {
    const t = decision.text;
    const ev: { field: string; quote: string }[] = [];
    const r: DecisionReading = { outcome: "unclear", reasonCategories: [], confidence: 0.3, evidence: ev };
    const take = (field: string, m: RegExpMatchArray | null) => {
      if (m) ev.push({ field, quote: m[0] });
      return m;
    };

    // Outcome wording
    let m: RegExpMatchArray | null;
    if ((m = take("outcome", first(t, /hearing (?:has been|is) scheduled/i)))) r.outcome = "not_final";
    else if ((m = take("outcome", first(t, /\b(?:is|was|has been) dismissed\b/i)))) r.outcome = "dismissed_procedural";
    else if ((m = take("outcome", first(t, /granted in full|granted in its entirety|full relief/i)))) r.outcome = "full_win";
    else if ((m = take("outcome", first(t, /granted in part|partially granted|partial relief/i)))) r.outcome = "partial_reduction";
    else if ((m = take("outcome", first(t, /\b(?:is|was|has been) denied\b|value (?:is|was) sustained|no change to the assessed value/i)))) r.outcome = "denied";
    if (r.outcome !== "unclear") r.confidence = 0.9;

    // Numbers and dates
    const nv = take("newAssessedValue", first(t, new RegExp(String.raw`(?:reduced to|revised (?:assessed )?value of|new assessed value (?:is|of)|value (?:is|was) set at)\s*${MONEY}`, "i")));
    if (nv) r.newAssessedValue = Number(nv[1]!.replace(/,/g, ""));
    const dd = take("decisionDate", first(t, new RegExp(String.raw`(?:decision date|date of decision|decided on)[:\s]+${DATE}`, "i")));
    if (dd) r.decisionDate = dd[1]!;
    const hd = take("hearingDate", first(t, new RegExp(String.raw`scheduled for\s+${DATE}`, "i")));
    if (hd) r.hearingDate = hd[1]!;
    const nx = take("statedNextStep.deadline", first(t, new RegExp(String.raw`(?:appeal|petition|request)[^.]*?\b(?:by|no later than|on or before)\s+${DATE}`, "i")));
    if (nx) r.statedNextStep = { deadline: nx[1]! };

    // Reasons (keys must exist in the desk config)
    const reasons: [string, RegExp][] = [
      ["comps_rejected", /comparable sales[^.]*not comparable|comparables? (?:were|was) (?:rejected|not accepted)/i],
      ["insufficient_evidence", /insufficient evidence|did not provide (?:sufficient|enough) evidence/i],
      ["value_supported", /evidence supports the (?:assessed|current) value|value is supported/i],
      ["condition_not_shown", /condition (?:was|is) not (?:shown|demonstrated|documented)/i],
    ];
    for (const [key, re] of reasons) if (cfg.denialReasons[key] && take(`reasonCategories.${key}`, first(t, re))) r.reasonCategories.push(key);

    const procedural: [string, RegExp][] = [
      ["late_filing", /filed after the (?:filing )?deadline|untimely|not timely filed/i],
      ["missing_signature", /not signed|missing (?:a |the )?signature|unsigned/i],
      ["missing_authorization", /authorization (?:was )?(?:missing|not provided|not attached)/i],
      ["missing_form", /required form (?:was )?(?:missing|not attached|not provided)/i],
    ];
    if (r.outcome === "dismissed_procedural") {
      for (const [key, re] of procedural)
        if (cfg.proceduralReasons[key] && take("proceduralReason", first(t, re))) {
          r.proceduralReason = key;
          break;
        }
    }
    return { reading: r, model: "mock-reader", costUsd: 0, cached: false };
  }
}
