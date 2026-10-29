"""The `run` job's first step: what the Task is built from, read with the reader App's key, before the model's step
(#196's ruling 7, the Maintainer's answer (b); design section 3.5).

    python3 -m harness.read NAME ITEM PASS OUT

NAME is the Run's run-name, ITEM its pull request as `owner/repo#number`, PASS the id of the pass record that holds its
Decision: the three inputs the pass dispatched it with. The step mints the reader App's token, from `READER_APP_KEY`,
for the home repo with the reads its grant allows and no write; finds the pass record by PASS among the poller's runs;
finds in it the Decision of the Run id the run-name names, which must be of the item and the content the run-name names;
reads the pull request's facts, its threads held to what its Lenses recorded, and the bytes of its diff, which must be the content the Decision admitted; and writes,
into the new folder OUT, the record, the Run id, the facts, the diff, the texts, the Role's manifest and the Findings,
for `python3 -m harness.run OUT RESULT`. The token is revoked before the step ends, whatever happened, and a token
GitHub did not revoke fails the step, so the model's step never starts beside a live reader token.

Before anything else is read, the Run's own Release is named: the one Release tag, among the `factory/` tags read with
that token, on the commit the job checked out, `steps.commit()`, the one the job hands on (#197's rulings 8 and 11). A
Run whose own Release is not its pass record's builds no Task: OUT holds its `outcome/1` alone, `superseded`,
`release_moved`, and the step stops by that code. One whose own Release cannot be named stops `release_unresolved` and
writes nothing; the pass record's Release is never taken for it; a checkout `steps.commit()` cannot read stops
`release_unreadable`, before any key is read. Not read yet, by the stories that hold them: the texts
(`adapters/texts.py`), so the Task carries the diff alone; the Finding records a Decision names (`harness/apply.py`
writes them, and `adapters/applied.py` reads them for the threads alone), so the review Intent, which names none, is
the one a Run can carry; an issue's Run, whose reads are the issue Lifecycle's."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time

from adapters import applied, facts as facts_, identity, passes, pull, records, tags, timeline
from adapters.github import Live, Unanswered
from controller import configuration
from harness import approve, shared, steps, task
from harness.steps import Stop
from release import current, cut

APP = "reader"
KEY = "READER_APP_KEY"
ITEM = re.compile(r"([A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100})#([1-9][0-9]{0,8})")
FILES = ("record.json", "run", "facts.json", "diff", "texts.json", "role.json", "findings.json")


class ReleaseMoved(Stop):
    """The Run's own Release is not its pass record's: it builds no Task, and ends `superseded`."""

    def __init__(self, release: str):
        super().__init__("release_moved")
        self.release = release


def own_release(transport, home: str, commit) -> str:
    """The Release the job runs: the one Release tag on the commit it checked out; Stop `release_unresolved` when the
    commit is not a full sha, the tags cannot be read whole, or no one Release names it."""
    refs = tags.read(transport, home) if cut.sha(commit) else None      # a cheap guard: `resolve` refuses it too
    found = current.resolve(commit, refs) if refs is not None else None
    if found is None:
        raise Stop("release_unresolved")
    return found


def wanted(config: dict) -> dict:
    """Every read the reader App is granted, and no write."""
    names = [n for grant in config["app"]["permissions"].values() for n in grant["needs"] if n.startswith("read:")]
    return identity.granted(config["app"], config["needs"], names, "read")


def asked(name: str, item: str, pass_id: str, home: str) -> dict:
    """The run-name read, held to the item and the home repo it was dispatched with; Stop otherwise."""
    parts = records.named(name)
    if parts is None:
        raise Stop("run_name_unreadable")
    found = ITEM.fullmatch(item) if isinstance(item, str) else None
    if not found or (found.group(1), int(found.group(2))) != (parts["item"]["repo"], parts["item"]["number"]):
        raise Stop("item_not_the_run_names")
    if parts["item"]["repo"] != home:
        raise Stop("item_not_home")
    if parts["item"]["type"] != "pull_request":
        raise Stop("issue_not_built")
    if not isinstance(pass_id, str) or not passes.PASS_ID.fullmatch(pass_id):
        raise Stop("pass_unreadable")
    return parts


def decided(record, parts: dict, owner_role: str) -> dict:
    """The Decision the run-name names in `record`: an admission of the run-name's item, Intent, Role and content, or
    an act issuing the approval of its item and content under the owner Role; Stop `not_the_decision` otherwise. A Run
    dispatched by hand with another Run's id finds none. A record that is no `pass/1` is `record_unreadable`."""
    if shared.errors(record, "pass"):
        raise Stop("record_unreadable")
    if parts["intent"] == approve.APPROVAL:
        act = approve.decision_of(record, parts["run"])
        if act is None or act["item"] != parts["item"] or act["content_id"] != parts["content_id"] \
                or parts["role"] != owner_role:
            raise Stop("not_the_decision")
        return act
    entry = task.decision_of(record, parts["run"])
    admit = entry["decision"].get("admit") if entry else None
    if admit is None or entry["decision"]["item"] != parts["item"] or \
            (admit["intent"], admit["role"], admit["content_id"]) != (parts["intent"], parts["role"], parts["content_id"]):
        raise Stop("not_the_decision")
    return admit


def reads(transport, config: dict, parts: dict, pass_id: str, clock, commit=None) -> dict:
    """Each file the step writes, by its name, read through `transport`."""
    controller = config["controller"]
    home, branch = controller["home"]["repo"], controller["home"]["branch"]
    own = own_release(transport, home, commit)
    record = passes.find(transport, home, branch, controller["workflows"]["poller"], pass_id)
    if record is None:
        raise Stop("record_not_found")
    admit = decided(record, parts, config["kernel"]["owner_role"])
    # Once the record holds this Run's Decision, so that no outcome is left for a Run id it does not hold: a pass of
    # another Release than the Run's own builds no Task. Nothing of the Decision has been used yet.
    if record["release"] != own:
        raise ReleaseMoved(own)
    if "intent" not in admit:
        raise Stop("not_the_decision")       # an approval is the approving act's, and runs no Task
    identities, approver, lenses, factory = facts_.accounts_of(controller)
    who = timeline.Accounts(transport, home, approver, lenses, factory, facts_.queue_of(controller))
    number = parts["item"]["number"]
    # The threads are held to what the item's Lenses recorded, read from their Runs (adapters/applied.py, issue 338).
    listed = records.runs(transport, home, branch, [controller["workflows"]["run"], controller["workflows"]["approval"]],
                          facts_.dispatcher_of(controller))
    found = applied.recorded(transport, home, listed, [number], set(config["kernel"]["required_lenses"]["model"]),
                             config["authority"])
    facts, _, head = facts_.snapshot(transport, home, number, identities, who, True, clock, with_head=True,
                                     opener=facts_.opener_of(controller, config["kernel"], config["apps"]),
                                     recorded=found[number])
    first = pull.read(transport, home, number)
    if str(first["head"]["sha"]) != head:
        raise Stop("head_moved")
    change = pull.change(transport, first, pull.base(transport, first)["head"])
    if "sha256:" + hashlib.sha256(change).hexdigest() != admit["content_id"]:
        raise Stop("content_moved")
    role = steps.read_json(steps.ROOT, os.path.join("roles", "%s.json" % admit["role"]))
    return {"record.json": record, "run": (parts["run"] + "\n").encode(), "facts.json": facts, "diff": change,
            "texts.json": [], "role.json": role, "findings.json": []}


def step(argv: list, environ: dict, base, clock=time.time, connect=Live) -> str:
    argv = steps.given(argv, environ, steps.INPUTS, ("task",))
    if len(argv) != 4:
        raise Stop("usage: python3 -m harness.read NAME ITEM PASS OUT")
    name, item, pass_id, out = argv
    config = configuration.load(steps.ROOT, None, APP)
    parts = asked(name, item, pass_id, config["controller"]["home"]["repo"])
    folder = steps.new_folder(base, out)
    commit = steps.commit()     # the commit this job checked out and hands on, read before any key is
    try:
        transport, revoke = identity.from_key(config["app"], config["controller"]["home"]["repo"], wanted(config),
                                              environ.get(KEY), int(clock()), connect)
    except identity.Refused as err:
        raise Stop(str(err)) from None
    utc = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(clock())))
    try:
        found = reads(transport, config, parts, pass_id, utc, commit)
    except BaseException as err:
        # The token is revoked whatever stopped the reads, and one GitHub did not revoke is the step's one code.
        if revoke() is not True:
            raise Stop("token_not_revoked") from None
        if isinstance(err, Unanswered):
            raise Stop("facts_unreadable") from None
        if isinstance(err, ReleaseMoved):
            # No Task: the Run's outcome alone, under its own Release, for the job's last step to carry.
            steps.write(folder, "outcome.json", {"schema": "outcome/1", "run": parts["run"], "release": err.release,
                                                 "outcome": "superseded", "reason": "release_moved"})
        raise
    if revoke() is not True:
        raise Stop("token_not_revoked")
    for name_ in FILES:
        steps.write(folder, name_, found[name_])
    return "read %d files for run %s" % (len(FILES), parts["run"])


if __name__ == "__main__":
    steps.exit_with(step, sys.argv[1:], dict(os.environ), os.getcwd())
