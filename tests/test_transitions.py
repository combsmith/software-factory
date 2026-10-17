"""Every change of State the Kernel can make, and who makes it, is one its Lifecycle declares (I-12).

The changes are found, not listed. Every change anyone can make to a pull request (a `Move`) is applied to facts for
each State and reason the Kernel can give (`BASES`), and again to everything one change from there. Each change that
moves the Kernel's State is a transition, made by whoever made the change: a person (`human`), a Lens (`lens`), the
Factory's own Run, act or App (`factory`), or GitHub itself and any App no Role owns (`platform`).

How complete it is. `test_every_reason_the_kernel_gives_with_a_state_has_facts` reads every reason that comes with a
State from the Kernel's source and fails until `BASES` reaches each, so a new reason or State cannot go unchecked. The
moves are every kind of change the facts schema can record, by everyone who can make it; the Factory's Runs and acts are
made only when the Kernel asks for them, as the Controller makes them, and `apply` writes nothing to an item that is
held or changed. Two changes deep reaches a change that needs one to set it up. The seeded simulation runs thousands of
changes deep, and `tests/test_simulator.py::test_invariants_hold_under_faults` fails if it makes a transition this does
not find. The comparison runs both ways: a transition the Lifecycle declares and nothing here makes fails too, unless
`UNREACHED` keeps it with the reason. What it cannot reach: a sequence that needs three changes to set up, which no base
starts nearer to and the seeds miss; a Pause, capacity or concurrency, which keep the State and change only the outcome;
and what no move makes: a rebase that changes the diff's size, a second check run a Lens's own App reports on unchanged
content (a re-run, which is a person's act), and a push by the machine user, which only approves.
"""
from __future__ import annotations

import ast
import copy
import datetime
import json
import marshal
import unittest

from kernel import terms as t
from kernel.decide import decide
from tests.support import (CONFIG, GREEN, MAINTAINER, OTHER_APP, ROOT, context, contract, evidence, facts,
                           labelled, review, run, thread)
from tests.support import changed as a_file
from tools import check_lifecycle
from tools.jsonschema_lite import validate

FACTS_SCHEMA = json.loads((ROOT / "schemas" / "facts.schema.json").read_text())
LIFECYCLE = check_lifecycle.load("pull_request")
LIMITS = CONFIG["limits"]
START = datetime.datetime(2026, 10, 11, 12, 0, 0)
# Facts are made at minutes before this; every change is made after it, a minute apart.
FIRST_MOVE = 30

COLLEAGUE = {"kind": "human", "name": "a-colleague", "can_write": True}
STRANGER = {"kind": "human", "name": "stranger", "can_write": False}
REVIEWER_APP = {"kind": "lens", "name": "pr-review", "can_write": True}
AUTHOR_APP = {"kind": "app", "name": "combsmith-sf-dev-lead[bot]", "can_write": True}
# An App that is neither a Lens's nor a Role's: any App installed with write access.
ANOTHER_APP = {"kind": "app", "name": "another-app[bot]", "can_write": True}
MACHINE = {"kind": "machine_user", "name": CONFIG["approver"], "can_write": True}
AGENT = {"class": "agent", "author": AUTHOR_APP["name"], "last_pusher": AUTHOR_APP["name"]}
DEPENDENCY = {"class": "dependency", "author": "dependabot[bot]", "last_pusher": "dependabot[bot]"}
OUTSIDE = {"class": "outside", "author": "a-stranger", "last_pusher": "a-stranger"}
PENDING = [dict(c, conclusion="queued", completed_at=None) for c in GREEN]
# A dependency bot's pin of an Action, in the workflow file a Lens is read from: a change to a protected path.
PIN = ".github/workflows/verify.yml"


def at(minute: int) -> str:
    return (START + datetime.timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")


def reviewed(content="sha256:aaaa", minute=10, name="r1") -> dict:
    return run(content=content, at=at(minute), name=name)


def fix(minute=20, name="f1", **over) -> dict:
    return run(role=CONFIG["author_role"], intent="fix-findings", at=at(minute), name=name, **over)


def ruling(minute=22, name="o1") -> dict:
    return run(role=CONFIG["owner_role"], intent="adjudicate-findings", at=at(minute), name=name)


def failures(count: int, intent="review-change", outcome="item") -> list:
    return [run(intent=intent, conclusion="failure", outcome=outcome, at=at(11 + i), name="x%d" % i)
            for i in range(count)]


def base(runs=(), **over) -> dict:
    """A pull request as the Kernel reads it: its facts, its Runs, and the minute of its last change."""
    return {"facts": facts(**over), "runs": [copy.deepcopy(r) for r in runs], "minute": FIRST_MOVE}


PERSONS_THREAD = thread(kind="human", name=MAINTAINER["name"], severity=None)
APPROVED = [review()]
# Evidence that every criterion of the default contract passes on the default content.
ACCEPTED = [evidence("AC-1"), evidence("AC-2")]
# Facts for every State and reason the Kernel gives with a State, and for the classes of pull request.
BASES = {
    "awaiting_checks": base(checks=PENDING),
    "awaiting_checks, an agent's": base(checks=PENDING, **AGENT),
    "awaiting_review": base(),
    "awaiting_review, an agent's": base(**AGENT),
    "awaiting_review of the author's answer": base([reviewed(), fix()], content_id="sha256:bbbb", threads=[thread()]),
    "a dependency update awaiting its checks": base(checks=PENDING, **DEPENDENCY),
    "a dependency update, approved": base(reviews=APPROVED, **DEPENDENCY),
    # One that changes a workflow's pin: it waits for the model review, and is queued only once reviewed.
    "a dependency update to a workflow's pin, awaiting its review": base(
        changed_paths=[a_file(PIN), a_file("docs/notes.md")], **DEPENDENCY),
    "a dependency update to a workflow's pin, queued": base(
        [reviewed()], reviews=APPROVED, queue=True, acts_since_writer=2,
        changed_paths=[a_file(PIN), a_file("docs/notes.md")], **DEPENDENCY),
    # A dependency bot's rebase at the act ceiling: held, then rebased, then its last check passes, and held again.
    "a dependency update held at the act ceiling": base(content_id="sha256:bbbb", reviews=APPROVED,
                                                        acts_since_writer=LIMITS["max_acts_per_item"], **DEPENDENCY),
    "a dependency update at the act ceiling, awaiting its last check": base(
        content_id="sha256:bbbb", reviews=APPROVED, acts_since_writer=LIMITS["max_acts_per_item"],
        checks=GREEN[:2] + PENDING[2:], **DEPENDENCY),
    "check_unreadable": base(checks=GREEN[:1] + [dict(GREEN[1], conclusion="neutral")] + GREEN[2:]),
    "check_unreadable from another App": base(checks=GREEN + [dict(GREEN[0], app_id=OTHER_APP)]),
    "check_failed": base(checks=[dict(GREEN[0], conclusion="failure")] + GREEN[1:]),
    "check_failed, with a fix Run": base([fix(status="in_progress")], checks=[dict(GREEN[0], conclusion="failure")]
                                         + GREEN[1:]),
    "conflict": base(mergeable=False),
    "conflict, after a review": base([reviewed()], mergeable=False),
    "conflict, on the owner's turn": base([reviewed(), fix()], threads=[thread()], mergeable=False),
    "findings_open": base([reviewed()], threads=[thread()]),
    "findings_open, an agent's": base([reviewed()], threads=[thread()], **AGENT),
    "findings_open, with a fix Run": base([reviewed(), fix(status="in_progress")], threads=[thread()]),
    "human_finding": base([reviewed()], threads=[PERSONS_THREAD]),
    "human_finding, requested by a colleague": base([reviewed()], reviews=[review("changes_requested", **COLLEAGUE)],
                                                    **AGENT),
    "awaiting_human": base([reviewed(), fix()], threads=[PERSONS_THREAD]),
    "proposals_await_owner": base([reviewed(), fix()], threads=[thread()]),
    "proposals_await_owner, with a ruling Run": base([reviewed(), fix(), dict(ruling(), status="in_progress",
                                                                              conclusion=None)], threads=[thread()]),
    "proposals_await_owner, and a fix Run still running": base(
        [reviewed(), fix(), fix(24, "f2", status="in_progress")], threads=[thread()]),
    "proposals_await_owner, and a person's thread answered": base(
        [reviewed(), fix()], threads=[thread(), dict(PERSONS_THREAD, id="T2")]),
    "approval_due": base([reviewed()]),
    "approval_due, an agent's": base([reviewed()], **AGENT),
    "approved": base([reviewed()], reviews=APPROVED),
    "approved, an agent's": base([reviewed()], reviews=APPROVED, **AGENT),
    "in_merge_queue": base([reviewed()], reviews=APPROVED, queue=True, acts_since_writer=2),
    "in_merge_queue, at the act ceiling": base([reviewed()], reviews=APPROVED, queue=True,
                                               acts_since_writer=LIMITS["max_acts_per_item"]),
    "in_merge_queue, an agent's": base([reviewed()], reviews=APPROVED, queue=True, acts_since_writer=2, **AGENT),
    "approval_lost": base([reviewed()], queue=True, acts_since_writer=2),
    "gate_open": base([reviewed()], reviews=APPROVED, queue=True, acts_since_writer=2, threads=[PERSONS_THREAD]),
    "human_hold": base([reviewed()], label_events=[labelled(t.LABEL_HOLD)]),
    "human_hold, from hands-off an App placed": base([reviewed()], label_events=[labelled(t.LABEL_HANDS_OFF,
                                                                                         AUTHOR_APP)]),
    "hands_off": base([reviewed()], label_events=[labelled(t.LABEL_HANDS_OFF)]),
    "hands_off, queued": base([reviewed()], reviews=APPROVED, queue=True, acts_since_writer=2,
                              label_events=[labelled(t.LABEL_HANDS_OFF)]),
    "outside_not_admitted": base(**OUTSIDE),
    "outside, admitted": base(label_events=[labelled(t.LABEL_ADMIT, at=at(5))], **OUTSIDE),
    "empty_diff": base(diff={"files": 0, "lines": 0, "truncated": False}),
    "too_large": base(diff={"files": 2, "lines": 40, "truncated": True}),
    "approver_is_author_or_last_pusher": base([reviewed()], last_pusher=CONFIG["approver"]),
    "attempts_exhausted": base(failures(LIMITS["max_attempts"]), checks=GREEN),
    "attempts_exhausted, of approvals": base([reviewed()] + failures(LIMITS["max_attempts"], "issue-approval")),
    "run_ceiling": base([reviewed()] + failures(LIMITS["max_runs_per_item"] - 1, outcome="environment"),
                        threads=[thread()]),
    "run_ceiling, one Run short": base([reviewed()] + failures(LIMITS["max_runs_per_item"] - 2, outcome="environment"),
                                       threads=[thread()]),
    "run_ceiling, awaiting checks": base(failures(LIMITS["max_runs_per_item"], outcome="environment"),
                                         checks=PENDING),
    "awaiting_review at the Run ceiling, with a review Run": base(
        failures(LIMITS["max_runs_per_item"] - 1, outcome="environment")
        + [dict(reviewed(minute=25, name="r9"), status="in_progress", conclusion=None)]),
    "proposals_await_owner at the Run ceiling, with a ruling Run": base(
        [reviewed(), fix()] + failures(LIMITS["max_runs_per_item"] - 3, outcome="environment")
        + [dict(ruling(25, "o9"), status="in_progress", conclusion=None)], threads=[thread()]),
    "max_rounds": base([reviewed()] + [r for i in range(LIMITS["max_rounds"])
                                       for r in (fix(20 + 2 * i, "a%d" % i), ruling(21 + 2 * i, "o%d" % i))]
                       + [fix(27, "a9")], threads=[thread()]),
    "act_ceiling": base([reviewed()], acts_since_writer=LIMITS["max_acts_per_item"]),
    # A Hold that leaves on a conflict or a reopened thread, one change from coming back: each starts nearer than two
    # changes from another base would reach.
    "act_ceiling, conflicted": base([reviewed()], acts_since_writer=LIMITS["max_acts_per_item"], mergeable=False),
    "attempts_exhausted, of approvals, conflicted": base([reviewed()] + failures(LIMITS["max_attempts"],
                                                                                "issue-approval"), mergeable=False),
    "approver_is_author_or_last_pusher, conflicted": base([reviewed()], last_pusher=CONFIG["approver"],
                                                          mergeable=False),
    "approver_is_author_or_last_pusher, awaiting review": base(last_pusher=CONFIG["approver"]),
    "proposals_await_owner at the act ceiling, with a ruling Run": base(
        [reviewed(), fix(), dict(ruling(), status="in_progress", conclusion=None)], threads=[thread()],
        acts_since_writer=LIMITS["max_acts_per_item"]),
    "max_rounds, conflicted": base([reviewed()] + [r for i in range(LIMITS["max_rounds"])
                                                   for r in (fix(20 + 2 * i, "a%d" % i), ruling(21 + 2 * i, "o%d" % i))]
                                   + [fix(27, "a9")], threads=[thread()], mergeable=False),
    "act_ceiling, one act short": base([reviewed()], acts_since_writer=LIMITS["max_acts_per_item"] - 1),
    "draft": base(is_draft=True),
    "base_not_protected": base(targets_protected=False),
    "base_not_protected, held": base([reviewed()], targets_protected=False, label_events=[labelled(t.LABEL_HOLD)]),
    "base_not_protected, approved": base([reviewed()], targets_protected=False, reviews=APPROVED),
    "base_not_protected, a draft": base(targets_protected=False, is_draft=True),
    "merged": base(state="merged"),
    "closed": base(state="closed"),
    # An item with an acceptance contract: its evidence not yet given, a criterion failing, and every one passing.
    "acceptance_evidence_missing": base([reviewed()], acceptance=contract()),
    "acceptance_evidence_missing, an agent's": base([reviewed()], acceptance=contract(), **AGENT),
    "acceptance_failed": base([reviewed()], acceptance=contract(results=[evidence("AC-1", "failing")])),
    "acceptance_failed, with a fix Run": base([reviewed(), fix(status="in_progress")],
                                              acceptance=contract(results=[evidence("AC-1", "failing")])),
    "approval_due, with a contract": base([reviewed()], acceptance=contract(results=ACCEPTED)),
    "in_merge_queue, with a contract": base([reviewed()], reviews=APPROVED, queue=True, acts_since_writer=2,
                                            acceptance=contract(results=ACCEPTED)),
}


def now(pr: dict) -> str:
    return at(pr["minute"])


def kernel(pr: dict) -> dict:
    ctx = context(passes_since=now(pr), **pr.get("context", {}))
    return decide(pr["facts"], pr["runs"], ctx, CONFIG, now(pr))


# Facts for the reasons that keep the State they were given: a Pause, capacity, concurrency and a count of acts that
# cannot be read. They change no State, so they are not explored; each must still be given.
STILL = {
    "paused": dict(base([reviewed()]), context={"paused": True}),
    "pause_unreadable": dict(base([reviewed()]), context={"paused": None}),
    "capacity": dict(base(), context={"model_deferred_until": "2099-01-01T00:00:00Z"}),
    "capacity_unreadable": dict(base(), context={"active_runs": None}),
    "concurrency": dict(base(), context={"active_runs": CONFIG["limits"]["org_max_active_runs"]}),
    # A count the facts schema refuses, which the Kernel still reads as unreadable.
    "acts_unreadable": base([reviewed()], acts_since_writer=None),
    # A result on this content for a criterion the contract does not name: no State, so nothing to explore from.
    "acceptance_unreadable": base([reviewed()], acceptance=contract(results=ACCEPTED + [evidence("AC-9")])),
    # A path the schema refuses, which the Kernel still reads as unreadable.
    "paths_unreadable": base([reviewed()], changed_paths=[a_file("docs/../lifecycle/issue.json"),
                                                           a_file("docs/notes.md")]),
}


# ---- the changes, each by one actor. A change returns the pull request after it, or None where it cannot be made.

def changed(pr: dict) -> dict:
    """A copy of `pr` a minute later, for a change to be made to."""
    out = marshal.loads(marshal.dumps(pr))     # a deep copy of plain data, and quicker than copy.deepcopy
    out["minute"] += 1
    return out


def open_item(fn):
    """A change that can be made only to a pull request that is open."""
    def move(pr):
        return fn(changed(pr)) if pr["facts"]["state"] == "open" else None
    move.__name__ = fn.__name__
    return move


def push(pr: dict, who: str, writer: bool, diff=None) -> dict:
    f = pr["facts"]
    f.update(content_id="sha256:%04x" % pr["minute"], last_push_at=now(pr), last_pusher=who, queue=False,
             mergeable=True, checks=copy.deepcopy(PENDING), diff=diff or {"files": 2, "lines": 40, "truncated": False})
    if writer:
        f["last_writer_action_at"] = now(pr)
    pr.pop("rerun", None)
    return pr


def writer_acted(pr: dict) -> dict:
    pr["facts"]["last_writer_action_at"] = now(pr)
    return pr


def label(pr: dict, name: str, by: dict, action="labeled") -> dict:
    pr["facts"]["label_events"].append(labelled(name, by, now(pr), action))
    return writer_acted(pr) if by["kind"] == "human" and by["can_write"] else pr


def new_thread(pr: dict, by: dict, **over) -> dict:
    f = pr["facts"]
    th = thread("T%d" % (len(f["threads"]) + 1), kind=by["kind"], name=by["name"], can_write=by["can_write"],
                at=now(pr), **over)
    f["threads"].append(th)
    return pr


def resolve(pr: dict, by: dict, which) -> dict:
    """`by` resolves every open thread `which` picks."""
    found = [th for th in pr["facts"]["threads"] if not th["resolved"] and which(th)]
    if not found:
        return None
    for th in found:
        th.update(resolved=True, resolved_by=dict(by))
    return pr


def reopen(pr: dict, by: dict) -> dict:
    """`by` marks unresolved again every resolved thread it may: a person any, a Lens's App its own Lens's."""
    found = [th for th in pr["facts"]["threads"] if th["resolved"]
             and (by["kind"] == "human" or th["opened_by"]["name"] == by["name"])]
    if not found:
        return None
    for th in found:
        th.update(resolved=False, resolved_by=None)
    return writer_acted(pr) if by["kind"] == "human" else pr


def person_review(pr: dict, state: str) -> dict:
    f = pr["facts"]
    if COLLEAGUE["name"] in (f["author"], f["last_pusher"]):
        return None
    f["reviews"].append(review(state, content=f["content_id"], at=now(pr), **COLLEAGUE))
    return writer_acted(pr)


def dismiss(pr: dict, by: dict, whose: str) -> dict:
    live = [rv for rv in pr["facts"]["reviews"] if rv["by"]["name"] == whose and rv["state"] != "dismissed"]
    if not live:
        return None
    live[-1].update(state="dismissed", dismissed_from=live[-1]["state"], dismissed_by=dict(by))
    return writer_acted(pr) if by["kind"] == "human" else pr


def check(pr: dict, i: int, conclusion: str, rerun: bool = False) -> dict:
    """The i-th required check reports. On a run a person started again, on unchanged content, the verdict is that
    person's (the ruling on #38): a Lens reports once for each run, and only a person runs a check again."""
    c = pr["facts"]["checks"][i]
    again = pr.get("rerun", [])
    if CONFIG["check_conclusions"].get(c["conclusion"]) != "pending" or (i in again) != rerun:
        return None
    c.update(conclusion=conclusion, completed_at=now(pr))
    pr["rerun"] = [j for j in again if j != i]
    return pr


def ran_again(pr: dict, which) -> dict:
    """A person runs again each required check `which` picks: it is pending until its Lens reports once more, and the
    re-run replaces the run it repeats."""
    checks = pr["facts"]["checks"]
    again = [i for i, c in enumerate(checks) if c["app_id"] != OTHER_APP and which(c)]
    if not again:
        return None
    for i in again:
        checks[i].update(conclusion="queued", completed_at=None)
    pr["rerun"] = sorted(set(pr.get("rerun", [])) | set(again))
    return writer_acted(pr)


def ending(pr: dict, conclusion="success", outcome=None, intent=None) -> dict:
    """The oldest Run not yet completed ends. None when there is none, or it is not of `intent`."""
    live = [r for r in pr["runs"] if r["status"] != "completed"]
    if not live or (intent is not None and live[0]["intent"] != intent):
        return None
    live[0].update(status="completed", conclusion=conclusion, outcome=outcome)
    return pr


def applies(pr: dict, intent: str):
    """The oldest Run not yet completed, of `intent`, succeeds, and `apply` makes its Effects: or None.

    `apply` reads the item again first, and writes nothing to one that is held or whose content changed (decision
    0004); the Run then fails as superseded, which `a Run is superseded` makes.
    """
    live = [r for r in pr["runs"] if r["status"] != "completed"]
    if not live or live[0]["intent"] != intent or live[0]["content_id"] != pr["facts"]["content_id"] \
            or kernel(pr)["state"] == t.HELD:
        return None
    return ending(pr)


def superseded(pr: dict) -> dict:
    """The oldest Run not yet completed fails as superseded: `apply` found the item held or changed."""
    live = [r for r in pr["runs"] if r["status"] != "completed"]
    if not live or (live[0]["content_id"] == pr["facts"]["content_id"] and kernel(pr)["state"] != t.HELD):
        return None
    return ending(pr, "failure", "superseded")


def review_ends(pr: dict, finding: bool) -> dict:
    if applies(pr, "review-change") is None:
        return None
    return new_thread(pr, REVIEWER_APP) if finding else pr


def fix_ends(pr: dict) -> dict:
    if applies(pr, "fix-findings") is None:
        return None
    return push(pr, AUTHOR_APP["name"], writer=False)


def ruling_ends(pr: dict, accepts: bool) -> dict:
    if applies(pr, "adjudicate-findings") is None:
        return None
    if accepts:
        resolve(pr, REVIEWER_APP, lambda th: th["opened_by"]["kind"] == "lens")
    return pr


def admits(pr: dict) -> dict:
    """The Controller starts the Run the Kernel asks for."""
    d = kernel(pr)
    if d["outcome"] != t.ADMIT:
        return None
    pr = changed(pr)
    pr["runs"].append(run(role=d["admit"]["role"], intent=d["admit"]["intent"], content=d["admit"]["content_id"],
                          status="in_progress", at=now(pr), name="n%d" % pr["minute"]))
    return pr


def acts(pr: dict, lands: bool = True) -> dict:
    """The Controller makes the act the Kernel asks for. An approval is a Run with no Engine, which may not land."""
    d = kernel(pr)
    if d["outcome"] != t.ACT:
        return None
    pr = changed(pr)
    f = pr["facts"]
    if d["action"] == "issue_approval":
        pr["runs"].append(run(role=CONFIG["owner_role"], intent=t.ISSUE_APPROVAL, content=f["content_id"],
                              conclusion="success" if lands else "failure", outcome=None if lands else "item",
                              at=now(pr), name="n%d" % pr["minute"]))
        if not lands:
            return pr
        f["reviews"].append(review(content=f["content_id"], at=now(pr)))
    elif not lands:
        return None
    else:
        f["queue"] = d["action"] == "enqueue"
    f["acts_since_writer"] += 1
    return pr


def reports(pr: dict, result: str) -> dict:
    """A Lens reports a result for the first criterion of the contract with none on this content: or None."""
    f = pr["facts"]
    if f["acceptance"] is None:
        return None
    given = {ev["criterion"] for ev in f["acceptance"]["results"] if ev["content_id"] == f["content_id"]}
    lacking = [c for c in f["acceptance"]["criteria"] if c not in given]
    if not lacking:
        return None
    f["acceptance"]["results"].append(evidence(lacking[0], result, f["content_id"]))
    return pr


def reports_again(pr: dict) -> dict:
    """A Lens gives a second result, failing, for the first criterion with a passing one on this content: another check
    suite's run of the same check, which the port reports beside the first. Or None."""
    f = pr["facts"]
    if f["acceptance"] is None:
        return None
    passed = [ev["criterion"] for ev in f["acceptance"]["results"]
              if ev["content_id"] == f["content_id"] and ev["result"] == "passing"]
    if not passed:
        return None
    f["acceptance"]["results"].append(evidence(passed[0], "failing", f["content_id"]))
    return pr


def expires(pr: dict) -> dict:
    """The oldest result is gone, as an artifact is past its retention: or None when there is none."""
    f = pr["facts"]
    if f["acceptance"] is None or not f["acceptance"]["results"]:
        return None
    del f["acceptance"]["results"][0]
    return pr


def queue_merges(pr: dict) -> dict:
    if not pr["facts"]["queue"]:
        return None
    pr["facts"].update(state="merged", queue=False)
    return pr


def queue_ejects(pr: dict) -> dict:
    if not pr["facts"]["queue"]:
        return None
    pr["facts"]["queue"] = False
    return pr


def rebase(pr: dict) -> dict:
    """A dependency bot rebases its own pull request: new content, of the same size."""
    f = pr["facts"]
    if f["class"] != "dependency" or f["last_pusher"] != f["author"]:
        return None
    return push(pr, f["author"], writer=False, diff=f["diff"])


def pins(pr: dict) -> dict:
    """A dependency bot rebases its own pull request onto a new pin of an Action, in a Lens's workflow file."""
    f = pr["facts"]
    if any(entry["path"] == PIN for entry in f["changed_paths"]):
        return None
    out = rebase(pr)
    if out is not None:
        out["facts"]["changed_paths"] = f["changed_paths"] + [a_file(PIN)]
        out["facts"]["diff"] = dict(f["diff"], files=len(out["facts"]["changed_paths"]))
    return out


def set_fact(**values):
    def change(pr):
        f = pr["facts"]
        if all(f[k] == v for k, v in values.items()):
            return None
        f.update(values)
        return pr
    return change


def a_persons(fn):
    """A person's change: what a person with write access does is an action of theirs, and renews the allowance."""
    def change(pr):
        out = fn(pr)
        return writer_acted(out) if out is not None else None
    return change


class Move:
    def __init__(self, name: str, by: str, fn, whole: bool = False, when=None):
        """`fn` takes a copy of an open pull request a minute on; with `whole`, the pull request as it stands. `when`,
        if given, says cheaply whether the change can be made at all, so that no copy is made for one that cannot."""
        self.name, self.by = name, by
        make = fn if whole else open_item(fn)
        self.make = make if when is None else (lambda pr: make(pr) if when(pr) else None)


def running(pr: dict) -> bool:
    return any(r["status"] != "completed" for r in pr["runs"])


def checking(i: int, rerun: bool):
    """Whether the i-th required check is pending, on a run a person started again or not."""
    def when(pr):
        c = pr["facts"]["checks"][i]
        return CONFIG["check_conclusions"].get(c["conclusion"]) == "pending" and (i in pr.get("rerun", [])) == rerun
    return when


def resolved(pr: dict) -> bool:
    return any(th["resolved"] for th in pr["facts"]["threads"])


NORMAL = {"files": 2, "lines": 40, "truncated": False}
MOVES = [
    # A person with write access.
    Move("a person pushes", "human", lambda pr: push(pr, MAINTAINER["name"], True)),
    Move("a person pushes an empty diff", "human", lambda pr: push(pr, MAINTAINER["name"], True,
                                                                   {"files": 0, "lines": 0, "truncated": False})),
    Move("a person pushes a diff too large", "human", lambda pr: push(pr, MAINTAINER["name"], True,
                                                                      dict(NORMAL, truncated=True))),
    Move("a person marks it a draft", "human", a_persons(set_fact(is_draft=True, queue=False))),
    Move("a person marks it ready", "human", a_persons(set_fact(is_draft=False))),
    Move("a person adds a Hold", "human", lambda pr: label(pr, t.LABEL_HOLD, MAINTAINER)),
    Move("a person removes a Hold", "human", lambda pr: label(pr, t.LABEL_HOLD, MAINTAINER, "unlabeled")),
    Move("a person adds hands-off", "human", lambda pr: label(pr, t.LABEL_HANDS_OFF, MAINTAINER)),
    Move("a person removes hands-off", "human", lambda pr: label(pr, t.LABEL_HANDS_OFF, MAINTAINER, "unlabeled")),
    Move("a person admits it", "human", lambda pr: label(pr, t.LABEL_ADMIT, MAINTAINER)),
    Move("a person takes its admission off", "human", lambda pr: label(pr, t.LABEL_ADMIT, MAINTAINER, "unlabeled")),
    Move("a person opens a thread", "human", lambda pr: writer_acted(new_thread(pr, MAINTAINER, severity=None))),
    Move("a person marks the resolved threads unresolved", "human", lambda pr: reopen(pr, MAINTAINER), when=resolved),
    Move("a person resolves their threads", "human", a_persons(
        lambda pr: resolve(pr, MAINTAINER, lambda th: th["opened_by"]["name"] == MAINTAINER["name"]))),
    Move("a person resolves a Lens's threads", "human", a_persons(
        lambda pr: resolve(pr, MAINTAINER, lambda th: th["opened_by"]["kind"] == "lens"))),
    Move("a person asks for changes", "human", lambda pr: person_review(pr, "changes_requested")),
    Move("a person approves", "human", lambda pr: person_review(pr, "approved")),
    Move("a person dismisses the approver's approval", "human", lambda pr: dismiss(pr, MAINTAINER, CONFIG["approver"])),
    Move("a person dismisses a request for changes", "human", lambda pr: dismiss(pr, MAINTAINER, COLLEAGUE["name"])),
    Move("a person runs the checks again", "human", lambda pr: ran_again(pr, lambda c: c["conclusion"] != "success")),
    Move("a person runs a passing check again", "human",
         lambda pr: ran_again(pr, lambda c: c["conclusion"] == "success")),
    *[Move("the check %s a person ran again %s" % (c["name"], said), "human",
           (lambda i, said: lambda pr: check(pr, i, said, rerun=True))(i, said), when=checking(i, True))
      for i, c in enumerate(GREEN) for said in ("success", "failure", "neutral")],
    Move("a person closes it", "human", a_persons(set_fact(state="closed", queue=False))),
    Move("a person merges it", "human", a_persons(set_fact(state="merged", queue=False))),
    Move("a person points it at a base that is not protected", "human",
         a_persons(set_fact(targets_protected=False, queue=False))),
    Move("a person points it at a protected base", "human", a_persons(set_fact(targets_protected=True))),
    # Someone with no write access.
    Move("a stranger comments", "stranger", lambda pr: (pr["facts"]["reviews"].append(
        review("commented", content=pr["facts"]["content_id"], at=now(pr), **STRANGER)) or pr)),
    Move("a stranger opens a thread", "stranger", lambda pr: new_thread(pr, STRANGER, severity=None)),
    # A Lens: its check reports, its review Run gives a verdict, its App dismisses a review.
    *[Move("the check %s %s" % (c["name"], said), "lens", (lambda i, said: lambda pr: check(pr, i, said))(i, said),
           when=checking(i, False)) for i, c in enumerate(GREEN) for said in ("success", "failure", "neutral")],
    Move("a Lens's review passes", "lens", lambda pr: review_ends(pr, False), when=running),
    Move("a Lens's review opens a Finding", "lens", lambda pr: review_ends(pr, True), when=running),
    Move("a Lens's App dismisses a person's review", "lens", lambda pr: dismiss(pr, REVIEWER_APP, COLLEAGUE["name"])),
    # A Lens gives the result for a criterion of the acceptance contract, from the check that ran it, on this content.
    *[Move("a Lens reports a criterion %s" % said, "lens", (lambda said: lambda pr: reports(pr, said))(said))
      for said in ("passing", "failing")],
    Move("a Lens gives a criterion a second result, failing", "lens", reports_again),
    # Any App with write access can dismiss a review and place or remove a label (`an_app_can_dismiss_a_review`,
    # `an_app_can_label`), a Lens's among them.
    Move("a Lens's App marks its threads unresolved", "lens", lambda pr: reopen(pr, REVIEWER_APP), when=resolved),
    Move("a Lens's App resolves its own threads", "lens",
         lambda pr: resolve(pr, REVIEWER_APP, lambda th: th["opened_by"]["name"] == REVIEWER_APP["name"])),
    Move("a Lens's App dismisses the approver's approval", "lens",
         lambda pr: dismiss(pr, REVIEWER_APP, CONFIG["approver"])),
    Move("a Lens's App adds a Hold", "lens", lambda pr: label(pr, t.LABEL_HOLD, REVIEWER_APP)),
    Move("a Lens's App adds hands-off", "lens", lambda pr: label(pr, t.LABEL_HANDS_OFF, REVIEWER_APP)),
    Move("a Lens's App removes a Hold", "lens", lambda pr: label(pr, t.LABEL_HOLD, REVIEWER_APP, "unlabeled")),
    # The Factory: the Runs and acts the Kernel asks for, a Run that fails, and its Apps acting out of turn. A Role's
    # App writes only inside a Run, with a token minted for it (decision 0005).
    Move("the Controller admits a Run", "factory", admits, whole=True),
    Move("the Controller makes an act", "factory", acts, whole=True),
    Move("an approval does not land", "factory", lambda pr: acts(pr, lands=False), whole=True),
    Move("a fix Run pushes", "factory", fix_ends, when=running),
    Move("a fix Run answers with no push", "factory", lambda pr: applies(pr, "fix-findings"), when=running),
    Move("a ruling Run accepts", "factory", lambda pr: ruling_ends(pr, True), when=running),
    Move("a ruling Run rejects", "factory", lambda pr: ruling_ends(pr, False), when=running),
    Move("a Run is superseded", "factory", superseded, when=running),
    Move("a Run fails for the item", "factory", lambda pr: ending(pr, "failure", "item"), when=running),
    Move("a Run fails for the environment", "factory", lambda pr: ending(pr, "failure", "environment"), when=running),
    Move("a Run times out", "factory", lambda pr: ending(pr, "timed_out", "capacity"), when=running),
    Move("a Role's App adds a Hold", "factory", lambda pr: label(pr, t.LABEL_HOLD, AUTHOR_APP)),
    Move("a Role's App removes a Hold", "factory", lambda pr: label(pr, t.LABEL_HOLD, AUTHOR_APP, "unlabeled")),
    Move("a Role's App adds hands-off", "factory", lambda pr: label(pr, t.LABEL_HANDS_OFF, AUTHOR_APP)),
    Move("a Role's App removes hands-off", "factory",
         lambda pr: label(pr, t.LABEL_HANDS_OFF, AUTHOR_APP, "unlabeled")),
    Move("a Role's App marks its draft ready", "factory", set_fact(is_draft=False)),
    Move("a Role's App dismisses the approver's approval", "factory",
         lambda pr: dismiss(pr, AUTHOR_APP, CONFIG["approver"])),
    Move("a Role's App dismisses a person's review", "factory", lambda pr: dismiss(pr, AUTHOR_APP, COLLEAGUE["name"])),
    Move("a Role's App resolves a person's threads", "factory",
         lambda pr: resolve(pr, AUTHOR_APP, lambda th: th["opened_by"]["kind"] == "human")),
    # GitHub itself, and any App that is not the one a Lens is read from: the Kernel cannot tell which.
    Move("another App posts a check under a Lens's name", "platform", lambda pr: (pr["facts"]["checks"].append(
        dict(GREEN[0], app_id=OTHER_APP, completed_at=now(pr))) or pr)),
    Move("the queue merges it", "platform", queue_merges),
    Move("the queue ejects it", "platform", queue_ejects),
    Move("another App adds a Hold", "platform", lambda pr: label(pr, t.LABEL_HOLD, ANOTHER_APP)),
    Move("another App adds hands-off", "platform", lambda pr: label(pr, t.LABEL_HANDS_OFF, ANOTHER_APP)),
    Move("another App removes a Hold", "platform", lambda pr: label(pr, t.LABEL_HOLD, ANOTHER_APP, "unlabeled")),
    Move("another App removes hands-off", "platform",
         lambda pr: label(pr, t.LABEL_HANDS_OFF, ANOTHER_APP, "unlabeled")),
    Move("another App marks a draft ready", "platform", set_fact(is_draft=False)),
    Move("another App dismisses the approver's approval", "platform",
         lambda pr: dismiss(pr, ANOTHER_APP, CONFIG["approver"])),
    # The base moves, whether the item merged cleanly or conflicted: a conflict can clear with no push.
    Move("the base moves", "platform",
         lambda pr: set_fact(mergeable=None)(pr) if pr["facts"]["mergeable"] is not None else None),
    Move("GitHub works out it merges cleanly", "platform",
         lambda pr: set_fact(mergeable=True)(pr) if pr["facts"]["mergeable"] is None else None),
    # The queue drops a pull request that conflicts.
    Move("GitHub works out it conflicts", "platform",
         lambda pr: set_fact(mergeable=False, queue=False)(pr) if pr["facts"]["mergeable"] is None else None),
    Move("GitHub retargets it at the default branch", "platform", set_fact(targets_protected=True)),
    Move("a dependency bot rebases it", "platform", rebase),
    Move("a dependency bot rebases it onto a workflow's pin", "platform", pins),
    # A result is kept as long as the artifact it was read from: GitHub deletes it past its retention, whoever asks.
    Move("a result expires", "platform", expires),
]


def key(item: dict) -> str:
    """What a Work item is, whatever minute it is."""
    return json.dumps({k: v for k, v in item.items() if k != "minute"}, sort_keys=True)


def explore(bases: dict, moves: list, judge=None, depth: int = 2):
    """Every transition the moves make from `bases`, `depth` changes deep, as {(from, to, by): {(reason before, reason
    after): an example}}; and every (State, reason) reached on the way. Any type of Work item: `judge` gives {'state', 'reason'} for one, by default
    the Kernel's Decision on a pull request.

    Facts that give no State, such as a merge state GitHub has not worked out, are passed through: the transition is
    from the last State to the next, made by whoever made the change that gave it.
    """
    judge = judge or kernel
    made, reached, seen = {}, set(), set()
    level = [(how, pr, judge(pr)) for how, pr in bases.items()]
    for deep in range(depth):
        following = []
        for how, pr, before in level:
            k = key(pr) + str(before["state"])
            if k in seen:
                continue
            seen.add(k)
            reached.add((before["state"], before["reason"]))
            for m in moves:
                after_pr = m.make(pr)
                if after_pr is None:
                    continue
                after = judge(after_pr)
                if after["state"] is None:
                    after = dict(after, state=before["state"], reason=before["reason"])
                elif before["state"] is not None and after["state"] != before["state"]:
                    made.setdefault((before["state"], after["state"], m.by), {}).setdefault(
                        (before["reason"], after["reason"]), "%s, then %s" % (how, m.name))
                following.append(("%s, then %s" % (how, m.name), after_pr, after))
        level = following
    reached |= {(after["state"], after["reason"]) for _, _, after in level}
    return made, reached


def state_of(node, where: str, problems: list):
    """The State a node of the Kernel's source writes out: a code from `terms`, a string, or None. Else a problem."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "t" \
            and isinstance(getattr(t, node.attr, None), str):
        return getattr(t, node.attr)
    if isinstance(node, ast.Constant) and (node.value is None or isinstance(node.value, str)):
        return node.value
    problems.append("%s: a State that is not written out" % where)
    return None


def reason_of(node, where: str, problems: list):
    """The reason a node writes out: a string. Else a problem: a variable or a conditional cannot be read."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    problems.append("%s: a reason that is not written out" % where)
    return None


def sites(sources: dict) -> tuple:
    """Every place the Kernel's source gives a reason, read without running it: ({(State, reason)}, {reason},
    [problem]).

    A State and a reason written together are a pair. A reason given to a Decision derive already made,
    `dict(d, reason=...)`, keeps that Decision's State, so it is a reason alone; so is a reason written out beside
    `state` in `_decision(facts, state, ...)`, which passes on derive's State. `_decision(facts, None, ...)` gives no
    State. Anything else that is not written out, a variable other than derive's own `reason` passed on, or a
    conditional, cannot be read, and is a problem: so is a reason with no State.
    """
    pairs, alone, problems = set(), set(), []
    for rel, text in sources.items():
        tree = ast.parse(text)
        # `_decision` builds a Decision from the State and reason its callers give, which are read where they call it.
        maker = {id(n) for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == "_decision"
                 for n in ast.walk(f)}
        for node in ast.walk(tree):
            where = "%s:%d" % (rel, getattr(node, "lineno", 0))
            if id(node) in maker:
                continue
            if isinstance(node, ast.Dict):
                fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
                if "reason" not in fields:
                    continue
                if "state" not in fields:
                    problems.append("%s: a reason with no State" % where)
                    continue
                state, reason = state_of(fields["state"], where, problems), reason_of(fields["reason"], where, problems)
                if state is not None and reason is not None:
                    pairs.add((state, reason))
            elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "dict":
                for kw in node.keywords:
                    if kw.arg == "state":
                        problems.append("%s: a State given to a Decision already made" % where)
                    elif kw.arg == "reason" and reason_of(kw.value, where, problems) is not None:
                        alone.add(kw.value.value)
            elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_decision":
                given, said = node.args[1], node.args[2]
                if (isinstance(given, ast.Name) and given.id == "state") or \
                        (isinstance(given, ast.Constant) and given.value is None):
                    # derive's State, or none, passed on: with derive's reason, or with one of its own written out,
                    # which keeps derive's State and so is a reason alone.
                    if not (isinstance(said, ast.Name) and said.id == "reason"):
                        reason = reason_of(said, where, problems)
                        if reason is not None and isinstance(given, ast.Name):
                            alone.add(reason)
                    continue
                state, reason = state_of(given, where, problems), reason_of(said, where, problems)
                if state is not None and reason is not None:
                    pairs.add((state, reason))
    return pairs, alone, problems


def kernel_sites() -> tuple:
    return sites({rel: (ROOT / rel).read_text() for rel in ("kernel/derive.py", "kernel/decide.py", "kernel/brakes.py")})


def uncovered(pairs: set, alone: set, decisions: list) -> list:
    """Each pair, and each reason alone, that no Decision in `decisions` gives."""
    given = {(d["state"], d["reason"]) for d in decisions}
    return sorted(pairs - given) + sorted(alone - {reason for _, reason in given})


def example(pairs: dict) -> str:
    (before, after), how = sorted(pairs.items())[0]
    return "%s (%s -> %s)" % (how, before, after)


EXPLORED = {}


def explored():
    if not EXPLORED:
        EXPLORED["made"], EXPLORED["reached"] = explore(BASES, MOVES)
    return EXPLORED["made"], EXPLORED["reached"]


# What bounds a Hold that no person makes, by the reason it gives: the ceiling it was reached at, whose counter only a
# writer's action renews; or, for a label, a person, since only a person ends what a label holds, whoever placed it.
# The Hold of I-26 ends only by a push: a person's, or a fix Run's, after which the Role's App is the last pusher. On a
# lap through it that a Lens or the platform makes, the only work the Factory does is that Run, which the Run ceiling
# counts, so it is bound as the at-ceiling laps are: by the counter of the Factory's own work on the lap.
HOLD_BOUNDS = {"run_ceiling": "max_runs_per_item", "attempts_exhausted": "max_attempts", "max_rounds": "max_rounds",
               "act_ceiling": "max_acts_per_item", "human_hold": check_lifecycle.PERSON,
               "hands_off": check_lifecycle.PERSON, "approver_is_author_or_last_pusher": "max_runs_per_item"}
# What a label holds.
LABEL_HOLDS = ("human_hold", "hands_off")
# Transitions the Lifecycle declares that nothing here makes, each with why it is kept.
UNREACHED = {
}


def entered_through_a_person(lifecycle: dict) -> set:
    """The States every way into is a person's, or from another such State. An item may start in one, as in a draft,
    but a cycle through one passes through a person, so what leaves it needs no bound."""
    found, more = set(), True
    while more:
        more = False
        for state in set(lifecycle["states"]) - found:
            ways_in = [tr for tr in lifecycle["transitions"] if tr["to"] == state]
            if ways_in and all(tr["by"] == "human" or tr["from"] in found for tr in ways_in):
                found.add(state)
                more = True
    return found


def holds_made_by_no_person(made: dict, lifecycle: dict = LIFECYCLE) -> dict:
    """Each Hold made by anyone but a person, from a State not entered only through a person, as {(from, held, by,
    bound): an example}."""
    through = entered_through_a_person(lifecycle)
    out = {}
    for (start, end, by), pairs in made.items():
        if end == t.HELD and by != "human" and start not in through:
            for (before, after), how in sorted(pairs.items()):
                out.setdefault((start, end, by, HOLD_BOUNDS.get(after)), "%s (%s -> %s)" % (how, before, after))
    return out


class Transitions(unittest.TestCase):
    def test_every_set_of_facts_made_here_is_valid(self):
        for name, pr in BASES.items():
            self.assertEqual(validate(pr["facts"], FACTS_SCHEMA), [], name)
            self.assertIsNotNone(kernel(pr)["state"], name)
        for m in MOVES:
            for name, pr in BASES.items():
                out = m.make(pr)
                if out is not None:
                    self.assertEqual(validate(out["facts"], FACTS_SCHEMA), [], (name, m.name))

    def test_every_state_and_reason_the_kernel_gives_has_facts(self):
        pairs, alone, problems = kernel_sites()
        self.assertEqual(problems, [], "write each State and reason out, so that this test can read it")
        decisions = [kernel(pr) for pr in list(BASES.values()) + list(STILL.values())]
        self.assertEqual(uncovered(pairs, alone, decisions), [], "add facts to BASES, or STILL, that give each of these")
        self.assertEqual(sorted({s for s, _ in pairs} - set(LIFECYCLE["states"])), [])

    def test_a_state_or_reason_the_source_does_not_write_out_fails(self):
        # A State the Lifecycle does not know, given with a reason the Kernel already gives elsewhere, is a pair no
        # facts give.
        decisions = [kernel(pr) for pr in BASES.values()]
        pairs, alone, problems = sites({"x.py": 'r = {"state": "frozen", "reason": "too_large"}\n'})
        self.assertEqual((uncovered(pairs, alone, decisions), problems), ([("frozen", "too_large")], []))
        # A reason or a State that is not written out cannot be read at all.
        for code in ('{"state": t.HELD, "reason": why}', '{"state": t.HELD, "reason": "a" if x else "b"}',
                     '{"state": s, "reason": "too_large"}', '{"reason": "too_large"}', 'dict(d, reason=why)',
                     'dict(d, state=t.HELD)', '_decision(facts, t.HELD, why, [], t.HOLD)',
                     '_decision(facts, t.HELD if x else t.DRAFT, "draft", [], t.HOLD)'):
            _, _, problems = sites({"x.py": "r = %s\n" % code})
            self.assertEqual(len(problems), 1, code)
        # A reason of its own beside derive's State is a reason alone, which facts must give; a variable there is
        # unreadable, but derive's own reason passed on is not.
        pairs, alone, problems = sites({"x.py": 'r = _decision(facts, state, "untested_reason", [], t.HOLD)\n'})
        self.assertEqual((uncovered(pairs, alone, decisions), problems), (["untested_reason"], []))
        for code in ("_decision(facts, state, why, [], t.DEFER)", "_decision(facts, None, why, [], t.DEFER)"):
            self.assertEqual(len(sites({"x.py": "r = %s\n" % code})[2]), 1, code)
        pairs, alone, problems = sites({"x.py": "r = _decision(facts, state, reason, [], t.DEFER)\n"
                                                "r = _decision(facts, None, reason, [], t.DEFER)\n"})
        self.assertEqual((pairs, alone, problems), (set(), set(), []))

    def test_every_state_reached_is_one_the_lifecycle_declares(self):
        _, reached = explored()
        self.assertEqual(sorted({s for s, _ in reached if s is not None} - set(LIFECYCLE["states"])), [])

    def test_every_change_of_state_is_declared_with_who_makes_it(self):  # I-12
        made, _ = explored()
        missing = check_lifecycle.undeclared(LIFECYCLE, made)
        self.assertEqual(missing, [], "\n".join("%s -> %s by %s: %s" % (*m, example(made[m])) for m in missing))

    def test_a_hold_no_person_makes_names_what_bounds_it(self):  # I-14
        # The ceiling it was reached at, or for a label, a person. Never a counter that did not advance to it.
        made, _ = explored()
        declared = {(tr["from"], tr["to"], tr["by"], tr["bound"]) for tr in LIFECYCLE["transitions"]}
        holds = holds_made_by_no_person(made)
        self.assertEqual(sorted(h for h in holds if h[3] is None), [], "a Hold with nothing behind it")
        missing = sorted(set(holds) - declared)
        self.assertEqual(missing, [], "\n".join("%s -> %s by %s, bound %s: %s" % (*h, holds[h]) for h in missing))
        # And no such Hold is declared with a bound that nothing here reaches it at.
        through = entered_through_a_person(LIFECYCLE)
        self.assertEqual(through, {t.NOT_SERVED, t.DRAFT, t.CLOSED})
        unfound = {h for h in declared if h[1] == t.HELD and h[2] != "human" and h[0] not in through} - set(holds)
        self.assertEqual(sorted(unfound), [])

    def test_only_a_person_ends_what_a_label_holds(self):  # I-6, L-02, L-17
        # The queue can still merge a held item before a pass takes it out: that race ends the item, not the Hold.
        made, _ = explored()
        ended = sorted("%s -> %s by %s: %s" % (start, end, by, how) for (start, end, by), pairs in made.items()
                       if start == t.HELD and by != "human" and end not in LIFECYCLE["terminal"]
                       for (before, _), how in pairs.items() if before in LABEL_HOLDS)
        self.assertEqual(ended, [])

    def test_every_transition_declared_is_found_or_kept_for_a_reason(self):
        made, _ = explored()
        declared = check_lifecycle.declared(LIFECYCLE)
        self.assertEqual(sorted(declared - set(made) - set(UNREACHED)), [], "remove it, or say in UNREACHED why not")
        # Nothing is kept that is found, or not declared.
        self.assertEqual(sorted(set(UNREACHED) - (declared - set(made))), [])

    def test_a_stranger_changes_no_state(self):  # I-28
        made, _ = explored()
        self.assertEqual([m for m in made if m[2] == "stranger"], [])

    def test_the_states_that_admit_nothing_include_every_end_and_not_only_the_ends(self):
        self.assertLessEqual(set(LIFECYCLE["terminal"]), t.ADMITS_NOTHING)
        # Not served admits nothing, and is no end: GitHub serves the item again when it retargets it.
        self.assertEqual(t.ADMITS_NOTHING - set(LIFECYCLE["terminal"]), {t.NOT_SERVED})
        for state in t.ADMITS_NOTHING:
            self.assertIn(state, LIFECYCLE["states"])

    def test_a_person_a_lens_the_factory_and_the_platform_each_change_some_state(self):
        # The exploration is not empty: each who may change a State is seen to.
        made, _ = explored()
        self.assertEqual({by for _, _, by in made}, {"human", "lens", "factory", "platform"})


class AnyLifecycle(unittest.TestCase):
    """The exploration and the comparison serve any Lifecycle. An issue's needs only its own facts, changes and judge,
    once the Kernel derives an issue's State."""

    def test_an_issue_explored_is_held_to_the_issue_lifecycle(self):
        lc = check_lifecycle.load("issue")

        def becomes(state, *starts):
            def change(item):
                return dict(item, state=state) if item["state"] in starts else None
            return change

        def judge(item):
            return {"state": item["state"], "reason": item["state"]}

        moves = [Move("the Controller triages it", "factory", becomes("triage", "new"), whole=True),
                 Move("a person declines it", "human", becomes("declined", "new", "triage"), whole=True)]
        made, _ = explore({"new": {"state": "new"}}, moves, judge)
        self.assertEqual(sorted(made), [("new", "declined", "human"), ("new", "triage", "factory"),
                                        ("triage", "declined", "human")])
        self.assertEqual(check_lifecycle.undeclared(lc, made), [])
        # The other side: the Factory may not decline an issue.
        moves.append(Move("the Factory declines it", "factory", becomes("declined", "new", "triage"), whole=True))
        made, _ = explore({"new": {"state": "new"}}, moves, judge)
        self.assertEqual(check_lifecycle.undeclared(lc, made), [("new", "declined", "factory"),
                                                                ("triage", "declined", "factory")])

    def test_a_transition_declared_by_someone_else_is_undeclared(self):
        for name in ("pull_request", "issue"):
            lc = check_lifecycle.load(name)
            tr = lc["transitions"][0]
            made = {(tr["from"], tr["to"], tr["by"]): "declared"}
            self.assertEqual(check_lifecycle.undeclared(lc, made), [], name)
            others = sorted({"human", "lens", "factory", "platform"} - {tr["by"]})
            for by in others:
                if (tr["from"], tr["to"], by) not in check_lifecycle.declared(lc):
                    made = {(tr["from"], tr["to"], by): "another"}
                    self.assertEqual(check_lifecycle.undeclared(lc, made), [(tr["from"], tr["to"], by)], name)
            self.assertEqual(check_lifecycle.undeclared(lc, {(lc["states"][0], "nowhere", "human"): "x"}),
                             [(lc["states"][0], "nowhere", "human")], name)


if __name__ == "__main__":
    unittest.main()
