// Admission: what, if anything, happens next on one pull request. No I/O, no clock.
import * as t from "./terms.ts";
import type { Config, Context, Decision, Facts, Run } from "./terms.ts";
import { derive, inProgress, runsOn, sinceWriter } from "./derive.ts";

const NEEDS_YOU_REASONS = new Set([
  "human_hold", "outside_not_admitted", "empty_diff", "too_large", "human_finding",
  "attempts_exhausted", "run_ceiling", "max_rounds", "approver_is_author_or_last_pusher", "awaiting_human",
]);

function attention(state: string | null, reason: string, working: boolean): string {
  if (state === null) return t.NONE;
  if (working) return t.WORKING;
  if (NEEDS_YOU_REASONS.has(reason)) return t.NEEDS_YOU;
  if (t.TERMINAL.has(state) || state === t.DRAFT || reason === "hands_off") return t.NONE;
  if (state === t.ADDRESSING) return t.FAILED;
  if (state === t.VERIFYING || state === t.ADJUDICATING) return t.REVIEW;
  return t.READY;
}

function wantedRun(state: string, reason: string, config: Config): [string, string] | null {
  if (state === t.VERIFYING && reason === "awaiting_review") return [config.required_lenses.model[0], "review-change"];
  if (state === t.ADDRESSING && ["check_failed", "findings_open", "human_finding", "conflict"].includes(reason)) {
    return config.author_role === null ? null : [config.author_role, "fix-findings"];
  }
  if (state === t.ADJUDICATING) return [config.owner_role, "adjudicate-findings"];
  return null;
}

export function decide(facts: Facts, runs: Run[], context: Context, config: Config, now: string): Decision {
  const d = derive(facts, runs, config);
  const out = (state: string | null, reason: string, evidence: string[], outcome: string,
               extra: Partial<Decision> = {}, working = false): Decision => ({
    schema: "decision/1", item: facts.item, state, reason, evidence: [...evidence],
    attention: attention(state, reason, working), outcome, ...extra,
  });

  if (d.state === null) return out(null, d.reason, d.evidence, t.DEFER);
  const state = d.state;
  if (t.TERMINAL.has(state) || state === t.DRAFT || state === t.QUEUED) return out(state, d.reason, d.evidence, t.NOTHING);
  if (state === t.HELD) return out(state, d.reason, d.evidence, t.HOLD);

  const mine = runsOn(runs, facts);
  if (inProgress(mine).length) return out(state, d.reason, d.evidence, t.NOTHING, {}, true);

  if (state === t.CONVERGED) {
    if (config.approver === facts.author || config.approver === facts.last_pusher) {
      return out(t.HELD, "approver_is_author_or_last_pusher", [], t.HOLD);
    }
    const action = d.reason === "approved" ? "enqueue" : "issue_approval";
    return out(state, d.reason, d.evidence, t.ACT, { action, content_id: facts.content_id });
  }

  const wanted = wantedRun(state, d.reason, config);
  if (wanted === null) return out(state, d.reason, d.evidence, t.NOTHING);
  const [role, intent] = wanted;

  if (context.paused !== false) return out(state, context.paused ? "paused" : "pause_unreadable", d.evidence, t.DEFER);
  const limits = config.limits;
  const recent = sinceWriter(mine, facts);
  const attempts = recent.filter((r) => r.intent === intent && r.status === "completed"
    && r.conclusion !== "success" && r.outcome === "item");
  if (attempts.length >= limits.max_attempts) return out(t.HELD, "attempts_exhausted", attempts.map((r) => r.run), t.HOLD);
  if (intent === "adjudicate-findings") {
    const rounds = recent.filter((r) => r.intent === intent && r.status === "completed");
    if (rounds.length >= limits.max_rounds) return out(t.HELD, "max_rounds", d.evidence, t.HOLD);
  }
  if (recent.length >= limits.max_runs_per_item) return out(t.HELD, "run_ceiling", [], t.HOLD);

  if (!("model_deferred_until" in context)) return out(state, "capacity_unreadable", d.evidence, t.DEFER);
  const until = context.model_deferred_until;
  if (until != null && until > now) return out(state, "capacity", d.evidence, t.DEFER);
  if (context.active_runs == null) return out(state, "capacity_unreadable", d.evidence, t.DEFER);
  if (context.active_runs >= limits.org_max_active_runs) return out(state, "concurrency", d.evidence, t.DEFER);

  return out(state, d.reason, d.evidence, t.ADMIT, { admit: { role, intent, content_id: facts.content_id } });
}
