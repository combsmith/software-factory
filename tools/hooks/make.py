"""Run a make target for a hook, in the project or in one of its worktrees, and nowhere else.

A run leaves nothing behind (issue 344): it runs in a process group of its own, with a temporary
folder of its own as every temporary folder's root, and when it ends, runs out of time, or the hook
is told to end (SIGTERM, SIGHUP), the group is ended and the folder removed. A hook killed outright
cannot remove its folder, so each run first removes such folders older than STALE. The time a run is
given counts from when the hook asked, the sweep's time included.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import signal
import subprocess
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
TAIL = 40   # lines of output shown; the end of a run is where it says what failed
PREFIX = "sf-make-"     # the temporary folder of one run
STALE = 3600    # seconds; no run is given this long, so a folder this old is one a killed hook left
UNFINISHED = "`make %s` did not finish in %d seconds in %s."


def project(env: dict) -> pathlib.Path:
    """The project the session started in: its settings are what run these hooks."""
    return pathlib.Path(env.get("CLAUDE_PROJECT_DIR") or ROOT).resolve()


def tree(base: pathlib.Path, place):
    """Where make runs for `place`: the worktree under base/.claude/worktrees/ that holds it, or base. None outside both."""
    if not place:
        return None
    path, worktrees = pathlib.Path(place).resolve(), base / ".claude" / "worktrees"
    if worktrees in path.parents:
        return worktrees / path.relative_to(worktrees).parts[0]
    if path == base or base in path.parents:
        return None if path == worktrees else base
    return None


def tail(text: str, lines: int = TAIL) -> str:
    return "\n".join(text.rstrip("\n").split("\n")[-lines:])


def _make(env: dict):
    return shutil.which("make", path=env.get("PATH", os.defpath))


def temporary(env: dict) -> str:
    """Where the runs' temporary folders are made: the one the hook's environment names, as the run's would be."""
    return env.get("TMPDIR") or tempfile.gettempdir()


def sweep(env: dict, now: float) -> None:
    """Remove the folders of runs a killed hook left, older than STALE: a running one is never that old."""
    place = temporary(env)
    try:
        names = os.listdir(place)
    except OSError:
        return
    for name in names:
        path = os.path.join(place, name)
        try:
            if name.startswith(PREFIX) and os.path.isdir(path) and not os.path.islink(path) \
                    and now - os.lstat(path).st_mtime > STALE:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


class Ended(Exception):
    """The hook was told to end while its run was going."""


def _ended(signum, frame):
    raise Ended(signum)


def _hold() -> dict:
    """Have SIGTERM and SIGHUP end the run before the hook ends; the handlers they replace, to restore."""
    held = {}
    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            held[sig] = signal.signal(sig, _ended)
        except (ValueError, OSError):
            pass        # not the main thread: the hook's own run is always on it
    return held


def _end(child: subprocess.Popen) -> None:
    """End the run's whole process group, whatever it started, and reap it."""
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    child.communicate()


def make(target: str, where: pathlib.Path, env: dict, timeout: int, clock=time.time) -> tuple:
    """(passed, what to show). Without make, it did not pass, and says why in one sentence. Whatever the run makes
    under its temporary folder is removed when it ends, and so is every process it started."""
    exe = _make(env)
    if exe is None:
        return False, ("make is not on PATH, so `make %s` did not run in %s. Put make on PATH; the same checks "
                       "run without it as python3 -m tools.verify%s." % (target, where, " --fast" if target == "fast" else ""))
    asked = time.monotonic()
    sweep(env, clock())
    try:
        root = tempfile.mkdtemp(prefix=PREFIX, dir=temporary(env))
    except OSError as err:
        return False, "`make %s` could not start in %s: %s." % (target, where, err)
    child, held = None, _hold()
    try:
        try:
            child = subprocess.Popen([exe, target], cwd=str(where), env=dict(env, TMPDIR=root, TMP=root, TEMP=root),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     start_new_session=True)
        except OSError as err:
            return False, "`make %s` could not start in %s: %s." % (target, where, err)
        try:
            out, _ = child.communicate(timeout=max(1.0, timeout - (time.monotonic() - asked)))
        except subprocess.TimeoutExpired:
            return False, UNFINISHED % (target, timeout, where)
        return child.returncode == 0, tail(out)
    finally:
        if child is not None:
            _end(child)
        shutil.rmtree(root, ignore_errors=True)
        for sig, handler in held.items():
            signal.signal(sig, handler)


def lacks(target: str, where: pathlib.Path, env: dict) -> bool:
    """Whether make is there and the Makefile in `where` has no such target, as on a branch older than it."""
    exe = _make(env)
    if exe is None:
        return False
    try:
        done = subprocess.run([exe, "-n", target], cwd=str(where), env=env, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode != 0
