"""The push loop's own pieces, each a tested function that `harness/push.py`, not built yet, composes (issue 838; the
Solution Architect's ruling 2 of 2026-11-28). They decide nothing: what may leave, and what an answer must say, is
`guards/push.py`'s; each request is built by `adapters/push.py` and sent by its `send`.

- `step(state, sender, repo, branch, req)`: one request of a push. It is asked of the guard's `permits` unchanged, sent
  unchanged by the push's own sender, `adapters/push.py`'s `transport`, and its answer given to `seen`. A tree's answer
  goes through the port's `listed` first, at the tree its path names: no answer there is the port's
  `push_tree_unfetched`. `(state, None)`, or `(None, code)`: `NOT_PERMITTED`, sending nothing, for a request that may
  not leave, one with a key `request` never gives, or a repo and branch not the push's own; otherwise the guard's or
  the port's code, `UNANSWERED` among them for what `send` will not send.
- `land(state, sender, repo, branch, write)`: the branch's write, made or moved, then the branch read once more, by
  `step` both. The read says whether the push landed at the commit it made; after a 422 it says whose the refusal was,
  moved or a person's (decision 1253). A write the guard refuses reads nothing.
- `first(checks)`: the first code of the checks a push passes before its first write, asked in `ORDER` and each only
  once every one before it passed; None where all pass. `checks` is `(name, check)` pairs, read once into a tuple, each
  `check` callable, taking nothing and giving a code or None. Pairs in another order, one missing or one more, or a
  check that cannot be called, give `NOT_PERMITTED` and ask none: a loop that skipped a check is the Factory's own
  fault, a person's. A check that gives anything but None or a code, lowercase words joined by `_`, gives
  `NOT_PERMITTED` too, so no sentence is a reason.

Its limits: what each check reads, and which push it refuses, is the check's own; this holds only their order and
that none is skipped. Which request comes next, the reads and writes of a push in turn, is `harness/push.py`'s, held
by the guard's `permits`.
"""
from __future__ import annotations

import re

from adapters import push as port
from guards import push as guard

# The checks a push passes before its first write, in the order they are asked: the repo is the Factory's own
# (decision 0004); the patch's paths are held to the base's list at both commits (decisions 0188, 0242); the admitted
# commit stands on the default branch (decision 0242); and the workflows read again hold no command beside a secret
# that a work branch can start (decision 0239, as pull request 1378 narrows it).
ORDER = ("consumer", "listed", "base", "workflows")
TREES = "/git/trees/"
GET = "GET"
CODE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


def _request(req) -> bool:
    """Whether `req` is a request in the shape `adapters/github.py`'s `request` gives: a method, a path and a body."""
    return type(req) is dict and set(req) <= port.REQUEST and type(req.get("method")) is str \
        and type(req.get("path")) is str and "body" in req


def step(state, sender, repo, branch, req) -> tuple:
    """`(state, None)` after one request of a push, asked of `permits`, sent and seen; or `(None, code)`."""
    if not _request(req) or not guard.permits(state, req["method"], req["path"], req["body"]) \
            or [repo, branch] != [state["push"]["repo"], state["push"]["branch"]]:
        return None, guard.NOT_PERMITTED
    trees = "/repos/" + repo + TREES
    answer = port.send(sender, repo, branch, req)
    if req["method"] == GET and req["path"].startswith(trees):
        answer, why = port.listed(answer, req["path"][len(trees):len(trees) + len(guard.SHA)])
        if why is not None:
            return None, why
    return guard.seen(state, req["method"], req["path"], req["body"], answer)


def land(state, sender, repo, branch, write) -> tuple:
    """`(state, None)` once the branch's write and the branch read after it are seen, or `(None, code)`."""
    state, why = step(state, sender, repo, branch, write)
    if why is not None:
        return None, why
    return step(state, sender, repo, branch, port.read_branch(repo, branch))


def first(checks):
    """The first code among `checks`, asked in `ORDER`, each once all before it passed; or None where every one passes."""
    checks = tuple(checks) if type(checks) in (list, tuple) else ()
    if [type(pair) is tuple and len(pair) == 2 and type(pair[0]) is str and pair[0] for pair in checks] != list(ORDER) \
            or not all(callable(check) for _, check in checks):
        return guard.NOT_PERMITTED
    for _, check in checks:
        why = check()
        if why is not None:
            return why if type(why) is str and CODE.fullmatch(why) else guard.NOT_PERMITTED
    return None
