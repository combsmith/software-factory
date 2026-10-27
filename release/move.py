"""The release workflow's steps (rulings 4′ and 5′): a step's plan from what was read, and the step itself.

    python3 -m release.move plan < READS
    python3 -m release.move

`plan`: READS, on standard input, is one JSON object: `step`, the step asked (`release/cut.py`'s), `refs`, the refs
`adapters/tags.py` read, and `facts`, the facts of the commit asked about. It opens no path it is given (SonarCloud's
S2083 and S8707), as `tools/redact_trial.py` opens none. It prints `{"writes": [...]}` and exits 0, or
`{"refused": code}` and exits 1, and writes nothing. Reads that cannot be read are refused, `step_unreadable`.

The step, with no argument, is the release job's one step after the token's mint and the checkout. It is given its
inputs by its environment: `RELEASE_COMMAND` (`cut`, `move` or `rollback`), `RELEASE_VERSION` and `RELEASE_CUT_COMMIT`
for a cut (a cut asked with no version is of the next patch of `next`'s major, as the schedule asks one), `RELEASE_TO`
for a move or a rollback, and `RELEASE_TOKEN`, the release App's token. Through that token alone it reads the
`factory/` tags, and, but for a rollback, the commit's facts (`adapters/candidate.py`); plans; sends each write and
reads the tags again after it, once more if need be, stopping at the first not read back on its commit as the one
Release planned; and records a Deployment of each move of `next` once read back. A rollback reads no fact and passes
no gate, so it works while the Factory is broken. It prints what it did, by codes alone, and exits 0, or 1 with the
code that stopped it. Nothing here reads a file at any tag.

The Channels a step may move are those `release/rings.json` declares, and `next` is the one a step moves.
"""
from __future__ import annotations

import json
import pathlib
import sys

from release import current, cut

ROOT = pathlib.Path(__file__).resolve().parent.parent
RINGS = ROOT / "release" / "rings.json"
CONTROLLER = ROOT / "config" / "controller.json"
USAGE = "usage: python3 -m release.move plan < READS, or python3 -m release.move"
COMMANDS = ("cut", "move", "rollback")
READ = object()       # read the Release's own file


def _json(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def channels(rings) -> frozenset:
    """The Channels the ring file declares, by tag; none when it cannot be read."""
    found = rings.get("channels") if isinstance(rings, dict) else None
    if not isinstance(found, dict) or not all(isinstance(c, dict) for c in found.values()):
        return frozenset()
    return frozenset(c.get("tag") for c in found.values())


def next_channel(rings):
    """The tag of `next`, as the ring file declares it, or None."""
    found = rings.get("channels") if isinstance(rings, dict) else None
    tag = (found.get("next") or {}).get("tag") if isinstance(found, dict) and isinstance(found.get("next"), dict) else None
    return tag if current.channel(tag) else None


def home(controller):
    """The repo the Factory's own Releases are tags of: the Controller's home."""
    found = (controller.get("home") or {}).get("repo") if isinstance(controller, dict) else None
    return found if isinstance(found, str) else None


def asked(environ: dict, channel) -> dict:
    """The step `RELEASE_COMMAND` asks for, from the job's environment; a command not known is asked as given."""
    command = environ.get("RELEASE_COMMAND")
    if command == "cut":
        return {"command": "cut", "channel": channel, "version": environ.get("RELEASE_VERSION"),
                "commit": environ.get("RELEASE_CUT_COMMIT")}
    return {"command": command, "channel": channel, "to": environ.get("RELEASE_TO") or None}


def branch(controller) -> str:
    """The branch a Release is cut from: the Controller's home branch."""
    found = (controller.get("home") or {}).get("branch") if isinstance(controller, dict) else None
    return found if isinstance(found, str) else "main"


def _named(after, write, released) -> bool:
    """Whether the refs read after `write` hold it: its name on its commit, and that commit one Release's, `released`."""
    return after is not None and after.get(write[1]) == write[2] and current.resolve(write[2], after) == released


def run(environ: dict, connect, rings=READ, controller=READ) -> tuple:
    """`(done, None)` for the step the environment asks, sent and read back, or `(done, code)` with what was done before
    the code that stopped it. `connect` makes the transport from the token."""
    from adapters import candidate, deployments, tags
    rings = _json(RINGS) if rings is READ else rings
    controller = _json(CONTROLLER) if controller is READ else controller
    repo, channel = home(controller), next_channel(rings)
    token = environ.get("RELEASE_TOKEN")
    done = {"writes": [], "deployments": []}
    if environ.get("RELEASE_COMMAND") not in COMMANDS or repo is None or channel is None:
        return done, cut.STEP_UNREADABLE
    if not isinstance(token, str) or not token:
        return done, "token_unreadable"
    try:
        transport = connect(token)
    except Exception:      # a token the transport refuses: nothing was asked, and nothing of it is said
        return done, "token_unreadable"
    refs = tags.read(transport, repo)
    if refs is None:
        return done, "refs_unreadable"
    step = asked(environ, channel)
    if step["command"] == "cut" and not step["version"]:
        step["version"] = cut.next_version(channel, refs)      # the schedule's cut, which names no version
    if step["command"] == "rollback":
        facts = {}
    else:
        name = step["version"] if step["command"] == "cut" else step["to"]
        commit = step["commit"] if step["command"] == "cut" else refs.get(step["to"])
        facts = candidate.facts(transport, repo, commit, name, branch(controller))
    writes, refused = cut.plan(step, refs, facts, channels(rings))
    if refused:
        return done, refused
    # The Release every write is of: the version cut, or the one the Channel moves to, by the refs read before.
    released = writes[0][1] if writes[0][0] == "create" else current.resolve(writes[0][2], refs)
    for write in writes:
        if not tags.write(transport, repo, write, refs):
            return done, "write_unanswered"
        after = tags.read(transport, repo)
        if not _named(after, write, released):
            after = tags.read(transport, repo)      # once more, for a read that had not yet caught up with the write
        if not _named(after, write, released):
            done["sent"] = list(write)
            return done, "not_read_back"
        refs = after
        done["writes"].append(list(write))
        if write[0] == "move":
            ident = deployments.record(transport, repo, write[2], released)
            if ident is None:
                return done, "deployment_unrecorded"
            done["deployments"].append(ident)
    return done, None


def main(argv, stdin=None, rings=RINGS, environ=None, connect=None) -> int:
    if list(argv) in ([], ["step"]):
        if connect is None:
            from adapters.github import Live
            connect = Live
        try:
            done, refused = run(dict(environ if environ is not None else {}), connect, _json(rings))
        except Exception:      # one code, and no traceback, which could quote what GitHub answered
            done, refused = {"writes": [], "deployments": []}, "step_failed"
        print(json.dumps(dict(done, refused=refused) if refused else done))
        return 1 if refused else 0
    if list(argv) != ["plan"]:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        reads = json.loads((sys.stdin if stdin is None else stdin).read())
    except ValueError:
        reads = None
    reads = reads if isinstance(reads, dict) else {}
    writes, refused = cut.plan(reads.get("step"), reads.get("refs"), reads.get("facts"), channels(_json(rings)))
    if refused:
        print(json.dumps({"refused": refused}))
        return 1
    print(json.dumps({"writes": [list(write) for write in writes]}))
    return 0


if __name__ == "__main__":
    import os
    sys.exit(main(sys.argv[1:], environ=dict(os.environ)))
