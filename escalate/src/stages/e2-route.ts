/** E2 · Route by outcome — wins, waits and technicalities stop here; partials and denials go on. */
import { rungById } from "../config.js";
import { block, log, stop, type Draft } from "../draft.js";
import { addDays, daysBetween } from "../util.js";
import { evidenceWhy } from "./e6-evidence.js";

export function route(d: Draft): void {
  const { ctx, c, d: dec } = d;
  const f = d.facts!;
  const cfg = ctx.config;
  switch (f.outcome) {
    case "full_win":
      return stop(d, "E2", "W_FULL_WIN", f.newAssessedValue ? `new value ${f.newAssessedValue} ≤ target ${c.targetValue}` : "granted in full");

    case "not_final":
      if (f.hearingDate) {
        d.requeueOn = f.hearingDate >= ctx.today ? addDays(f.hearingDate, 1) : addDays(ctx.today, 1);
        return stop(d, "E2", "P_HEARING_SCHEDULED", `hearing ${f.hearingDate}; check again ${d.requeueOn}`);
      }
      d.requeueOn = addDays(ctx.today, cfg.reader.notFinalRecheckDays);
      return stop(d, "E2", "P_NOT_FINAL", `no final decision yet; check again ${d.requeueOn}`);

    case "dismissed_procedural": {
      const key = f.proceduralReason && cfg.proceduralReasons[f.proceduralReason] ? f.proceduralReason : "other";
      const rule = cfg.proceduralReasons[key]!;
      const cur = rungById(cfg, c.currentLevel);
      if (!cur) return stop(d, "E2", "C_UNHANDLED", `current level ${c.currentLevel} is not on the ladder`);
      if (!f.decisionDate) d.flags.add("F_DATE_FROM_RECEIPT");
      const base = f.decisionDate ?? dec.receivedOn;
      if (rule.curable && rule.refileWithinDays) {
        const deadline = addDays(base, rule.refileWithinDays);
        const daysLeft = daysBetween(ctx.today, deadline);
        if (daysLeft >= cur.fastTrackDays) {
          d.next = { rung: cur, deadline, daysLeft, fastTrack: daysLeft < cur.workDaysNeeded + cur.bufferDays };
          d.evidenceRequests = [{ key, why: evidenceWhy(key), forStep: "evidence" }];
          return stop(d, "E2", "A_REFILE_SAME_LEVEL", `dismissed (${key}); fix and refile at ${cur.id} by ${deadline} (${daysLeft}d left)`);
        }
        return stop(d, "E2", "C_PROCEDURAL_BAR", `dismissed (${key}); refile window ends ${deadline}, only ${daysLeft}d left (need ${cur.fastTrackDays})`);
      }
      return stop(d, "E2", "C_PROCEDURAL_BAR", `dismissed (${key}); not fixable`);
    }

    case "partial_reduction":
      d.mode = "partial";
      if (f.newAssessedValue === undefined) return block(d, "E2", "C_UNHANDLED", "partial reduction without a verified new value");
      d.currentValue = f.newAssessedValue;
      return log(d, "E2", "pass", `partial: ${c.assessedValue} → ${f.newAssessedValue} (target ${c.targetValue})`);

    case "denied":
      d.mode = "denied";
      d.currentValue = c.assessedValue;
      if (f.newAssessedValue !== undefined && f.newAssessedValue > c.assessedValue) {
        d.flags.add("F_VALUE_INCREASED");
        d.currentValue = f.newAssessedValue;
      }
      return log(d, "E2", "pass", `denied${f.reasonCategories.length ? ` (${f.reasonCategories.join(", ")})` : ""}; value under appeal ${d.currentValue}`);

    default:
      return stop(d, "E2", "C_UNHANDLED", `outcome ${f.outcome} has no rule`);
  }
}
