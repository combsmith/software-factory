"""Run a make target for a hook, in the project or in one of its worktrees, and nowhere else.

A run leaves nothing behind (issue 344): it runs in a process group of its own, with a temporary
folder of its own as every temporary folder's root, and when it ends, runs out of time, or the hook
is told to end (SIGTERM, SIGHUP), the group is ended and the folder removed. A process that starts a
session of its own leaves the group and is its own to end; what it leaves in the folder goes with the
folder, or with the sweep. A hook killed outright
cannot remove its folder, so each run first removes such folders older than STALE. The time a run is
given counts from when the hook asked, the sweep's time included.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import signal
import subprocess
import tempfile
import time

from tools import walk

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
    return os.path.abspath(env.get("TMPDIR") or tempfile.gettempdir())


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


REAP = 5        # seconds to wait for the run itself once its group is killed

def _end(child: subprocess.Popen) -> None:
    """End the run's whole process group, whatever it started, and reap it. The output is not read on: a process of
    a session of its own may hold it open for as long as it lives."""
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    if child.stdout is not None:
        child.stdout.close()
    try:
        child.wait(timeout=REAP)
    except subprocess.TimeoutExpired:
        pass


def make(target: str, where: pathlib.Path, env: dict, timeout: int, clock=time.time) -> tuple:
    """(passed, what to show). Without make, it did not pass, and says why in one sentence. Whatever the run makes
    under its temporary folder is removed when it ends, and so is every process of its group."""
    exe = _make(env)
    if exe is None:
        return False, ("make is not on PATH, so `make %s` did not run in %s. Put make on PATH; the same checks "
                       "run without it as python3 -m tools.verify%s." % (target, where, "" if target == "verify" else " --" + target))
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


PASSED = "sf-checks-passed"     # in the tree's git directory: the state its last `make checks` that passed was run at
GIT_SECONDS = 5
AFTER = 5           # seconds of a run's time kept to read the state again once it has passed


def _git(where: pathlib.Path, env: dict, args: list):
    exe = shutil.which("git", path=env.get("PATH", os.defpath))
    if exe is None:
        return None
    try:
        done = subprocess.run([exe] + args, cwd=str(where), env=env, capture_output=True, timeout=GIT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.decode("utf-8", "surrogateescape") if done.returncode == 0 else None


def gitdir(where: pathlib.Path, env: dict):
    """The git directory of the tree at `where`, a worktree's own; None where it cannot be read."""
    found = _git(where, env, ["rev-parse", "--absolute-git-dir"])
    path = pathlib.Path(found.strip()) if found and found.strip() else None
    return path if path is not None and path.is_dir() else None


def state(where: pathlib.Path, env: dict):
    """What `make checks` reads in `where`, as one key; None where any of it cannot be read: every entry of git's index,
    the commits HEAD and origin's main name, and the folders at any depth, the links and the files tools/walk.py lists,
    each file's mode and bytes. Nothing is written, to git or elsewhere."""
    held = _git(where, env, ["ls-files", "-s", "-z"])
    head = _git(where, env, ["rev-parse", "HEAD"])
    base = _git(where, env, ["for-each-ref", "--format=%(objectname)", "refs/remotes/origin/main"])
    if held is None or not head or base is None:
        return None
    digest = hashlib.sha256("\0".join([held, head.strip(), base.strip()]).encode("utf-8", "surrogateescape"))

    def name(kind: bytes, path: pathlib.Path, mode: int = 0):
        at = path.relative_to(where).as_posix().encode("utf-8", "surrogateescape")
        digest.update(b"\0%s %o " % (kind, mode) + at + b"\0")
    try:
        for path in walk.directories(where):
            name(b"d", path)
        for path in walk.links(where):
            name(b"l", path)
            digest.update(os.readlink(str(path)).encode("utf-8", "surrogateescape"))
        for path in walk.files(where):
            if path.is_symlink():
                continue
            name(b"f", path, path.stat().st_mode)
            with open(str(path), "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    digest.update(chunk)
    except (OSError, ValueError):
        return None
    return digest.hexdigest()


def ran_out(said: str, target: str, where: pathlib.Path) -> bool:
    """Whether what a run said is that it did not finish in its time."""
    before, after = UNFINISHED.split("%d")
    start, end = before % target, after % where
    return said.startswith(start) and said.endswith(end) and said[len(start):len(said) - len(end)].isdigit()


def checks(where: pathlib.Path, env: dict, timeout: int) -> tuple:
    """make("checks"), skipped where its last pass was at the state `where` is in now. A pass is written down only when
    the state read before the run is the state read after it, so an edit made while it ran is never taken as checked.
    A state that cannot be read skips nothing and is not written down."""
    asked = time.monotonic()
    git_dir = gitdir(where, env)
    record = git_dir / PASSED if git_dir is not None else None
    key = state(where, env) if git_dir is not None else None
    try:
        if key is not None and record.read_text().strip() == key:
            return True, ""
    except (OSError, ValueError):       # a record that is not text is no pass (Codex on #568)
        pass
    passed, said = make("checks", where, env, max(1, int(timeout - AFTER - (time.monotonic() - asked))))
    if passed and key is not None and state(where, env) == key:
        try:
            record.write_text(key + "\n")
        except OSError:
            pass
    return passed, said


def lacks(target: str, where: pathlib.Path, env: dict) -> bool:
    """Whether make is there and the Makefile in `where` has no such target, as on a branch older than it. A Makefile that
    cannot be read, or a target whose own needs are missing, has the target, and running it says what is wrong."""
    exe = _make(env)
    if exe is None:
        return False
    try:
        done = subprocess.run([exe, "-n", target], cwd=str(where), env=env, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    said = done.stderr.decode(errors="replace")
    return done.returncode != 0 and re.search(r"No rule to make target .%s." % re.escape(target), said) is not None
