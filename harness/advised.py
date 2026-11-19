"""The advisory part of `apply`, the half that asks GitHub nothing: which advisory Lens has a Result to show, and
what the child that shows them said (decision 0224, "What is shown").

`asked` decides, with no network, which Lens has a Result to show and builds its check run. `told` reads back what the
child that writes the check runs said, a line at a time, whatever became of it:

    began                   before the token is asked for
    unminted                no token was minted: `identity` refused before GitHub was asked for one
    <lens> <code> [<key>]   one Lens's check run: a code of `adapters/advice.py`'s, and its key where it was read back
    revoked | unrevoked     whether GitHub confirmed the token revoked

A Lens the child did not report is `out_of_time`. A child that began and did not say `revoked`, killed or not, leaves
the token's state unknown: every Lens it was asked for is `token_not_revoked`, with the key of any it had shown.
"""
from __future__ import annotations

import os
import re

from adapters import advice
from harness import shared, steps
from harness.steps import Stop

REVIEWING = "review-change"     # the Intent whose Run the advisory Lenses read for
LINE = re.compile(r"([a-z]{1,31}) ([a-z_]{1,40})(?: ([A-Za-z0-9_=:-]{1,100}))?")


def _file(base, folder, name: str, most: int):
    """At most `most` bytes of the file `name` in `folder`, or None. The folder is followed to where it really is, a
    link or not, and must lie inside `base`; the file itself is never a link: one is not opened."""
    try:
        opened = os.open(os.path.join(steps.inside(base, folder), name), os.O_RDONLY | os.O_NOFOLLOW)
        with open(opened, "rb") as f:
            return f.read(most)
    except (OSError, Stop, TypeError, ValueError):
        return None


def asked(base, folder, admit, ended: dict, held: dict) -> tuple:
    """`(said, reqs)`: a code for each advisory Lens the Factory asks that has none to show, `{lens: code}`, and the
    check run of each that has, `[(lens, request)]`. Neither for a Run no Decision admitted or of another Intent than
    a review. A change under the Run, by its outcome or by the facts read again, is `superseded` for every Lens; a Run
    the Factory faulted, `environment` or `capacity`, is `run_not_whole`; an item not read again `item_not_read`. Else
    each Result is read from `folder`, it and its digest bounded, and held (`advice.held`): one that fails is its code."""
    if admit is None or admit["intent"] != REVIEWING:
        return {}, []
    asks = steps.read_json(steps.ROOT, os.path.join("config", "harness.json"))
    names = [lens for lens in asks["advisory"] if lens in asks.get("readers", {})]
    facts, head = held["item"][:2] if "item" in held else (None, None)
    every = "superseded" if ended["outcome"] == "superseded" else "run_not_whole" if ended["outcome"] not in (None, "item") \
        else "item_not_read" if facts is None \
        else "superseded" if facts["state"] != "open" or facts["content_id"] != admit["content_id"] else None
    if every is not None:
        return {lens: every for lens in names}, []
    said, reqs = {}, []
    for lens in names:
        data = _file(base, folder, "advice.%s.json" % lens, advice.LARGEST + 1)
        digest = _file(base, folder, "advice.%s.sha256" % lens, 128)
        result, said[lens] = advice.held(data, digest, lens, names, admit, shared.SCHEMAS)
        if result is not None:
            output, ids = advice.shown(result)
            reqs.append((lens, {"commit": head, "name": advice.CHECK % lens, "conclusion": "neutral",
                                "external_id": "%s:%s" % (admit["run"], lens), "output": output,
                                "annotations": [{"finding": ident} for ident in ids]}))
    return said, reqs


def told(out, lenses: list) -> dict:
    """`{lens: (code, key)}` for each Lens the child was asked, from what it said, `out`, however it ended."""
    lines = out.decode("utf-8", errors="replace").split("\n")[:-1] if isinstance(out, bytes) else []
    said = {}
    for line in lines:
        one = LINE.fullmatch(line)
        # A check run read back is said with its key, and nothing else is: a line that says otherwise says nothing.
        if one and one.group(1) in lenses and one.group(1) not in said and one.group(2) in advice.CODES \
                and (one.group(2) == "shown") == (one.group(3) is not None):
            said[one.group(1)] = (one.group(2), one.group(3))
    if "unminted" in lines and "unrevoked" not in lines:
        return {lens: ("token_not_minted", None) for lens in lenses}
    if "began" not in lines:
        return {lens: ("out_of_time", None) for lens in lenses}     # nothing was asked of GitHub
    if "revoked" not in lines or "unrevoked" in lines:
        # The token's state is not known: it was asked for, and GitHub was not heard to revoke it.
        return {lens: ("token_not_revoked", said.get(lens, (None, None))[1]) for lens in lenses}
    return {lens: said.get(lens, ("out_of_time", None)) for lens in lenses}
