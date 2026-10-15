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

# The Intent of the Run with no Engine that issues an approval: only its `apply` holds the machine user's token.
ISSUE_APPROVAL = "issue-approval"

# Attention classes, in the order the control room lists them.
NEEDS_YOU = "needs_you"
FAILED = "failed"
REVIEW = "review"
READY = "ready"
WORKING = "working"
NONE = "none"

GATING_SEVERITIES = frozenset({"blocking", "major"})
# The reasons an open gate gives, whoever's turn it is. On a queued item each is the one reason `gate_open`.
GATE_REASONS = ("human_finding", "findings_open", "awaiting_human", "proposals_await_owner")
# The waits that end on their own, and that a queued item is read past: they never take it out of the merge queue.
QUEUE_WAITS = ("mergeable_unreadable", "awaiting_checks", "awaiting_review")

# Who opened a thread or submitted a review, and the states of a review: schemas/facts.schema.json names them too.
ACTOR_KINDS = ("human", "lens")
REVIEW_STATES = ("approved", "changes_requested", "commented", "dismissed")
# What a dismissed review was before, as the timeline records it.
DISMISSED_FROM = ("approved", "changes_requested", "commented")
# Classes of pull request whose author is a bot: an agent's, or a dependency update's.
BOT_CLASSES = ("agent", "dependency")

# The one text format of a time, YYYY-MM-DDTHH:MM:SSZ, with 9 for any digit. Times compare as text.
TIME_SHAPE = "9999-99-99T99:99:99Z"
DIGITS = "0123456789"

# What the facts say was read in full: the flags `complete` requires in schemas/facts.schema.json.
READ_IN_FULL = ("checks", "diff", "reviews", "runs", "threads", "timeline")

# Labels: the human's input vocabulary.
LABEL_HOLD = "factory:hold"
LABEL_HANDS_OFF = "factory:hands-off"
LABEL_ADMIT = "factory:admit"
