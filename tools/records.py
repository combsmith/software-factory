"""A one-line index of the decision records, made from the records alone and printed, never committed (decision 0009).

`python3 -m tools.records` prints it. A row gives a record's number and its title as written; whether it is live or
which record replaced it, from its Status as `tools/check_decisions.py` reads one; and its area, the top directories of
this repo that the paths its Boundaries name are in, but `tests/`, where nearly every check is. Under Chains, each live
record that replaced others names every record it replaced, through the records those replaced in turn. It is printed
on demand rather than kept as a page, since a kept page would need every pull request that adds a record to rewrite it.
"""
from __future__ import annotations

import pathlib
import sys

from tools import check_context, check_decisions

ROOT = pathlib.Path(__file__).resolve().parent.parent
FOLDER = "docs/decisions"
SKIPPED = {"tests"}
HEAD = """# Decision records

Printed by `python3 -m tools.records` from the records in `docs/decisions/` alone.
A record is live until a later one replaces it. Its area is the top directories its Boundaries name, but `tests/`.

| Record | Title | Status | Area |
|---|---|---|---|
"""
CHAINS = """
## Chains

Each live record that replaced others, and every record it replaced, through the chain.

| Live record | Replaced |
|---|---|
"""


def _order(rel: str) -> tuple:
    """Where a record stands in the index: by its number as a number, so that 10000 comes after 1166 (decision 1121)."""
    named = check_context.RECORD_NUMBER.match(rel.rsplit("/", 1)[-1])
    return (0, int(named.group(1)), rel) if named else (1, 0, rel)


def _read(path: pathlib.Path, root: pathlib.Path) -> tuple:
    """(title, replaced by, area) of one record: the title after its number, the path of the record that replaced it
    or "", and the top directories of this repo that the paths its Boundaries name are in."""
    text = path.read_text(encoding="utf-8", errors="replace")
    first = text.split("\n", 1)[0]
    digits = path.name.split("-", 1)[0]
    title = first[len("# %s. " % digits):] if first.startswith("# %s. " % digits) else first.lstrip("# ")
    said = check_decisions.parse(text)
    status = said[0] if isinstance(said, tuple) else ""
    replaced = check_decisions.REPLACED.match(status)
    tops = set()
    for _, check in check_decisions.boundaries(text):
        for token in check_context.TOKEN.findall(check):
            name = token.split("::")[0]
            top = name.split("/")[0]
            if "/" in name and (root / top).is_dir() and not (root / top).is_symlink():
                tops.add(top)
    return title.strip(), replaced.group(1) if replaced else "", sorted(tops - SKIPPED)


def _number(rel: str) -> str:
    """A record's number, as its file gives it."""
    return rel.rsplit("/", 1)[-1].split("-", 1)[0]


def render(root: pathlib.Path = ROOT) -> str:
    """The index the records under `root` make."""
    # A link is never followed, as tools/check_decisions.py follows none: a record is a file, or it is not read.
    folder = root / FOLDER
    found = folder.glob("*.md") if folder.is_dir() and not folder.is_symlink() else []
    kept = [("%s/%s" % (FOLDER, p.name), p) for p in found if p.is_file() and not p.is_symlink()]
    records = {rel: _read(p, root) for rel, p in sorted(kept, key=lambda pair: _order(pair[0]))}
    rows, heads = [], {}
    for rel, (title, replaced, area) in records.items():
        status = "replaced by " + _number(replaced) if replaced else "live"
        cell = title.replace("\\", "\\\\").replace("|", "\\|")
        rows.append("| %s | %s | %s | %s |\n" % (_number(rel), cell, status, ", ".join(area)))
        # A replaced record's Status names only the record that replaced it, so a chain is read from the old end.
        head, seen = rel, {rel}
        while head in records and records[head][1] and records[head][1] not in seen:
            head = records[head][1]
            seen.add(head)
        if head != rel:
            heads.setdefault(head, []).append(rel)
    chains = ["| %s | %s |\n" % (_number(head), ", ".join(_number(rel) for rel in sorted(olds, key=_order)))
              for head, olds in sorted(heads.items(), key=lambda pair: _order(pair[0]))]
    return HEAD + "".join(rows) + (CHAINS + "".join(chains) if chains else "")


def main(argv: list = None, root: pathlib.Path = ROOT) -> int:
    sys.stdout.write(render(root))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
