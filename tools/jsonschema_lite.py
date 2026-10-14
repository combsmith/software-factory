"""A small JSON Schema validator: the subset the Factory's schemas use.

It fails closed. A schema that uses a keyword this file does not implement is
rejected, so a schema can never silently promise more than is checked.
"""
from __future__ import annotations

import re

ANNOTATIONS = {"$schema", "$id", "title", "description", "$defs", "$comment"}
KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "items", "enum", "const",
    "minimum", "maximum", "minLength", "minItems", "pattern", "$ref",
}
TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "null": type(None), "integer": int, "number": (int, float),
}


class SchemaError(Exception):
    """The schema itself is not one this validator can enforce."""


def _is(value, name: str) -> bool:
    if name not in TYPES:
        raise SchemaError("unknown type: %s" % name)
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, TYPES[name])


def _resolve(ref: str, root: dict) -> dict:
    if not ref.startswith("#/$defs/"):
        raise SchemaError("only local $defs references are supported: %s" % ref)
    name = ref[len("#/$defs/"):]
    try:
        return root["$defs"][name]
    except KeyError:
        raise SchemaError("unresolved reference: %s" % ref)


def validate(value, schema: dict, root: dict = None, path: str = "$") -> list:
    """Return a list of error strings; empty means valid."""
    root = schema if root is None else root
    unknown = set(schema) - KEYWORDS - ANNOTATIONS
    if unknown:
        raise SchemaError("unsupported keyword(s) at %s: %s" % (path, sorted(unknown)))
    if "$ref" in schema:
        return validate(value, _resolve(schema["$ref"], root), root, path)

    errors = []
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is(value, n) for n in names):
            return ["%s: expected %s" % (path, " or ".join(names))]
    if "const" in schema and value != schema["const"]:
        errors.append("%s: must be %r" % (path, schema["const"]))
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s: %r is not one of %s" % (path, value, schema["enum"]))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append("%s: shorter than %d" % (path, schema["minLength"]))
        if "pattern" in schema and (re.search(schema["pattern"], value) is None or value.endswith("\n")):
            errors.append("%s: does not match %s" % (path, schema["pattern"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: below %s" % (path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: above %s" % (path, schema["maximum"]))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append("%s: fewer than %d items" % (path, schema["minItems"]))
        if "items" in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], root, "%s[%d]" % (path, i))
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append("%s: missing %s" % (path, name))
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            if name in props:
                errors += validate(item, props[name], root, "%s.%s" % (path, name))
            elif extra is False:
                errors.append("%s: unexpected %s" % (path, name))
            elif isinstance(extra, dict):
                errors += validate(item, extra, root, "%s.%s" % (path, name))
    return errors
