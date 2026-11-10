"""Every step that mints a token mints it for every read its code can reach (slice 1's dry runs, the Factory Builder's
sweep of 2026-11-10). Each step's code is walked statically, from its entry, through the Harness's and the Controller's
own functions, to each function of `adapters/` it calls. Each such function's reads are named here, by the permission
GitHub asks for them, and the step's token, minted from `config/apps.json` as the step mints it, must hold each one.
A function of `adapters/` that no table names fails the walk, so a read added to a step is classed before it ships."""
from __future__ import annotations

import ast
import json
import pathlib
import unittest

from adapters import identity
from controller import __main__ as pass_main
from harness import apply, queue_step, read

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = json.loads((ROOT / "config" / "apps.json").read_text())
PACKAGES = ("adapters", "harness", "controller", "release")

# Each function of `adapters/` that reads GitHub, by the permissions its reads take, as GitHub's documentation names the
# endpoint's fine-grained permission. Read is enough for each.
READS = {
    "passes.find": {"actions"}, "passes.records": {"actions"}, "passes.started": {"actions"},
    "passes.written": {"actions"},
    "records.runs": {"actions"}, "records.known": {"actions"}, "records.read_at": {"actions"},
    "applied.recorded": {"actions"}, "applied.opened": {"actions"}, "applied.effects": {"actions"},
    "tags.read": {"contents"},
    "pull.read": {"pull_requests"}, "pull.base": {"contents"}, "pull.change": {"contents"},
    # The pull request, its branch, its activity, its diff and files, its timeline, reviews, checks, closing issues,
    # threads and edits (adapters/facts.py).
    "facts.snapshot": {"pull_requests", "contents", "metadata", "issues", "checks"},
    "texts.issues": {"issues", "pull_requests"},
    "timeline.Accounts": {"metadata"},          # a login's permission on the repo
    "pause.read": {"actions_variables"},        # FACTORY_PAUSED, the repo's and the org's through the repo
    "items.open_pull_requests": {"pull_requests"},
    "seen.read": {"issues", "pull_requests", "checks"}, "seen.pushes": {"metadata"},
    # The queue App's port: the pull request, its threads and its place in the queue, read before each write.
    "queue.pull": {"pull_requests"}, "queue.threads": {"pull_requests"}, "queue.queued": {"pull_requests"},
}
# What writes, by the permission each write takes, as `config/apps.json`'s needs name it.
WRITES = {"queue.enqueue": {"contents"}, "queue.dequeue": {"contents"}, "queue.resolve": {"contents"}}
# What reads nothing of GitHub: a function of the configuration, a request's form, a check of a token, an allowlist that
# wraps a transport, an exception.
PURE = {
    "facts.accounts_of", "facts.dispatcher_of", "facts.opener_of", "facts.opener_role", "facts.queue_of",
    "facts.run_files_of", "facts.Moved", "records.named", "github.raw", "github.request", "github.tarball",
    "github.Unanswered", "identity.from_key", "identity.granted", "identity.permissions", "identity.jwt",
    "identity.mint", "identity.revoke", "seen.apps_of", "seen.identities", "seen.seen", "queue.Queuing",
    "effects.role_permits",
}
# What a Role's write takes is minted per Effect, from the Effect's own need (`harness/apply.py`), never by the step's
# read token; and the approving act's reads and its write go through the machine user's token, which no step mints.
ELSEWHERE = {"effects.Allowed", "effects.role_write", "effects.Approving", "effects.approve", "effects.approval_of",
             "effects.approver_of"}
# A function of the Harness that reads GitHub itself, through the transport it is given.
HARNESS_READS = {"harness.head.fetch": {"contents"}, "harness.head.tree": {"contents"}}


def imports(tree) -> dict:
    """Each name a module imports from the packages walked: a module by its dotted name, or a name of one, `m:name`."""
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in PACKAGES:
            for alias in node.names:
                names[alias.asname or alias.name] = "%s.%s" % (node.module, alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in PACKAGES:
            for alias in node.names:
                names[alias.asname or alias.name] = "%s:%s" % (node.module, alias.name)
    return names


def reached(dotted: str, function: str) -> set:
    """Each function of `adapters/`, `module.name`, and each Harness read `HARNESS_READS` names, that `function` of the
    module `dotted` can call, through the Harness's and the Controller's own functions and classes."""
    leaves, seen = set(), set()

    def walk(dotted, name):
        if (dotted, name) in seen:
            return
        seen.add((dotted, name))
        if "%s.%s" % (dotted, name) in HARNESS_READS:
            leaves.add("%s.%s" % (dotted, name))
            return
        path = ROOT / (dotted.replace(".", "/") + ".py")
        if not path.exists():
            return
        tree = ast.parse(path.read_text())
        names = imports(tree)
        defined = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        if name not in defined:
            return
        for node in ast.walk(defined[name]):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if isinstance(called, ast.Attribute) and isinstance(called.value, ast.Name) and called.value.id in names:
                target = names[called.value.id]
                if ":" in target:
                    continue
                if target.startswith("adapters."):
                    leaves.add("%s.%s" % (target.split(".", 1)[1], called.attr))
                else:
                    walk(target, called.attr)
            elif isinstance(called, ast.Name):
                if called.id in defined:
                    walk(dotted, called.id)
                elif called.id in names and ":" in names[called.id]:
                    module, imported = names[called.id].split(":")
                    if module.startswith("adapters."):
                        leaves.add("%s.%s" % (module.split(".", 1)[1], imported))
                    else:
                        walk(module, imported)
    walk(dotted, function)
    return leaves


def taken(leaf: str) -> set:
    return READS.get(leaf) or WRITES.get(leaf) or HARNESS_READS.get(leaf) or set()


# Each step that mints a token: its entry; the permissions it mints, from `config/apps.json` as the step mints them; and
# the reads it makes through another token than the one it mints, each with the token.
STEPS = {
    "the reader": (("harness.read", "step"),
                   lambda: read.wanted({"app": APPS["apps"]["reader"], "needs": APPS["needs"]}), {}),
    "apply's read again": (("harness.apply_step", "written"),
                           lambda: identity.granted(APPS["apps"]["pr-review"], APPS["needs"], apply.READS, "read"), {}),
    "the queue App's act": (("harness.queue_step", "written"),
                            lambda: identity.granted(APPS["apps"]["queue"], APPS["needs"], queue_step.NEEDS, "write"),
                            {"passes.find": "the job's own token, `GITHUB_TOKEN`, before any is minted"}),
    "the pass": (("controller.__main__", "main"),
                 lambda: pass_main.wanted({"app": APPS["apps"]["controller"], "needs": APPS["needs"]}), {}),
}
# What a step is owed, by the issue that holds it, while that step is not live: the queue App's act reads the pull
# request with no pull_requests grant, "queue_step mints no pull_requests read, and the queue App holds none" (#711).
# It is no exception once the Controller names the queue App's account: then the step is live, and held as any other.
OWED = {"the queue App's act": {("queue.pull", "pull_requests"), ("queue.queued", "pull_requests"),
                                ("queue.threads", "pull_requests")}}
CONTROLLER = json.loads((ROOT / "config" / "controller.json").read_text())


class TokenNeeds(unittest.TestCase):
    def test_every_read_a_step_can_reach_is_named(self):
        # A function of adapters/ no table names is a read no token was checked for: it is classed before it ships.
        for step, ((dotted, function), _, _) in STEPS.items():
            unknown = sorted(reached(dotted, function) - set(READS) - set(WRITES) - PURE - ELSEWHERE - set(HARNESS_READS))
            self.assertEqual(unknown, [], step)

    def test_each_step_mints_every_permission_its_reads_take(self):
        # Slice 1's third dry run stopped in apply as pause_unreadable: apply's token held no actions_variables for the
        # Pause its read again reads. Each step's token is held here to every read its code can reach.
        for step, ((dotted, function), minted, other) in STEPS.items():
            held = minted()
            missing = {(leaf, permission) for leaf in reached(dotted, function) - set(other)
                       for permission in taken(leaf) if permission not in held}
            owed = OWED.get(step, set()) if CONTROLLER["accounts"]["queue"] is None else set()
            self.assertEqual(sorted(missing - owed), [], step)
            # An owed gap that is closed is no longer owed: its exception is taken out with it.
            self.assertEqual(sorted(owed - missing), [], step)

    def test_the_walk_reaches_the_reads_each_step_is_known_to_make(self):
        # The walk is no check if it reaches nothing: each step reaches the reads its own code names.
        self.assertTrue({"passes.find", "facts.snapshot", "texts.issues", "harness.head.fetch"}
                        <= reached("harness.read", "step"))
        self.assertTrue({"passes.find", "facts.snapshot", "pause.read"} <= reached("harness.apply_step", "written"))
        self.assertTrue({"queue.pull", "queue.enqueue"} <= reached("harness.queue_step", "written"))
        self.assertTrue({"items.open_pull_requests", "facts.snapshot", "pause.read", "seen.read"}
                        <= reached("controller.__main__", "main"))

    def test_the_approving_act_mints_no_token(self):
        # Its reads and its one write go through the machine user's token, which the workflow gives it: no need of an
        # App's is minted, so there is none to hold here (harness/approve_step.py).
        self.assertNotIn("identity.from_key", reached("harness.approve_step", "written"))


if __name__ == "__main__":
    unittest.main()
