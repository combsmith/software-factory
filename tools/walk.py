"""The files of this working tree, and of no other nested inside it.

A session's git worktree sits inside the main checkout, a whole copy of the repo with a `.git`
file; a full clone has a `.git` directory. Either is another working tree, and nothing in it is
this repo's. Every check that walks the tree walks it here, and every copy of the repo is made
here, so that all of them skip the same things. It reads only the tree, so it needs no git and
works in an export that has no `.git` at all.
"""
from __future__ import annotations

import os
import pathlib
import shutil

# Never part of the repo: git's own store, Python's caches, and the corpus `make_corpus.py` writes.
SKIP = {".git", "__pycache__", "corpus"}


def elsewhere(path: pathlib.Path) -> bool:
    """Is `path` a directory that holds another working tree? Its `.git` may be a file or a directory."""
    return os.path.lexists(os.path.join(str(path), ".git"))


def _skipped(folder: str, names: list) -> set:
    return {n for n in names if n in SKIP or (os.path.isdir(os.path.join(folder, n))
                                             and elsewhere(pathlib.Path(folder, n)))}


def files(root: pathlib.Path) -> list:
    """Every file below `root`, sorted, but none in SKIP and none in another working tree."""
    out = []
    for folder, dirs, names in os.walk(str(root)):
        skipped = _skipped(folder, dirs + names)
        dirs[:] = sorted(d for d in dirs if d not in skipped)
        out += [pathlib.Path(folder, n) for n in names if n not in skipped]
    return sorted(out)


def copy(root: pathlib.Path, to: pathlib.Path) -> None:
    """Copy this working tree to `to`, which must not exist, leaving out what `files` leaves out."""
    shutil.copytree(str(root), str(to), ignore=_skipped)
