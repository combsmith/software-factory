"""Every step that mints a token mints it for every read and write its code can reach (slice 1's dry runs, the Factory
Builder's sweep of 2026-11-10). Each step's code is walked statically, from its entry, through every function and
class of `adapters/`, the Harness and the Controller that it calls, to each function that builds a request of
GitHub's itself. Each of those is named here by the permissions, and the levels, GitHub asks for its request, and the
step's token, minted from `config/apps.json` as the step mints it, must hold each one. A function the walk reaches
that builds a request no table names fails it, so a read added anywhere a step reaches is classed before it ships."""
from __future__ import annotations

import ast
import json
import pathlib
import unittest

from adapters import effects, identity
from controller import __main__ as pass_main
from harness import apply, queue_step, read

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = json.loads((ROOT / "config" / "apps.json").read_text())
CONTROLLER = json.loads((ROOT / "config" / "controller.json").read_text())
PACKAGES = ("adapters", "harness", "controller", "release")
READ, WRITE = {"level": "read"}, {"level": "write"}

# Each function that builds a request of GitHub's itself, by the permissions and levels its requests take, as GitHub's
# documentation names each endpoint's fine-grained permission.
R, W = "read", "write"
RAW = {
    "adapters.acceptance.closing": {"pull_requests": R, "issues": R},   # a pull request's closing issues
    "adapters.acceptance.labelled": {"issues": R},
    "adapters.artifacts._listed": {"actions": R}, "adapters.artifacts.read": {"actions": R},
    # The head's rollup, with each check suite's App and workflow run, and the pull request's place in the queue.
    "adapters.checks._read": {"pull_requests": R, "checks": R, "actions": R},
    "adapters.edits.last_edited_at": {"pull_requests": R},
    "adapters.effects._check": {"checks": W}, "adapters.effects._comment": {"pull_requests": W},
    "adapters.effects._review": {"pull_requests": W}, "adapters.effects._threads": {"pull_requests": R},
    "adapters.effects._dispatch": {"actions": W}, "adapters.effects.open_issues": {"issues": R},
    "adapters.effects.tracking": {"issues": W}, "adapters.effects.write_status": {"checks": W},
    # An installation's token, asked by the App's own key, and revoked by itself: no grant of the repo's.
    "adapters.identity.mint": {}, "adapters.identity.revoke": {},
    "adapters.items._page": {"pull_requests": R},
    "adapters.passes.find": {"actions": R}, "adapters.passes.records": {"actions": R},
    "adapters.passes.started": {"actions": R}, "adapters.passes.written": {"actions": R},
    # FACTORY_PAUSED, the repo's and the org's through the repo.
    "adapters.pause._org_value": {"actions_variables": R}, "adapters.pause._value": {"actions_variables": R},
    "adapters.pull.read": {"pull_requests": R}, "adapters.pull.base": {"contents": R},
    "adapters.pull.change": {"contents": R}, "adapters.pull.changed_paths": {"contents": R},
    "adapters.pull.diff": {"contents": R}, "adapters.pull.last_push": {"metadata": R},
    # The queue App's port: the pull request, its threads and its place in the queue, read before each write; and its
    # writes, as config/apps.json's needs name them.
    "adapters.queue.pull": {"pull_requests": R}, "adapters.queue.threads": {"pull_requests": R},
    "adapters.queue.queued": {"pull_requests": R}, "adapters.queue.enqueue": {"contents": W},
    "adapters.queue.dequeue": {"contents": W}, "adapters.queue.resolve": {"contents": W},
    "adapters.records._list": {"actions": R},
    "adapters.seen._check_runs": {"checks": R}, "adapters.seen._threads": {"pull_requests": R},
    "adapters.seen.pushes": {"metadata": R},
    "adapters.tags._ours": {"contents": R}, "adapters.tags._page": {"contents": R},
    "adapters.texts.issues": {"issues": R}, "adapters.threads._read": {"pull_requests": R},
    "adapters.timeline.Accounts": {"metadata": R},                     # a login's permission on the repo
    "adapters.timeline._content": {"contents": R},                     # a commit's content, compared with its base
    "adapters.timeline._pages": {"issues": R, "pull_requests": R},     # the timeline, and the reviews
    "harness.head.fetch": {"contents": R}, "harness.head.tree": {"contents": R},
}
# A request of GitHub's, built where it is sent: whatever function builds one reads or writes GitHub itself.
REQUESTS = {"request", "download", "tarball"}


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
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in PACKAGES:
                    names[alias.asname or alias.name] = alias.name
    return names


def reached(dotted: str, function: str) -> set:
    """Each function that builds a request of GitHub's itself, by its dotted name, that `function` of the module
    `dotted` can reach, through every function and class it calls of the packages walked."""
    leaves, seen = set(), set()

    def walk(dotted, name):
        if (dotted, name) in seen:
            return
        seen.add((dotted, name))
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
                module, function_ = (target.split(":")[0], "%s.%s" % (target.split(":")[1], called.attr)) \
                    if ":" in target else (target, called.attr)
            elif isinstance(called, ast.Name) and called.id in defined:
                module, function_ = dotted, called.id
            elif isinstance(called, ast.Name) and called.id in names and ":" in names[called.id]:
                module, function_ = names[called.id].split(":")
            else:
                continue
            if module == "adapters.github":
                if function_ in REQUESTS:
                    leaves.add("%s.%s" % (dotted, name))
                continue
            walk(module, function_.split(".")[0])      # a function, or the class whose method is called
    walk(dotted, function)
    return leaves


def taken(leaf: str) -> dict:
    """What `leaf` takes, `{permission: level}`."""
    return RAW.get(leaf, {})


def effects_minted() -> dict:
    """The Controller's token for its writes step, as `adapters/effects.controller_token` mints it: each of
    `CONTROLLER_NEEDS` the App is granted."""
    wanted = {}
    for name in effects.CONTROLLER_NEEDS:
        for permission, level in identity.granted(APPS["apps"]["controller"], APPS["needs"], [name], "write").items():
            wanted[permission] = max(wanted.get(permission, "read"), level, key=identity.LEVELS.index)
    return wanted


# Each step that mints a token: its entry; the permissions it mints, from `config/apps.json` as the step mints them; and
# the reads and writes it makes through another token than the one it mints, each with the token.
STEPS = {
    "the reader": (("harness.read", "step"),
                   lambda: read.wanted({"app": APPS["apps"]["reader"], "needs": APPS["needs"]}), {}),
    "apply's read again": (("harness.apply_step", "written"),
                           lambda: identity.granted(APPS["apps"]["pr-review"], APPS["needs"], apply.READS, "read"),
                           dict.fromkeys(("adapters.effects._check", "adapters.effects._comment", "adapters.effects._review",
                                          "adapters.effects._threads"),
                                         "each Effect's own token, minted from that Effect's need (harness/apply.py)")),
    "the queue App's act": (("harness.queue_step", "written"),
                            lambda: identity.granted(APPS["apps"]["queue"], APPS["needs"], queue_step.NEEDS, "write"),
                            dict.fromkeys(("adapters.passes.find", "adapters.artifacts._listed", "adapters.artifacts.read"),
                                          "the pass record, read through the job's own token, `GITHUB_TOKEN`, before any "
                                          "is minted")),
    "the pass": (("controller.__main__", "main"),
                 lambda: pass_main.wanted({"app": APPS["apps"]["controller"], "needs": APPS["needs"]}), {}),
    "the pass's writes": (("adapters.effects", "main"), effects_minted,
                          {"adapters.effects._dispatch": "the pass job's own token, `WORKFLOW_TOKEN`, with actions: write"}),
}
# What a step is owed, by the issue that holds it, while that step is not live: the queue App's act reads the pull
# request with no pull_requests grant, "queue_step mints no pull_requests read, and the queue App holds none" (#711).
# It is no exception once the Controller names the queue App's account: then the step is live, and held as any other.
OWED = {"the queue App's act": {("adapters.queue.pull", "pull_requests"), ("adapters.queue.queued", "pull_requests"),
                                ("adapters.queue.threads", "pull_requests")}}


def short(held: dict, leaf: str) -> set:
    """Each permission `leaf` takes that `held` does not hold at its level."""
    return {(leaf, permission) for permission, level in taken(leaf).items()
            if permission not in held or identity.LEVELS.index(held[permission]) < identity.LEVELS.index(level)}


class TokenNeeds(unittest.TestCase):
    def test_every_read_a_step_can_reach_is_named(self):
        # A function the walk reaches that no table names is a read no token was checked for: it is classed before it
        # ships, a request built outside adapters/ among them.
        for step, ((dotted, function), _, _) in STEPS.items():
            unknown = sorted(reached(dotted, function) - set(RAW))
            self.assertEqual(unknown, [], step)

    def test_each_step_mints_every_permission_its_reads_take(self):
        # Slice 1's third dry run stopped in apply as pause_unreadable: apply's token held no actions_variables for the
        # Pause its read again reads. Each step's token is held here to every read and write its code can reach, each at
        # its level.
        for step, ((dotted, function), minted, other) in STEPS.items():
            held = minted()
            missing = set().union(*[short(held, leaf) for leaf in reached(dotted, function) - set(other)])
            owed = OWED.get(step, set()) if CONTROLLER["accounts"]["queue"] is None else set()
            self.assertEqual(sorted(missing - owed), [], step)
            # An owed gap that is closed is no longer owed: its exception is taken out with it.
            self.assertEqual(sorted(owed - missing), [], step)

    def test_a_write_is_held_at_its_level(self):
        # A read grant is not a write's: the level is held, not the permission's name alone.
        self.assertEqual(short({"contents": "read"}, "adapters.queue.enqueue"), {("adapters.queue.enqueue", "contents")})
        self.assertEqual(short({"contents": "write"}, "adapters.queue.enqueue"), set())
        self.assertEqual(short({"contents": "write"}, "harness.head.fetch"), set())

    def test_the_walk_reaches_the_reads_each_step_is_known_to_make(self):
        # The walk is no check if it reaches nothing: each step reaches the reads its own code names, and a request built
        # in a step's own module is reached as that function's.
        self.assertTrue({"adapters.passes.find", "adapters.checks._read", "adapters.texts.issues", "harness.head.fetch"}
                        <= reached("harness.read", "step"))
        self.assertTrue({"adapters.passes.find", "adapters.checks._read", "adapters.pause._value"}
                        <= reached("harness.apply_step", "written"))
        self.assertTrue({"adapters.queue.pull", "adapters.queue.enqueue"} <= reached("harness.queue_step", "written"))
        self.assertTrue({"adapters.items._page", "adapters.checks._read", "adapters.pause._value",
                         "adapters.seen._check_runs"} <= reached("controller.__main__", "main"))
        self.assertTrue({"adapters.pause._value", "adapters.effects.open_issues", "adapters.effects.write_status"}
                        <= reached("adapters.effects", "main"))

    def test_the_approving_act_mints_no_token(self):
        # Its reads and its one write go through the machine user's token, which the workflow gives it: no App's token is
        # minted, by from_key or by mint itself, so there is none to hold here (harness/approve_step.py).
        self.assertNotIn("adapters.identity.mint", reached("harness.approve_step", "written"))
        self.assertIn("adapters.identity.mint", reached("harness.read", "step"))     # as the reader's step mints one


if __name__ == "__main__":
    unittest.main()
