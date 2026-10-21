"""The one snapshot of a pull request: every part of `facts/1`, each from its own read, put together and held to the
schema, with the title handed beside it (design section 3.3, decision 0039).

The pull request is read first and once more last (`adapters/pull.same_head`): a push or a retarget between makes the
parts of two pull requests, and the snapshot is refused, to be read again at the next pass. A head pushed away and back
between the two reads is not seen: the diff and the files are the pull request's, not pinned to its head commit, so they
may be of the commit between (the known limit; pinning them is still to be built). A part that cannot be read
refuses the whole; a list that was not read whole says so in its `complete` flag, and the Kernel defers on it.

Two parts are not read yet, and say so: a thread's state and its Finding's category wait on `adapters/threads.py`, so
`threads` is whole only when the pull request holds none; and the acceptance contract waits on
`adapters/acceptance.py`, so `acceptance` is null and never read whole. The run records are the records port's, read
once a pass: the caller says whether that read was whole.

`read_at` is taken after the last read, never given by the caller. `last_push_at` is the push's own time where the head
branch's activity names the head, and `read_at` where it does not, so that an admission placed before the read never
reads as after a push it could not see. The known cost: a fork's head, which the base's activity never names, and a
push the activity has not listed yet, read as pushed at each pass, so a wait measured from the push starts again each
pass until GitHub names it.
"""
from __future__ import annotations

import datetime
import json
import pathlib

from adapters import checks, pull, timeline
from adapters.github import Unanswered
from tools.jsonschema_lite import validate

SCHEMA = json.loads((pathlib.Path(__file__).resolve().parent.parent / "schemas" / "facts.schema.json").read_text())


def _utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot(transport, repo: str, number: int, identities: dict, accounts: timeline.Accounts, runs_whole: bool,
             clock=_utc) -> tuple:
    """`(facts/1, title)` for one pull request. `identities` gives the class's accounts (`adapters/pull.own`),
    `accounts` who acted, `runs_whole` whether the pass read the run records whole, and `clock` the time after the last
    read."""
    first = pull.read(transport, repo, number)
    own, title = pull.own(first, identities)
    branch = pull.base(transport, first)
    pusher, pushed_at = pull.last_push(transport, first)
    content = pull.diff(transport, first)
    paths = pull.changed_paths(transport, first)
    events, timeline_whole = timeline.events(transport, first)
    reviews, reviews_whole = timeline.reviews(transport, first, events, accounts, branch["head"])
    writer = timeline.since_writer(events, accounts)
    labels = timeline.label_events(events, accounts)
    read = checks.read(transport, first)
    if not pull.same_head(transport, first):
        raise Unanswered("the pull request moved while it was read; it is read again at the next pass")
    now = clock()
    facts = dict(own)
    facts.update({
        "schema": "facts/1",
        "last_pusher": pusher,
        "targets_protected": branch["protected"],
        "content_id": content["content_id"],
        "diff": content["diff"],
        "changed_paths": paths["changed_paths"],
        "label_events": labels,
        "last_push_at": pushed_at or now,
        "last_writer_action_at": writer["last_writer_action_at"],
        "reviews": reviews,
        "threads": [],
        "checks": read["checks"],
        "queue": read["queue"],
        "acts_since_writer": writer["acts_since_writer"],
        "acceptance": None,
        "complete": {"acceptance": False, "reviews": reviews_whole, "threads": read["threads"] == 0,
                     "checks": read["complete"], "diff": content["complete"],
                     "changed_paths": paths["complete"], "runs": runs_whole is True, "timeline": timeline_whole},
        "read_at": now,
    })
    problems = validate(facts, SCHEMA)
    if problems:
        raise Unanswered("the snapshot does not hold to facts/1: %s" % problems[0])
    return facts, title
