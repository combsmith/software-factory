"""What the Harness's modules share: the Release's schemas, read once as the module loads."""
from __future__ import annotations

import json
import pathlib

from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
           for p in sorted((ROOT / "schemas").glob("*.schema.json"))}


def errors(value, kind: str) -> list:
    return validate(value, SCHEMAS[kind], schemas=SCHEMAS)


def checked(value, kind: str, refused):
    """`value`, if it validates against the schema `kind`; otherwise `refused` is raised with what is wrong."""
    wrong = errors(value, kind)
    if wrong:
        raise refused("%s: %s" % (kind, "; ".join(wrong)))
    return value
