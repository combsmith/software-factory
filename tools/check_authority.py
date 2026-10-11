"""Mechanical checks on who decides what."""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL_JUDGED = {"functional", "security", "architecture", "delivery", "reliability",
                "requirements", "uncategorised"}


def run(authority: dict = None) -> list:
    a = json.loads((ROOT / "config" / "authority.json").read_text()) if authority is None else authority
    problems = []
    cats = a["categories"]
    for name in sorted(MODEL_JUDGED - set(cats)):
        problems.append("category has no owner: %s" % name)
    for name, c in sorted(cats.items()):
        owner = c["owner"]
        if name in MODEL_JUDGED and owner in ("none", "human"):
            problems.append("%s is judged by a model and needs a Role as owner" % name)
        if owner == a["author_role"]:
            problems.append("%s: the author Role may not own a category" % name)
        if c.get("shadow") == owner:
            problems.append("%s: a Role cannot shadow itself" % name)
        if c.get("shadow") == a["author_role"]:
            problems.append("%s: the author Role may not shadow a category" % name)
    weak = set(cats.get("security", {}).get("may_accept", [])) & {"declined", "deferred"}
    if weak:
        problems.append("a security Finding may never be accepted as: %s" % sorted(weak))
    return problems
