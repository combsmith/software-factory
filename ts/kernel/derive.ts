// Derive the State of a pull request from facts and run records. State is never stored.
import * as t from "./terms.ts";
import type { Config, Derived, Facts, Run, Thread } from "./terms.ts";

const same = (a: t.Item, b: t.Item) => a.repo === b.repo && a.type === b.type && a.number === b.number;

export const incomplete = (facts: Facts): string[] =>
  Object.entries(facts.complete).filter(([, whole]) => !whole).map(([k]) => k).sort();

export const runsOn = (runs: Run[], facts: Facts): Run[] =>
  runs.filter((r) => same(r.item, facts.item))
    .map((r, i) => ({ r, i })).sort((a, b) => (a.r.started_at < b.r.started_at ? -1 : a.r.started_at > b.r.started_at ? 1 : a.i - b.i))
    .map((x) => x.r);

export const sinceWriter = (runs: Run[], facts: Facts): Run[] =>
  facts.last_writer_action_at === null ? runs : runs.filter((r) => r.started_at > (facts.last_writer_action_at as string));

/** Runs that hold the item: started, or admitted and still waiting for a runner. */
export const inProgress = (runs: Run[]): Run[] => runs.filter((r) => r.status !== "completed");

const reviewed = (runs: Run[], facts: Facts, role: string): boolean =>
  runs.some((r) => r.role === role && r.intent === "review-change" && r.content_id === facts.content_id
    && r.status === "completed" && r.conclusion === "success");

/** A person with write access always gates. A Lens gates only if required and blocking or major. */
export function gatingThreads(facts: Facts, config: Config): Thread[] {
  const required = new Set(config.required_lenses.model);
  return facts.threads.filter((th) => {
    if (th.resolved) return false;
    const by = th.opened_by;
    if (by.kind === "human") return by.can_write;
    return required.has(by.name) && t.GATING_SEVERITIES.has(th.severity);
  });
}

/** Who must act on an open gating thread. The author's answer may be new content. */
export function whoseTurn(thread: Thread, runs: Run[], config: Config): "author" | "owner" | "human" {
  const answers = runs.filter((r) => r.role === config.author_role && r.status === "completed"
    && r.conclusion === "success" && r.started_at > thread.opened_at).map((r) => r.started_at);
  if (answers.length === 0) return "author";
  if (thread.opened_by.kind === "human") return "human";
  const last = answers.reduce((a, b) => (a > b ? a : b));
  const ruled = runs.some((r) => r.intent === "adjudicate-findings" && r.status === "completed"
    && r.conclusion === "success" && r.started_at > last);
  return ruled ? "author" : "owner";
}

function admitted(facts: Facts): boolean {
  if (facts.class !== "outside") return true;
  if (!facts.labels.includes(t.LABEL_ADMIT) || facts.admitted_at === null) return false;
  return facts.admitted_at > facts.last_push_at;
}

export const standingApproval = (facts: Facts, config: Config) =>
  facts.reviews.find((rv) => rv.actor === config.approver && rv.state === "approved" && rv.content_id === facts.content_id) ?? null;

export function derive(facts: Facts, runs: Run[], config: Config): Derived {
  const gaps = incomplete(facts);
  if (gaps.length) return { state: null, reason: "facts_incomplete", evidence: gaps };
  const is = (state: string, reason: string, evidence: string[] = []): Derived => ({ state, reason, evidence });

  if (facts.state === "merged") return is(t.MERGED, "merged");
  if (facts.state === "closed") return is(t.CLOSED, "closed");
  if (!facts.targets_protected) return is(t.NOT_SERVED, "base_not_protected");
  if (facts.is_draft) return is(t.DRAFT, "draft");
  if (facts.labels.includes(t.LABEL_HANDS_OFF)) return is(t.HELD, "hands_off", [t.LABEL_HANDS_OFF]);
  if (facts.labels.includes(t.LABEL_HOLD)) return is(t.HELD, "human_hold", [t.LABEL_HOLD]);
  if (!admitted(facts)) return is(t.HELD, "outside_not_admitted");
  if (facts.diff.files === 0) return is(t.HELD, "empty_diff");
  if (facts.diff.truncated || facts.diff.lines > config.limits.max_diff_lines) return is(t.HELD, "too_large");
  if (facts.queue) return is(t.QUEUED, "in_merge_queue");
  if (facts.mergeable === false) return is(t.ADDRESSING, "conflict");

  const byLens = new Map(facts.checks.map((c) => [c.lens, c]));
  const failed: string[] = [], waiting: string[] = [];
  for (const lens of config.required_lenses.deterministic) {
    const check = byLens.get(lens);
    if (check === undefined || check.conclusion === "pending") waiting.push(lens);
    else if (check.conclusion !== "success") failed.push(lens);
  }
  if (failed.length) return is(t.ADDRESSING, "check_failed", failed);
  if (waiting.length) return is(t.VERIFYING, "awaiting_checks", waiting);

  const mine = runsOn(runs, facts);
  for (const lens of config.required_lenses.model) {
    if (!reviewed(mine, facts, lens)) return is(t.VERIFYING, "awaiting_review", [lens]);
  }

  const open = gatingThreads(facts, config);
  if (open.length) {
    const turns = open.map((th) => ({ th, who: whoseTurn(th, mine, config) }));
    const forAuthor = turns.filter((x) => x.who === "author");
    const forOwner = turns.filter((x) => x.who === "owner");
    if (forAuthor.length) {
      const human = forAuthor.some((x) => x.th.opened_by.kind === "human");
      return is(t.ADDRESSING, human ? "human_finding" : "findings_open", forAuthor.map((x) => x.th.id));
    }
    if (forOwner.length) return is(t.ADJUDICATING, "proposals_await_owner", forOwner.map((x) => x.th.id));
    return is(t.ADDRESSING, "awaiting_human", turns.map((x) => x.th.id).sort());
  }

  const approval = standingApproval(facts, config);
  return approval ? is(t.CONVERGED, "approved", [approval.commit]) : is(t.CONVERGED, "approval_due");
}
