"""The one snapshot of a pull request: every part of `facts/1`, each from its own read, put together and held to the
schema, with the title handed beside it (design section 3.3, decision 0039).

The pull request is read first and once more last (`adapters/pull.unchanged`): a push, a retarget, or any change
GitHub records on it between makes the parts of two pull requests, and the snapshot is refused, to be read again at the
next pass. The diff and the files are read by one compare pinned to the first read's head commit (issue 284), so a head
pushed away and back between the two reads still gives the parts of that commit. A part that cannot be read
refuses the whole; a list that was not read whole says so in its `complete` flag, and the Kernel defers on it.

One part is not read yet, and says so: `acceptance` is null, and whole only where no issue the pull request closes
asks for a contract (`adapters/acceptance.py`); the contract itself waits on `adapters/contract.py`. A Lens's thread has
no category or severity until `harness/` uploads the Finding records they are joined from (`adapters/threads.py`). The
run records are the records port's, read
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

from adapters import acceptance, checks, pull, threads, timeline
from adapters.github import Unanswered
from tools.jsonschema_lite import validate


class Moved(Unanswered):
    """The pull request changed while it was read: its head, its base or anything else GitHub moves `updated_at` for.
    A kind of `Unanswered`, so a pass reads it again at the next one, and the approving act can tell it apart and class
    it `superseded` without reading any text (issue 195, ruling 4)."""

SCHEMA = json.loads((pathlib.Path(__file__).resolve().parent.parent / "schemas" / "facts.schema.json").read_text())


def _utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot(transport, repo: str, number: int, identities: dict, accounts: timeline.Accounts, runs_whole: bool,
             clock=_utc, kept=None, with_head: bool = False, opener=None) -> tuple:
    """`(facts/1, title)` for one pull request, or `(facts/1, title, head)` `with_head`: the head commit its first read
    gave, which the snapshot is held to, beside the facts and never in them (#193's ruling 10). `identities` gives the class's accounts (`adapters/pull.own`),
    `accounts` who acted, `runs_whole` whether the pass read the run records whole, and `clock` the time after the last
    read. `kept`, where given, is filled with what GitHub gave the timeline, reviews, threads and check runs reads,
    each with whether it was whole, once the snapshot is whole: reconciliation reads them, so no read is made twice
    (`adapters/seen.py`, decision 0061)."""
    raw = {}
    first = pull.read(transport, repo, number)
    own, title = pull.own(first, identities)
    branch = pull.base(transport, first)
    pusher, pushed_at = pull.last_push(transport, first)
    content = pull.diff(transport, first, branch["head"])
    paths = pull.changed_paths(transport, first, branch["head"])
    events, timeline_whole = timeline.events(transport, first)
    raw["events"] = (events, timeline_whole)
    reviews, reviews_whole = timeline.reviews(transport, first, events, accounts, branch["head"], raw)
    writer = timeline.since_writer(events, accounts)
    labels = timeline.label_events(events, accounts)
    read = checks.read(transport, first, raw)
    contract, contract_whole = acceptance.read(transport, first, accounts, opener)
    found, threads_whole = threads.read(transport, first, accounts, raw)
    if pusher is not None and pushed_at is None:
        raise Unanswered("the head's push names its pusher but no time that can be read")
    if not pull.unchanged(transport, first):
        raise Moved("the pull request changed while it was read; it is read again at the next pass")
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
        "threads": found,
        "checks": read["checks"],
        "queue": read["queue"],
        "acts_since_writer": writer["acts_since_writer"],
        "acceptance": contract,
        "complete": {"acceptance": contract_whole, "reviews": reviews_whole, "threads": threads_whole,
                     "checks": read["complete"], "diff": content["complete"],
                     "changed_paths": paths["complete"], "runs": runs_whole is True, "timeline": timeline_whole},
        "read_at": now,
    })
    problems = validate(facts, SCHEMA)
    if problems:
        raise Unanswered("the snapshot does not hold to facts/1: %s" % problems[0])
    if kept is not None:
        kept.update(raw)
    return (facts, title, str(first["head"]["sha"])) if with_head else (facts, title)


def accounts_of(controller: dict) -> tuple:
    """`(identities, approver, lenses, factory)`, each account by its id and type as `controller/1` holds it: the
    class's accounts for `adapters/pull.own`, and who acted for `adapters/timeline.Accounts`."""
    held = controller["accounts"]
    bots = lambda entries: {(a["id"], "Bot") for a in entries}
    maintainer = {(held["maintainer"]["id"], "User")} if held["maintainer"] else set()
    identities = {"agent": bots(held["agents"]), "maintainer": maintainer, "dependency": bots(held["dependencies"])}
    approver = (held["approver"]["id"], "User") if held["approver"] else (0, "User")
    lenses = {(a["id"], "Bot"): a["lens"] for a in held["lenses"]}
    factory = bots(held["agents"]) | set(lenses) | ({(held["controller"]["id"], "Bot")} if held["controller"] else set())
    return identities, approver, lenses, factory


def opener_of(controller: dict, kernel: dict, apps: dict):
    """The bot account, `(id, "Bot")`, of the App that opens the Factory's pull requests: the App, in config/apps.json, of
    the Role the configuration names for `open-pull-request`, as `controller/1` holds its account. None where no Role
    opens one, so no pull request is bound to an issue by its branch (slice 1); `acceptance.UNTOLD` where one does but
    its App or its account cannot be told (issue 295)."""
    intent = kernel["issues"]["intents"]["open-pull-request"]
    if intent is None:
        return None
    app = apps.get(intent["role"]) if isinstance(apps.get(intent["role"]), dict) else {}
    account = controller["accounts"]["roles"].get(intent["role"])
    if not app.get("name") or app["name"] != intent["app"] or not isinstance(account, dict) \
            or account.get("login") != app["name"] + "[bot]":
        return acceptance.UNTOLD
    return account["id"], "Bot"


def dispatcher_of(controller: dict) -> tuple:
    """The pass's token's account, by id and type, which alone dispatches a Run; with none held, no account GitHub gives,
    id 0, so that no run is a Run."""
    token = controller["accounts"]["workflow_token"]
    return (token["id"], token["type"]) if token else (0, "Bot")
