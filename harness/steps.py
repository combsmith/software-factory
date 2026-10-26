"""What every step of a Run's jobs shares: its files and its exit. A step reads and writes only inside the directory it
runs in, each path followed to where it really is; it writes into a folder of its own that did not exist, each file
made new, its own user's alone to read; and it prints one code and exits 1 when it cannot go on, and nothing else, since
an error's message could quote what GitHub or the model answered (section 3.10)."""
from __future__ import annotations

import json
import os
import pathlib
import sys


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


ROOT = pathlib.Path(__file__).resolve().parent.parent
