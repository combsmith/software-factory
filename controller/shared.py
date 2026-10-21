"""What the Controller's modules share: the Release's schemas, the refusal, and the one time format, read by hand."""
from __future__ import annotations

import datetime
import json
import pathlib

from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# The Release's own schemas, read once as the module loads, as the Release's other data files are.
SCHEMAS = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
           for p in sorted((ROOT / "schemas").glob("*.schema.json"))}
FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Refused(ValueError):
    """The pass cannot make a record that validates, so it makes none, and nothing is dispatched."""


def moment(text):
    """A time in the one format, as a moment, or None if it is not one."""
    try:
        return datetime.datetime.strptime(text, FORMAT)
    except (TypeError, ValueError):
        return None


def text(at) -> str:
    return at.strftime(FORMAT)


def seconds(later: str, earlier: str):
    """Seconds from `earlier` to `later`, or None if either is no moment."""
    a, b = moment(later), moment(earlier)
    return None if a is None or b is None else int((a - b).total_seconds())


def checked(value, kind: str):
    """`value`, if it validates against the schema `kind`; otherwise refused."""
    errors = validate(value, SCHEMAS[kind], schemas=SCHEMAS)
    if errors:
        raise Refused("%s: %s" % (kind, "; ".join(errors)))
    return value


def errors(value, kind: str) -> list:
    return validate(value, SCHEMAS[kind], schemas=SCHEMAS)


def key(item: dict) -> str:
    """The item's page on GitHub, which is also how the feed and the titles name it."""
    kind = "pull" if item["type"] == "pull_request" else "issues"
    return "https://github.com/%s/%s/%d" % (item["repo"], kind, item["number"])
