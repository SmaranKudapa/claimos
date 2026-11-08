/** E3 · Next level — which rung, can ClaimOS file there, is it authorized, is there time, is it safe? */
import { rungById } from "../config.js";
import { block, log, type Draft } from "../draft.js";
import { addDays, daysBetween } from "../util.js";

export function nextLevel(d: Draft): void {
  const { ctx, c, d: dec } = d;
  const cfg = ctx.config;
  const f = d.facts!;
  const cur = rungById(cfg, c.currentLevel);
  if (!cur) return block(d, "E3", "C_UNHANDLED", `current level ${c.currentLevel} is not on the ladder`);
  const next = cfg.ladder.find((r) => r.order === cur.order + 1);
  if (!next) return block(d, "E3", "C_LADDER_END", `${cur.id} is the last level`);
  if (next.requiresLicensedRep) return block(d, "E3", "C_REFER_OUT", `${next.id} needs a licensed representative`);

  const scope = c.authorization.scope;
  if (!scope.includes("all_levels") && ![next.id, ...next.aliases].some((id) => scope.includes(id)))
    return block(d, "E3", "C_NOT_AUTHORIZED", `authorization covers ${scope.join(", ")}, not ${next.id}`);

  if (!f.decisionDate) d.flags.add("F_DATE_FROM_RECEIPT");
  const computed = addDays(f.decisionDate ?? dec.receivedOn, next.deadline.days);
  const stated = f.statedNextStep?.deadline;
  let deadline = computed;
  if (stated && stated !== computed) {
    d.flags.add("F_DEADLINE_CONFLICT");
    deadline = stated < computed ? stated : computed;
  }
  const daysLeft = daysBetween(ctx.today, deadline);
  if (daysLeft < 0) {
    d.flags.add("F_MISSED_DEADLINE");
    return block(d, "E3", "C_DEADLINE_PASSED", `${next.id} deadline ${deadline} passed ${-daysLeft}d ago`);
  }
  let fastTrack = false;
  if (daysLeft < next.workDaysNeeded + next.bufferDays) {
    if (daysLeft < next.fastTrackDays) return block(d, "E3", "C_DEADLINE_TOO_CLOSE", `${daysLeft}d left, fast track needs ${next.fastTrackDays}`);
    fastTrack = true;
    d.flags.add("F_FAST_TRACK");
  }
  if (next.valueCanIncrease) {
    if (!c.authorization.escalation?.acceptReopenRisk) return block(d, "E3", "C_REOPEN_RISK", `${next.id} can raise the value and the owner did not accept that risk`);
    d.flags.add("F_REOPEN_RISK");
  }
  d.next = { rung: next, deadline, daysLeft, fastTrack };
  log(d, "E3", "pass", `${next.id} by ${deadline} (${daysLeft}d left${fastTrack ? ", fast track" : ""})`);
}
