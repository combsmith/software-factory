"""Which Release a commit is: the one Release tag that names it (ruling 7).

A Release is a tag `factory/vMAJOR.MINOR.PATCH`; a Channel, `factory/vMAJOR-next` or `factory/vMAJOR-stable`, is
never a Release, whatever it points at. A commit with no Release is none, and so is a commit two Releases name: the
cut refuses a second Release on one commit (`already_released`), so two means something else wrote, and nothing is
read from either. Pure: it is given the refs, and reads nothing.
"""
from __future__ import annotations

PREFIX = "factory/v"


def _number(part: str) -> bool:
    """A version's part: digits, with no leading zero unless it is 0 itself."""
    return part.isdigit() and part.isascii() and (part == "0" or not part.startswith("0"))


def version(name) -> tuple:
    """(MAJOR, MINOR, PATCH) of a Release's name, or () for anything that is not one, a Channel among them."""
    if not isinstance(name, str) or not name.startswith(PREFIX):
        return ()
    parts = name[len(PREFIX):].split(".")
    if len(parts) != 3 or not all(_number(p) for p in parts):
        return ()
    return tuple(int(p) for p in parts)


def channel(name) -> tuple:
    """(MAJOR, "next" or "stable") of a Channel's name, or () for anything that is not one, a Release among them."""
    if not isinstance(name, str) or not name.startswith(PREFIX):
        return ()
    major, gap, ring = name[len(PREFIX):].partition("-")
    if not gap or not _number(major) or ring not in ("next", "stable"):
        return ()
    return int(major), ring


def resolve(commit, refs) -> str | None:
    """The one Release whose tag names `commit`, among `refs` ({tag name: commit}); None when none does, or two do."""
    if not isinstance(commit, str):
        return None
    found = [name for name, sha in sorted(refs.items()) if sha == commit and version(name)]
    return found[0] if len(found) == 1 else None
