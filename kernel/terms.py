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
STALE = "stale"
NONE = "none"
# The classes a wait past its State's limit turns stale. A person is already called to `needs_you`, and a Run holds
# a `working` item, so neither ever is.
MAY_GO_STALE = frozenset({REVIEW, READY})
# Deferrals that hold the whole scope, each one cause that health reports once (§4.6), so an item they defer is never
# stale: a Pause, read or not, the model provider's deferral (`capacity`), capacity unread, and the org's limit on Runs.
SCOPE_DEFERRALS = frozenset({"paused", "pause_unreadable", "capacity", "capacity_unreadable", "concurrency"})

GATING_SEVERITIES = frozenset({"blocking", "major"})
# A Finding of this category gates at any severity: severity is never how a security defect gets merged (FR-33).
SECURITY = "security"
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
# The calendar, which nobody chooses: the only numbers but 0 and 1 the Kernel writes. tools/check_purity.py pins each.
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365
# A year divisible by the first is a leap year, unless by the second, unless by the third.
LEAP_YEARS = (4, 100, 400)
# The days of a year that is not a leap year before each month begins, and the month a leap day ends.
DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
FEBRUARY = 2

# What the facts say was read in full: the flags `complete` requires in schemas/facts.schema.json.
READ_IN_FULL = ("checks", "diff", "reviews", "runs", "threads", "timeline")

# Labels: the human's input vocabulary.
LABEL_HOLD = "factory:hold"
LABEL_HANDS_OFF = "factory:hands-off"
LABEL_ADMIT = "factory:admit"
