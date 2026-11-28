"""A Role's push, whole: every check it passes before its first write, then the reads and writes of one commit on the
Run's work branch, each asked of `guards/push.py` (issue 838; the Solution Architect's ruling 2 of 2026-11-28). It is
a composition of tested functions and decides nothing itself; nothing calls it until `apply`'s dispatch does, which
`tests/test_harness.py` pins.

`push(reader, sender, told)` gives `(landed, None)`, `guards/push.py`'s `landed` of the push, the commit it made and
the branch it was told (decisions 1207 and 1208), or `(None, code)` with nothing written past the step that refused.
`reader` is the token `apply` reads with, and `sender` the push's own, `adapters/push.py`'s `transport`. `told` is
`TOLD`: the repo; the work branch; the commit the Decision admitted, `parent`, and the branch's head it admitted, `head`, None at the first push; the commit's message; the
patch's bytes; and `judged`, None or the implementing Role's acceptance contract and where it was read, `(contract,
at)`.

The checks, in `harness/push_loop.py`'s `ORDER`, each only once all before it passed:
- `consumer`: the repo is the Factory's own, `config/controller.json`'s `home`, whose default branch it names
  (decision 0004; `guards/judged.py`'s `consumer`).
- `listed`: the list is read at the admitted commit and at the default branch's head, and the contract's paths added
  (decisions 0188, 0242 and 0025); the admitted tree is read and the patch applied to it, by a push that writes
  nothing; and `harness/apply.py`'s `push_refusal` is asked about every path that lands (`guards/push.py`'s `touched`).
- `base`: at the first push, the admitted commit is the default branch's head or an ancestor of it (decision 0242).
- `workflows`: the workflows at the default branch's head and at the admitted commit, which is the work branch's head
  after the first push, hold no command beside a secret that a work branch can start, by the default head's list
  (decision 0239, as decisions 1378, 1390 and 1391 narrow it).

Then the push of the changes: the branch, the commit and its tree read again, a blob of each written file, one tree,
read back, one commit, read back, and the branch made or moved, then read (`harness/push_loop.py`'s `land`). The
default branch's head is read again right before the branch's write, and refuses it where it moved, `BASE_MOVED`, so
no check read another base; and at the first push once more after it, where the admitted commit no longer stands on
it, `OFF_DEFAULT`, or the head moved, `BASE_MOVED`, with nothing landed (decision 0242). Its limits: the branch it made
then stays, and no draft is opened from it, which is the dispatch's; a branch moved names no old head to GitHub, which
takes no such lease, so a branch rewound between the read and the move is seen only by the read after it.
The patch is taken as told: that it is the bundle's, by its digest, and the token the push is sent by, are the
dispatch's. FR-14's rule on a test the admitted commit holds (`guards/push.py`'s `existing`) is the fix Intent's.
"""
from __future__ import annotations

import base64 as encoding
import json
import pathlib

from adapters import base, rules
from adapters import push as port
from guards import judged, patch, workflows
from guards import push as guard
from harness import apply, push_loop

TOLD = ("repo", "branch", "parent", "head", "message", "patch", "judged")
ROOT = pathlib.Path(__file__).resolve().parent.parent
# The default branch's head could not be read, or where the admitted commit stands on it: the port's.
BASE_UNREAD = "push_base_unread"
# At the first push, the admitted commit is no commit of the default branch's head, before the write or after it.
OFF_DEFAULT = "push_base_off_default"
# The default branch's head moved between the checks and the branch's write: the checks read another base.
BASE_MOVED = "push_base_moved"
BLOB = "blob"


def _home() -> dict:
    """The Factory's own repo and its default branch, as `config/controller.json` names them."""
    return json.loads((ROOT / "config" / "controller.json").read_text())["home"]


def _through(state, sender, told, *asks) -> tuple:
    """`(state, None)` once each of `asks`, given the state and giving a request, was sent by `push_loop.step`."""
    for ask in asks:
        state, why = push_loop.step(state, sender, told["repo"], told["branch"], ask(state))
        if why is not None:
            return None, why
    return state, None


def _read(state, sender, told) -> tuple:
    """`(changes, None)` by a push that writes nothing: the branch, the admitted commit, its tree and the bytes of each
    file the patch reads, read in turn, then the patch applied to them; or `(None, code)`."""
    repo = told["repo"]
    state, why = _through(state, sender, told, lambda _: port.read_branch(repo, told["branch"]),
                          lambda _: port.read_commit(repo, told["parent"]), lambda at: port.read_tree(repo, at["tree"]))
    if why is not None:
        return None, why
    listing, held, answers = state["before"], [state, None], {}
    paths, why = port.to_read(listing, patch.sources(told["patch"]))
    if why is not None:
        return None, why

    def blob(path):
        # One blob's read, asked of the guard and seen by it as `step` does, its answer kept for `read_whole`: once
        # for each blob, however many files share it, as the guard permits it.
        sha = listing["blobs"][path][0]
        if sha in answers:
            return answers[sha]
        req = port.read_blob(repo, sha)
        if held[1] is not None or req is None or not guard.permits(held[0], req["method"], req["path"], req["body"]):
            held[1] = held[1] or guard.NOT_PERMITTED
            return None
        answer = port.send(sender, repo, told["branch"], req)
        held[0], held[1] = guard.seen(held[0], req["method"], req["path"], req["body"], answer)
        answers[sha] = answer if held[1] is None else None
        return answers[sha]
    contents, why = port.read_whole(listing, paths, blob)
    if why is not None or held[1] is not None:
        return None, held[1] or why
    return patch.applied(told["patch"], listing["tree"], contents)


def _write(sender, told, changes) -> tuple:
    """`(state, None)` of the push of `changes` once its commit is read back, before the branch's write; or `(None,
    code)`."""
    repo, written = told["repo"], changes["written"]
    blobs = {path: encoding.b64encode(data).decode("ascii") for path, (_, data) in written.items()}
    pushed = {key: told[key] for key in guard.PUSH if key in told}
    state, why = guard.began(dict(pushed, changes=changes, blobs=blobs))
    if why is not None:
        return None, why

    def tree(state):
        entries = [{"path": path, "mode": mode, "type": BLOB, "sha": state["made"][path]} for path, (mode, _) in written.items()]
        removed = [{"path": path, "mode": state["before"]["tree"][path], "type": BLOB, "sha": None} for path in changes["removed"]]
        return port.make_tree(repo, state["tree"], entries + removed)
    asks = [lambda _: port.read_branch(repo, told["branch"]), lambda _: port.read_commit(repo, told["parent"]),
            lambda at: port.read_tree(repo, at["tree"])]
    asks += [lambda _, path=path: port.make_blob(repo, blobs[path]) for path in written]
    asks += [tree, lambda at: port.read_tree(repo, at["new"]),
             lambda at: port.make_commit(repo, told["message"], at["new"], told["parent"]),
             lambda at: port.read_commit(repo, at["commit"])]
    return _through(state, sender, told, *asks)


def push(reader, sender, told) -> tuple:
    """`(landed, None)` for a push that landed, or `(None, code)`: see the module's text."""
    if type(told) is not dict or set(told) != set(TOLD):
        return None, guard.NOT_PERMITTED
    reading, why = guard.began(dict({key: told[key] for key in guard.PUSH if key in told}, changes=None, blobs=None))
    if why is not None:
        return None, why
    repo, parent, first, got, home = told["repo"], told["parent"], told["head"] is None, {}, _home()

    def standing():
        if "base" not in got:
            got["base"] = base.on_default(reader, repo, parent)
        return got["base"]

    def listed():
        default = standing()[1]
        if default is None:
            return BASE_UNREAD
        patterns = []
        for sha in dict.fromkeys((default, parent)):
            said, why = rules.listed_at(reader, repo, sha)
            if why is not None:
                return why
            got.setdefault("list", said)
            patterns += said
        if told["judged"] is not None:
            said, why = judged.paths(*told["judged"]) if type(told["judged"]) is tuple and len(told["judged"]) == 2 \
                else (None, judged.UNREADABLE)
            if why is not None:
                return why
            patterns += said
        changes, why = _read(reading, sender, told)
        if why is not None:
            return why
        touched, why = guard.touched(changes)
        if why is not None:
            return why
        got["changes"] = changes
        return apply.push_refusal(touched[0], touched[1], sorted(set(patterns)))

    def on_base():
        case = standing()[0]
        return None if not first or case in base.GOES_ON else BASE_UNREAD if case is None else OFF_DEFAULT

    def secrets():
        for sha in dict.fromkeys((standing()[1], parent)):
            files, why = rules.workflows_at(reader, repo, sha)
            why = why or workflows.refusal_at(files, got["list"], home["branch"], home["repo"])
            if why is not None:
                return why
        return None
    why = push_loop.first((("consumer", lambda: judged.consumer(repo, home["repo"])), ("listed", listed),
                           ("base", on_base), ("workflows", secrets)))
    if why is not None:
        return None, why
    state, why = _write(sender, told, got["changes"])
    if why is not None:
        return None, why
    moved = base.on_default(reader, repo, parent)[1]
    if moved != got["base"][1]:
        return None, BASE_UNREAD if moved is None else BASE_MOVED
    make = port.make_branch if first else port.move_branch
    state, why = push_loop.land(state, sender, repo, told["branch"], make(repo, told["branch"], state["commit"]))
    if why is not None:
        return None, why
    case, after = base.on_default(reader, repo, parent) if first else (base.HEAD, moved)
    if case not in base.GOES_ON:
        return None, BASE_UNREAD if case is None else OFF_DEFAULT
    if after != got["base"][1]:
        return None, BASE_MOVED
    return guard.landed(state), None
