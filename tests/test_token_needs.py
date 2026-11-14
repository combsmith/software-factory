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
import tempfile
import unittest
import unittest.mock

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
    "adapters.items.open_pull_requests": {"pull_requests": R}, "adapters.items.open_issues": {"issues": R},
    "adapters.issues.own": {"issues": R}, "adapters.issues.edits": {"issues": R},  # an issue, and its edits by GraphQL
    "adapters.passes.find": {"actions": R}, "adapters.passes.records": {"actions": R},
    "adapters.passes.started": {"actions": R}, "adapters.passes.written": {"actions": R},
    # FACTORY_PAUSED, the repo's and the org's through the repo.
    "adapters.pause._org_value": {"actions_variables": R}, "adapters.pause._value": {"actions_variables": R},
    "adapters.pull.read": {"pull_requests": R}, "adapters.pull.base": {"contents": R},
    "adapters.pull.change": {"contents": R}, "adapters.pull.changed_paths": {"contents": R},
    "adapters.pull.diff": {"contents": R},
    "adapters.pull.last_push": {"contents": R},                        # a branch's activity (decision 0048, P-47)
    # The queue App's port: the pull request, its threads and its place in the queue, read before each write; and its
    # writes, as config/apps.json's needs name them.
    "adapters.queue.pull": {"pull_requests": R}, "adapters.queue.threads": {"pull_requests": R},
    "adapters.queue.queued": {"pull_requests": R}, "adapters.queue.enqueue": {"contents": W},
    "adapters.queue.dequeue": {"contents": W}, "adapters.queue.resolve": {"contents": W},
    "adapters.records._began": {"actions": R},                         # a run's jobs, for when it began (0193)
    "adapters.records._list": {"actions": R},
    "adapters.rules._file_at": {"contents": R},                        # a file at the base: what a push may not touch
    "adapters.seen._check_runs": {"pull_requests": R, "checks": R},    # the pull request's head, then its checks
    "adapters.seen._threads": {"pull_requests": R},
    "adapters.seen.pushes": {"contents": R},                           # the repo's activity, as P-47 reads a branch's
    "adapters.tags._ours": {"contents": R}, "adapters.tags._page": {"contents": R},
    "adapters.texts.issues": {"issues": R}, "adapters.threads._read": {"pull_requests": R},
    "adapters.timeline.Accounts": {"metadata": R},                     # a login's permission on the repo
    "adapters.timeline._content": {"contents": R},                     # a commit's content, compared with its base
    "adapters.timeline._pages": {"issues": R, "pull_requests": R},     # the timeline, and the reviews
    "harness.head.fetch": {"contents": R}, "harness.head.tree": {"contents": R},
}
# How many requests each of those builds itself: one more, in a function already classed, is classed again first.
SITES = {
    "adapters.acceptance.closing": 1,
    "adapters.acceptance.labelled": 1,
    "adapters.artifacts._listed": 1,
    "adapters.artifacts.read": 1,
    "adapters.checks._read": 1,
    "adapters.edits.last_edited_at": 1,
    "adapters.effects._check": 3,
    "adapters.effects._comment": 3,
    "adapters.effects._dispatch": 1,
    "adapters.effects._review": 3,
    "adapters.effects._threads": 1,
    "adapters.effects.open_issues": 1,
    "adapters.effects.tracking": 3,
    "adapters.effects.write_status": 3,
    "adapters.identity.mint": 2,
    "adapters.identity.revoke": 1,
    "adapters.issues.edits": 1,
    "adapters.issues.own": 1,
    "adapters.items.open_issues": 1,
    "adapters.items.open_pull_requests": 1,
    "adapters.passes.find": 1,
    "adapters.passes.records": 1,
    "adapters.passes.started": 1,
    "adapters.passes.written": 1,
    "adapters.pause._org_value": 1,
    "adapters.pause._value": 1,
    "adapters.pull.base": 1,
    "adapters.pull.change": 1,
    "adapters.pull.changed_paths": 1,
    "adapters.pull.diff": 1,
    "adapters.pull.last_push": 1,
    "adapters.pull.read": 1,
    "adapters.queue.dequeue": 1,
    "adapters.queue.enqueue": 1,
    "adapters.queue.pull": 1,
    "adapters.queue.queued": 1,
    "adapters.queue.resolve": 1,
    "adapters.queue.threads": 1,
    "adapters.records._began": 1,
    "adapters.records._list": 1,
    "adapters.rules._file_at": 1,
    "adapters.seen._check_runs": 2,
    "adapters.seen._threads": 1,
    "adapters.seen.pushes": 1,
    "adapters.tags._ours": 1,
    "adapters.tags._page": 1,
    "adapters.texts.issues": 1,
    "adapters.threads._read": 1,
    "adapters.timeline.Accounts": 1,
    "adapters.timeline._content": 1,
    "adapters.timeline._pages": 1,
    "harness.head.fetch": 1,
    "harness.head.tree": 1,
}
# Every request the approving act can reach, through the machine user's token: one more, a mint among them, is seen.
APPROVING = [
    "adapters.acceptance.closing",
    "adapters.acceptance.labelled",
    "adapters.artifacts._listed",
    "adapters.artifacts.read",
    "adapters.checks._read",
    "adapters.edits.last_edited_at",
    "adapters.effects._open_at",
    "adapters.effects.approval_of",
    "adapters.effects.approve",
    "adapters.effects.approver_of",
    "adapters.passes.find",
    "adapters.pause._org_value",
    "adapters.pause._value",
    "adapters.pull.base",
    "adapters.pull.changed_paths",
    "adapters.pull.diff",
    "adapters.pull.last_push",
    "adapters.pull.read",
    "adapters.records._began",
    "adapters.records._list",
    "adapters.threads._read",
    "adapters.timeline.Accounts",
    "adapters.timeline._content",
    "adapters.timeline._pages",
]
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
                    # `import a.b` binds `a`, through which `a.b.f` is reached; `import a.b as c` binds `c` to `a.b`.
                    names[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
    return names


def dotted_name(node) -> list:
    """`a.b.c` as `["a", "b", "c"]`, for a name and the attributes on it; empty for anything else."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.insert(0, node.attr)
        node = node.value
    return [node.id] + parts if isinstance(node, ast.Name) else []


def resolve(module: str, rest: list) -> tuple:
    """`(module, name)` for `module.rest...`: the deepest module of the packages walked the dotted name holds, and the
    function or class named after it."""
    for depth in range(len(rest), -1, -1):
        candidate = ".".join([module] + rest[:depth])
        if (ROOT / (candidate.replace(".", "/") + ".py")).exists() and depth < len(rest):
            return candidate, ".".join(rest[depth:])
    return module, ".".join(rest)


def requests_in(dotted: str, name: str) -> int:
    """How many requests of GitHub's `name` of the module `dotted` builds itself, in its own body."""
    tree = ast.parse((ROOT / (dotted.replace(".", "/") + ".py")).read_text())
    names = imports(tree)
    defined = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    count = 0
    for node in ast.walk(defined[name]):
        if not isinstance(node, ast.Call):
            continue
        chain = dotted_name(node.func)
        if not chain or chain[0] not in names:
            continue
        target = names[chain[0]]
        if ":" in target:
            module, function_ = target.split(":")[0], ".".join([target.split(":")[1]] + chain[1:])
        else:
            module, function_ = resolve(target, chain[1:])
        count += module == "adapters.github" and function_ in REQUESTS
    return count


def reached(dotted: str, function: str) -> set:
    """Each function that builds a request of GitHub's itself, by its dotted name, that `function` of the module
    `dotted` can reach, through every function and class it calls of the packages walked."""
    leaves, seen = set(), set()

    def follow(dotted, name):
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
            chain = dotted_name(called)
            if isinstance(called, ast.Attribute) and chain and chain[0] in names:
                target = names[chain[0]]
                if ":" in target:
                    module, function_ = target.split(":")[0], ".".join([target.split(":")[1]] + chain[1:])
                else:
                    module, function_ = resolve(target, chain[1:])
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
            follow(module, function_.split(".")[0])      # a function, or the class whose method is called
    follow(dotted, function)
    return leaves


def taken(leaf: str) -> dict:
    """What `leaf` takes, `{permission: level}`."""
    return RAW.get(leaf, {})


def effects_minted() -> dict:
    """The Controller's token for its writes step, as `adapters/effects.controller_token` asks the mint for it, observed
    at the mint, never worked out beside it."""
    asked = []
    with unittest.mock.patch.object(effects.identity, "from_key",
                                    lambda app, repo, wanted, key, now, connect: asked.append(wanted) or ("t", None)):
        effects.controller_token({"CONTROLLER_APP_KEY": "a key"}, {"home": {"repo": "combsmith/software-factory"}}, 0)
    (wanted,) = asked
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

    def test_each_classed_function_builds_the_requests_it_was_classed_for(self):
        # A request added inside a function already classed is seen: the count of requests it builds is pinned, so the
        # function is classed again before its new request ships.
        self.assertEqual(set(SITES), set(RAW))
        for leaf, count in SITES.items():
            module, name = leaf.rsplit(".", 1)
            self.assertEqual(requests_in(module, name), count, leaf)

    def test_a_request_through_a_dotted_import_is_reached(self):
        # `import adapters.github` and `adapters.github.request(...)` is reached as the request it builds.
        with tempfile.TemporaryDirectory() as folder, unittest.mock.patch(__name__ + ".ROOT", pathlib.Path(folder)):
            for package in ("adapters", "harness"):
                pathlib.Path(folder, package).mkdir()
            pathlib.Path(folder, "adapters", "github.py").write_text("")
            pathlib.Path(folder, "harness", "probe.py").write_text(
                "import adapters.github\n\n\ndef step(transport):\n"
                "    return transport.send(adapters.github.request(\"GET\", \"/repos/a/b/actions/secrets\"))\n")
            self.assertEqual(reached("harness.probe", "step"), {"harness.probe.step"})
            self.assertEqual(requests_in("harness.probe", "step"), 1)

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
        self.assertTrue({"adapters.items.open_pull_requests", "adapters.items.open_issues", "adapters.issues.own", "adapters.checks._read", "adapters.pause._value",
                         "adapters.seen._check_runs"} <= reached("controller.__main__", "main"))
        self.assertTrue({"adapters.pause._value", "adapters.effects.open_issues", "adapters.effects.write_status"}
                        <= reached("adapters.effects", "main"))

    def test_the_approving_act_mints_no_token(self):
        # Its reads and its one write go through the machine user's token, which the workflow gives it: no App's token is
        # minted, by from_key or by mint itself, so there is none to hold here (harness/approve_step.py).
        # Every request it makes is pinned, so a new one, a mint among them, fails here.
        self.assertEqual(sorted(reached("harness.approve_step", "written")), APPROVING)
        self.assertIn("adapters.identity.mint", reached("harness.read", "step"))     # as the reader's step mints one


if __name__ == "__main__":
    unittest.main()
