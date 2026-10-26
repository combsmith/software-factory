"""What every step of a Run's jobs shares: its files and its exit. A step reads and writes only inside the directory it
runs in, each path followed to where it really is; it writes into a folder of its own that did not exist, each file
made new, its own user's alone to read; and it prints one code and exits 1 when it cannot go on, and nothing else, since
an error's message could quote what GitHub or the model answered (section 3.10)."""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

from release import current


class Stop(Exception):
    """A step that cannot go on, by its code alone."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def inside(base, path: str) -> str:
    """`path` as it really is, held inside `base`, or Stop `path_outside`."""
    root = os.path.realpath(str(base))
    real = os.path.realpath(os.path.join(root, path)) if isinstance(path, str) and path else None
    if real is None or not real.startswith(root + os.sep):
        raise Stop("path_outside")
    return real


def new_folder(base, path: str) -> str:
    """A folder made for this step alone, inside `base`; Stop `out_exists` if anything is there, a link among them."""
    real = inside(base, path)
    if os.path.lexists(os.path.join(os.path.realpath(str(base)), path)):
        raise Stop("out_exists")
    os.mkdir(real, 0o700)
    return real


def write(folder: str, name: str, data) -> None:
    """One new file in the step's folder: JSON for a document, the bytes as they are for bytes."""
    if isinstance(data, (bytes, bytearray)):
        body = bytes(data)
    else:
        body = (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    made = os.open(os.path.join(folder, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with open(made, "wb") as f:
        f.write(body)


def read_json(base, path: str):
    """A JSON document inside `base`; Stop `file_unreadable` if it cannot be read as one."""
    try:
        with open(inside(base, path), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        raise Stop("file_unreadable") from None


# The Run's three inputs, as the workflow hands each step them: in its environment, never on its command line, which
# holds `python3 -m <module>` and nothing else (`tools/check_workflows.py`'s `install`).
INPUTS = ("NAME", "ITEM", "PASS")


def given(argv: list, environ: dict, inputs: tuple, folders: tuple) -> list:
    """The step's arguments: those on its command line, or, with none, the workflow's form: each of `inputs` from the
    environment, then its folders by their fixed names."""
    return list(argv) if argv else [environ.get(name) for name in inputs] + list(folders)


HEAD = "HEAD"      # the commit checked out, as git names it: every tag `--points-at` lists is on it
SHA = re.compile(r"[0-9a-f]{40}")
GIT_ENV = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}


def _git(args: list, root, run) -> str:
    try:
        done = run(["git"] + args, cwd=str(root), capture_output=True, text=True, timeout=30, env=GIT_ENV, check=False)
    except (OSError, subprocess.SubprocessError):
        raise Stop("release_unreadable") from None
    if done.returncode != 0:
        raise Stop("release_unreadable")
    return done.stdout


def release(root=None, run=subprocess.run) -> str:
    """The Release this step runs as: the one Release tag on the commit checked out, read from the checkout's own tags,
    `git tag --points-at HEAD`, and named by `release/current.py`'s rules (#197's rulings 7 and 11), the one place they
    are written. The Channel's tag on the same commit is never one; none is `release_untagged`, and two refuse,
    `release_twice`, rather than pick. Each step that needs the name calls this, its one entry point, before it reads
    any key."""
    listed = _git(["tag", "--points-at", HEAD], ROOT if root is None else root, run).splitlines()
    refs = {line.strip(): HEAD for line in listed if line.strip()}
    found = current.resolve(HEAD, refs)
    if found is None:
        raise Stop("release_twice" if sum(1 for name in refs if current.version(name)) > 1 else "release_untagged")
    return found


def commit(root=None, run=subprocess.run) -> str:
    """The commit checked out, which each later job of the Run checks out exactly, so that every job runs one Release."""
    sha = _git(["rev-parse", "HEAD"], ROOT if root is None else root, run).strip()
    if not SHA.fullmatch(sha):
        raise Stop("release_unreadable")
    return sha


def run(step, *given) -> int:
    """A step's exit: 0 and its line on success, else 1 and its one code; whatever it raised is never printed."""
    try:
        said = step(*given)
    except Stop as stop:
        print(stop.code)
        return 1
    except Exception:       # a message could quote what GitHub or the model answered: a code alone
        print("step_failed")
        return 1
    print(said)
    return 0


def exit_with(step, *given) -> None:
    sys.exit(run(step, *given))


def handed_on(environ: dict) -> str:
    """`python3 -m harness.steps`, a workflow's first job's step after its checkout of the Channel: the commit it got,
    as the step's output `commit`, which every later job checks out."""
    sha = commit()
    with open(environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("commit=%s\n" % sha)
    return "commit %s" % sha


ROOT = pathlib.Path(__file__).resolve().parent.parent


if __name__ == "__main__":
    exit_with(handed_on, dict(os.environ))
