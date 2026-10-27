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


def kernel(root: pathlib.Path) -> dict:
    """The Kernel's configuration as its tests give it: the defaults, and the protected paths and the model Lenses'
    inputs, from the one list the session hooks read too."""
    held = dict(_json(root, "config", "defaults.json"),
                protected_paths=protected.protected_paths(root / "config" / "hooks.json"))
    held["model_lens_inputs"] = protected.model_lens_inputs(held["required_lenses"]["model"],
                                                            root / "config" / "hooks.json")
    return held


def load(root: pathlib.Path, release: str, app: str) -> dict:
    """`kernel`, `release`, `controller`, `feed` and `lifecycles`, as `pass_.run` takes them, `app` and `needs`,
    the App the reads go through and the needs it is granted under, and `authority`, which gives each Lens the
    categories its Findings may name (`adapters/applied.py`)."""
    apps = _json(root, "config", "apps.json")
    return {"kernel": kernel(root), "release": release, "controller": _json(root, "config", "controller.json"),
            "feed": _json(root, "config", "feed.json"),
            "lifecycles": {"pull_request": _json(root, "lifecycle", "pull_request.json"),
                           "issue": _json(root, "lifecycle", "issue.json")},
            "app": apps["apps"][app], "needs": apps["needs"], "authority": _json(root, "config", "authority.json")}
