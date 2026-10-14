"""Run a make target for a hook, in the copy of the repo the session is working in."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
TAIL = 40   # lines of output shown; the end of a run is where it says what failed


def tree(*places) -> pathlib.Path:
    """The copy of this repo that holds the first of `places` that is in one; else this one."""
    for place in places:
        if not place:
            continue
        path = pathlib.Path(place).resolve()
        for folder in (path,) + tuple(path.parents):
            if (folder / "tools" / "verify.py").is_file():
                return folder
    return ROOT


def tail(text: str, lines: int = TAIL) -> str:
    return "\n".join(text.rstrip("\n").split("\n")[-lines:])


def make(target: str, where: pathlib.Path, env: dict, timeout: int) -> tuple:
    """(passed, what to show). Without make, it did not pass, and says why in one sentence."""
    exe = shutil.which("make", path=env.get("PATH", os.defpath))
    if exe is None:
        return False, ("make is not on PATH, so `make %s` did not run in %s. Put make on PATH; the same checks "
                       "run without it as python3 -m tools.verify%s." % (target, where, " --fast" if target == "fast" else ""))
    try:
        done = subprocess.run([exe, target], cwd=str(where), env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "`make %s` did not finish in %d seconds in %s." % (target, timeout, where)
    except OSError as err:
        return False, "`make %s` could not start in %s: %s." % (target, where, err)
    return done.returncode == 0, tail(done.stdout)
