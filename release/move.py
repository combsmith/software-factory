"""The release workflow's steps (rulings 4′ and 5′): a step's plan from what was read, and the step itself.

    python3 -m release.move plan < READS
    python3 -m release.move step

`plan`: READS, on standard input, is one JSON object: `step`, the step asked (`release/cut.py`'s), `refs`, the refs
`adapters/tags.py` read, and `facts`, the facts of the commit asked about. It opens no path it is given (SonarCloud's
S2083 and S8707), as `tools/redact_trial.py` opens none. It prints `{"writes": [...]}` and exits 0, or
`{"refused": code}` and exits 1, and writes nothing. Reads that cannot be read are refused, `step_unreadable`.

`step`, the release job's one step after the token's mint and the checkout, is given its inputs by its environment:
`RELEASE_COMMAND` (`cut`, `move` or `rollback`), `RELEASE_VERSION` and `RELEASE_COMMIT` for a cut, `RELEASE_TO` for a
move or a rollback, and `RELEASE_TOKEN`, the release App's token. Through that token alone it reads the `factory/`
tags, and, but for a rollback, the commit's facts (`adapters/candidate.py`); plans; sends each write and reads the
tags again after it, stopping at the first that is not read back on its commit; and records a Deployment of each move of
`next` once read back. A rollback reads no fact and passes no gate, so it works while the Factory is broken. It prints
what it did, by codes alone, and exits 0, or 1 with the code that stopped it. Nothing here reads a file at any tag.

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
USAGE = "usage: python3 -m release.move plan < READS, or python3 -m release.move step"
COMMANDS = ("cut", "move", "rollback")


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
                "commit": environ.get("RELEASE_COMMIT")}
    return {"command": command, "channel": channel, "to": environ.get("RELEASE_TO") or None}


def run(environ: dict, connect, rings=None, controller=None) -> tuple:
    """`(done, None)` for the step the environment asks, sent and read back, or `(done, code)` with what was done before
    the code that stopped it. `connect` makes the transport from the token."""
    from adapters import candidate, deployments, tags
    rings = _json(RINGS) if rings is None else rings
    repo, channel = home(_json(CONTROLLER) if controller is None else controller), next_channel(rings)
    token = environ.get("RELEASE_TOKEN")
    done = {"writes": [], "deployments": []}
    if environ.get("RELEASE_COMMAND") not in COMMANDS or repo is None or channel is None:
        return done, cut.STEP_UNREADABLE
    if not isinstance(token, str) or not token:
        return done, "token_unreadable"
    transport = connect(token)
    refs = tags.read(transport, repo)
    if refs is None:
        return done, "refs_unreadable"
    step = asked(environ, channel)
    if step["command"] == "rollback":
        facts = {}
    else:
        name = step["version"] if step["command"] == "cut" else step["to"]
        commit = step["commit"] if step["command"] == "cut" else refs.get(step["to"])
        facts = candidate.facts(transport, repo, commit, name)
    writes, refused = cut.plan(step, refs, facts, channels(rings))
    if refused:
        return done, refused
    for write in writes:
        released = current.resolve(write[2], refs) if write[0] == "move" else write[1]
        if not tags.write(transport, repo, write, refs):
            return done, "write_unanswered"
        after = tags.read(transport, repo)
        if after is None or after.get(write[1]) != write[2]:
            return done, "not_read_back"
        refs = after
        done["writes"].append(list(write))
        if write[0] == "move":
            released = released or current.resolve(write[2], refs)
            ident = deployments.record(transport, repo, write[2], released)
            if ident is None:
                return done, "deployment_unrecorded"
            done["deployments"].append(ident)
    return done, None


def main(argv, stdin=None, rings=RINGS, environ=None, connect=None) -> int:
    if list(argv) == ["step"]:
        if connect is None:
            from adapters.github import Live
            connect = Live
        done, refused = run(dict(environ if environ is not None else {}), connect, _json(rings))
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
