"""What the Harness's modules share: the Release's schemas, read once as the module loads, and the codes that name a
read that failed."""
from __future__ import annotations

import contextlib
import json
import pathlib

from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
           for p in sorted((ROOT / "schemas").glob("*.schema.json"))}
# Who wrote a text, as the facts name an actor.
SCHEMAS["actor"] = {"$ref": "facts.schema.json#/$defs/actor"}


def errors(value, kind: str) -> list:
    return validate(value, SCHEMAS[kind], schemas=SCHEMAS)


@contextlib.contextmanager
def staged(stage: str):
    """A read of a step's, named `stage`: any fault it raises is told the stage and raised on (`unread` names it), a
    read GitHub did not answer and a fault of the read's own code alike, since a step that records every fault would
    hide which read it was (decision 0187). Each caller reads a Moved, the pull request changed, before any code."""
    try:
        yield
    except Exception as err:
        err.stage = stage
        raise


def unread(err) -> str:
    """The code of a read that failed, GitHub's refusal or a fault of its own code: `<stage>_unreadable`; with the part
    its port gave, a snapshot's `snapshot_<part>_unreadable` (`adapters/facts.py`) and a Pause's
    `pause_<part>_unreadable` (`adapters/pause.py`, decision 0191); or `facts_unreadable` for a fault no stage named.
    Codes of the Harness's own, never what GitHub or the fault said, so a Run that stops says which read it was (pull
    request 688, the dry run, stopped twice at one code for every read)."""
    stage, part = getattr(err, "stage", None), getattr(err, "part", None)
    if stage is None:
        return "facts_unreadable"
    return "%s_%s_unreadable" % (stage, part) if part else "%s_unreadable" % stage


def checked(value, kind: str, refused):
    """`value`, if it validates against the schema `kind`; otherwise `refused` is raised with what is wrong."""
    wrong = errors(value, kind)
    if wrong:
        raise refused("%s: %s" % (kind, "; ".join(wrong)))
    return value
