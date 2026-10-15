"""Enumerated codes used in facts and decisions. A code is never a sentence."""
from __future__ import annotations

# Lifecycle states of a pull request (lifecycle/pull_request.json declares them).
DRAFT = "draft"
VERIFYING = "verifying"
ADDRESSING = "addressing"
ADJUDICATING = "adjudicating"
CONVERGED = "converged"
QUEUED = "queued"
HELD = "held"
MERGED = "merged"
CLOSED = "closed"
NOT_SERVED = "not_served"

TERMINAL = frozenset({MERGED, CLOSED, NOT_SERVED})

# Decision outcomes.
NOTHING = "nothing"
DEFER = "defer"
HOLD = "hold"
ACT = "act"      # a change the Harness makes with no model Run
ADMIT = "admit"  # start one Run

# Attention classes, in the order the control room lists them.
NEEDS_YOU = "needs_you"
FAILED = "failed"
REVIEW = "review"
READY = "ready"
WORKING = "working"
NONE = "none"

GATING_SEVERITIES = frozenset({"blocking", "major"})

# What the facts say was read in full: the flags `complete` requires in schemas/facts.schema.json.
READ_IN_FULL = ("checks", "diff", "reviews", "runs", "threads")

# Labels: the human's input vocabulary.
LABEL_HOLD = "factory:hold"
LABEL_HANDS_OFF = "factory:hands-off"
LABEL_ADMIT = "factory:admit"
