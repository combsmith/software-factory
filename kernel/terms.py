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

# The States that admit nothing: no Run, and no act, not even a dequeue. The Factory leaves the item alone. Merged
# and closed end the Lifecycle; not served does not, as GitHub serves the item again when it retargets it. The
# Lifecycle's `terminal` names the ends.
ADMITS_NOTHING = frozenset({MERGED, CLOSED, NOT_SERVED})

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
# stale: a Pause, read or not, the model provider's deferral (`capacity`), capacity unread, the org's limit on Runs, and
# a Run listed before its run-name, which may be on any item (decision 0036).
SCOPE_DEFERRALS = frozenset({"paused", "pause_unreadable", "capacity", "capacity_unreadable", "concurrency",
                             "run_unidentified"})

# A Finding's categories, as the authority table names them, and its severities: schemas/facts.schema.json names
# them too, and a thread from a required Lens with any other, or none, cannot be read.
CATEGORIES = ("functional", "security", "architecture", "delivery", "reliability", "requirements", "mechanical",
              "uncategorised", "human")
SEVERITIES = ("blocking", "major", "minor", "info")
# The reasons an open gate gives, whoever's turn it is. On a queued item each is the one reason `gate_open`.
GATE_REASONS = ("human_finding", "findings_open", "awaiting_human", "proposals_await_owner")
# The waits that end on their own, and that a queued item is read past: they never take it out of the merge queue.
QUEUE_WAITS = ("mergeable_unreadable", "awaiting_checks", "awaiting_review")

# The kinds of actor, and the states of a review: schemas/facts.schema.json names them too. The port tells them apart
# from GitHub's account type and the configuration, never from a name's spelling: a person (`human`), the App of a
# Lens (`lens`), any other App (`app`), and the machine user, the approver the configuration names (`machine_user`).
ACTOR_KINDS = ("human", "lens", "app", "machine_user")
MACHINE_USER = "machine_user"
APP = "app"
# How GitHub ends the login of an App's bot account. No User's login can: it only ever refuses a person.
BOT_SUFFIX = "[bot]"
REVIEW_STATES = ("approved", "changes_requested", "commented", "dismissed")
# What a dismissed review was before, as the timeline records it.
DISMISSED_FROM = ("approved", "changes_requested", "commented")
# What one result for a criterion of an acceptance contract says: schemas/facts.schema.json names them too. Any other
# word, or none, cannot be read.
EVIDENCE_RESULTS = ("passing", "failing")
# The kinds of a criterion's check, as schemas/acceptance.schema.json names them, and the one only a person passes, by
# an approving review of the content: no check reports it. Any other word, or none, cannot be read.
CRITERION_KINDS = ("test", "scenario", "mutation", "static", "role", "human")
HUMAN_KIND = "human"
# The forms of a criterion's id and of a content id, as schemas/facts.schema.json gives them: a prefix, then digits.
CRITERION_PREFIX = "AC-"
CONTENT_PREFIX = "sha256:"
HEX_DIGITS = "0123456789abcdef"
# The one form of an acceptance contract's digest: the prefix, then a whole SHA-256 in lower-case hexadecimal, one
# character for each digit. Shorter or longer, it is no digest (schemas/facts.schema.json).
DIGEST_SHAPE = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
# The one form in which a Decision's evidence shows a workflow file's path, the form a Lens's workflow takes in
# schemas/config.schema.json: this directory, a name of these characters alone, and one of these endings.
WORKFLOW_DIR = ".github/workflows/"
WORKFLOW_ENDINGS = (".yml", ".yaml")
FILE_NAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
# Classes of pull request whose author is an App: an agent's, or a dependency update's.
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
READ_IN_FULL = ("acceptance", "changed_paths", "checks", "diff", "reviews", "runs", "threads", "timeline")

# A path the pull request changes, and a protected path or Lens's input in config/hooks.json, are names joined by this.
# In a pattern, the wildcard stands for any part of one name, two as a whole name for any run of names, none included,
# and a final separator for everything below it. A name that is one of these cannot be read: it would make a path
# empty, start or end it with the separator, or climb.
SEPARATOR = "/"
WILDCARD = "*"
ANY_NAMES = "**"
NOT_A_NAME = ("", ".", "..")

# What a reviewing Result says of each criterion of its rubric that applies (schemas/coverage.schema.json): met, a
# Finding that cites it, or not applicable with a reason that is a code. A criterion's id is capital letters, a hyphen
# and digits, as schemas/rubric.schema.json gives it, and a code is lower-case letters and underscores.
VERDICTS = ("met", "finding", "not_applicable")
FINDING = "finding"
NOT_APPLICABLE = "not_applicable"
CAPITALS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
HYPHEN = "-"
CODE_CHARS = "abcdefghijklmnopqrstuvwxyz_"

# Labels: the human's input vocabulary.
LABEL_HOLD = "factory:hold"
LABEL_HANDS_OFF = "factory:hands-off"
LABEL_ADMIT = "factory:admit"
# The labels the Kernel reads on a pull request, and what the timeline records was done to one.
CONTROL_LABELS = ("factory:hold", "factory:hands-off", "factory:admit")
LABEL_ACTIONS = ("labeled", "unlabeled")
# The label a person adds to an issue to ask for an acceptance contract (decision 0047): the facts port reads it from the
# issue a pull request closes, as the Kernel reads a control label. No Lifecycle runs an Intent that asks yet.
LABEL_CONTRACT = "factory:contract"
