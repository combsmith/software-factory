"""What a pass, and a Run that asks the Kernel again, are told: the Kernel's configuration, each Lifecycle, the feed's
table, `controller/1`, the authority table and the Release, read from the Release's own files (decision 0006), and the App whose token the
reads go through, with the needs `config/apps.json` names. It reads files and nothing else: no clock, no network."""
from __future__ import annotations

import json
import pathlib
import re

from tools.hooks import protected

RELEASE = re.compile(r"factory/v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def _json(root: pathlib.Path, *parts):
    return json.loads(root.joinpath(*parts).read_text())


def _readable(root: pathlib.Path, *parts):
    """The file as JSON, or None where it cannot be read: what reads it then reads none (`controller/credentials.py`)."""
    try:
        return _json(root, *parts)
    except (OSError, ValueError):
        return None


def kernel(root: pathlib.Path) -> dict:
    """The Kernel's configuration as its tests give it: the defaults, and the protected paths, the model Lenses'
    inputs and the paths only a person decides, from the one list the session hooks read too, read once."""
    hooks = protected.load(root / "config" / "hooks.json")
    held = dict(_json(root, "config", "defaults.json"), protected_paths=protected.protected_of(hooks))
    held["model_lens_inputs"] = protected.model_inputs_of(hooks, held["required_lenses"]["model"])
    held["person_only_paths"] = person_only(hooks, held["required_lenses"]["model"])
    return held


def person_only(hooks: dict, models: list) -> list:
    """What the Kernel is given as `person_only_paths`, of `hooks`, a reading of `config/hooks.json` by
    `tools/hooks/protected.py`: each path only a person decides that no Lens of `models`, the model Lenses, reads,
    once, in the file's order. By this list the Kernel names the wait `path_needs_person`, so a path that is a model
    Lens's own input as well is left off it: its change waits as a Lens's input does, the stricter name, and is never
    passed off as a person's path alone (decision 0207)."""
    own = [path for lens, path, _ in hooks["lens_inputs"] if lens in models]
    return [path for path in dict.fromkeys(path for path, _ in hooks["person_only"]) if path not in own]


def load(root: pathlib.Path, release: str, app: str) -> dict:
    """`kernel`, `release`, `controller`, `feed` and `lifecycles`, as `pass_.run` takes them, and `app` and `needs`,
    the App the reads go through and the needs it is granted under, `apps`, every App by its Role's name, and
    `authority`, which gives each Lens the categories its Findings may name (`adapters/applied.py`), and `credentials`,
    each stored credential's dates, or None where they cannot be read, which raises their alert (issue 305)."""
    apps = _json(root, "config", "apps.json")
    return {"kernel": kernel(root), "release": release, "controller": _json(root, "config", "controller.json"),
            "feed": _json(root, "config", "feed.json"),
            "lifecycles": {"pull_request": _json(root, "lifecycle", "pull_request.json"),
                           "issue": _json(root, "lifecycle", "issue.json")},
            "app": apps["apps"][app], "needs": apps["needs"], "apps": apps["apps"],
            "authority": _json(root, "config", "authority.json"),
            "credentials": _readable(root, "config", "credential-ages.json")}
