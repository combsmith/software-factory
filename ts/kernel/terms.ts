// Enumerated codes used in facts and decisions. A code is never a sentence.
export const DRAFT = "draft", VERIFYING = "verifying", ADDRESSING = "addressing",
  ADJUDICATING = "adjudicating", CONVERGED = "converged", QUEUED = "queued", HELD = "held",
  MERGED = "merged", CLOSED = "closed", NOT_SERVED = "not_served";
export const TERMINAL: ReadonlySet<string> = new Set([MERGED, CLOSED, NOT_SERVED]);

export const NOTHING = "nothing", DEFER = "defer", HOLD = "hold", ACT = "act", ADMIT = "admit";
export const NEEDS_YOU = "needs_you", FAILED = "failed", REVIEW = "review", READY = "ready",
  WORKING = "working", NONE = "none";
export const GATING_SEVERITIES: ReadonlySet<string | null> = new Set(["blocking", "major"]);
export const LABEL_HOLD = "factory:hold", LABEL_HANDS_OFF = "factory:hands-off", LABEL_ADMIT = "factory:admit";

export type Item = { repo: string; type: string; number: number };
export type Thread = {
  id: string; resolved: boolean; opened_at: string; severity: string | null; resolved_by: string | null;
  opened_by: { kind: "human" | "lens"; name: string; can_write: boolean };
};
export type Facts = {
  schema: string; item: Item; state: "open" | "closed" | "merged"; is_draft: boolean; class: string;
  author: string; last_pusher: string; targets_protected: boolean; mergeable: boolean | null;
  content_id: string; diff: { files: number; lines: number; truncated: boolean }; labels: string[];
  admitted_at: string | null; last_push_at: string; last_writer_action_at: string | null;
  reviews: { actor: string; state: string; commit: string; content_id: string }[];
  threads: Thread[]; checks: { lens: string; conclusion: string }[]; queue: boolean;
  complete: Record<string, boolean>; read_at: string;
};
export type Run = {
  run: string; item: Item; role: string; intent: string; content_id: string;
  status: "queued" | "in_progress" | "completed"; conclusion: string | null; outcome: string | null; started_at: string;
};
export type Config = {
  approver: string; author_role: string | null; owner_role: string;
  required_lenses: { deterministic: string[]; model: string[] };
  limits: { max_attempts: number; max_rounds: number; max_runs_per_item: number; org_max_active_runs: number; max_diff_lines: number };
};
export type Context = { paused?: boolean; active_runs?: number | null; model_deferred_until?: string | null };
export type Derived = { state: string | null; reason: string; evidence: string[] };
export type Decision = Derived & {
  schema: string; item: Item; attention: string; outcome: string;
  action?: string; content_id?: string; admit?: { role: string; intent: string; content_id: string };
};
