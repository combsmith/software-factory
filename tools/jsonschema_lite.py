"""A small JSON Schema validator: the subset the Factory's schemas use.

It fails closed. A schema that uses a keyword this file does not implement is
rejected, so a schema can never silently promise more than is checked.
"""
from __future__ import annotations

import json
import re

ANNOTATIONS = {"$schema", "$id", "title", "description", "$defs", "$comment"}
KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "items", "enum", "const",
    "minimum", "maximum", "minLength", "minItems", "uniqueItems", "pattern", "$ref",
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


FILE = re.compile(r"^([a-z][a-z0-9-]*)\.schema\.json(#.*)?$")


def _resolve(ref: str, root: dict, schemas: dict = None) -> tuple:
    """(the schema `ref` names, the root its own references are read against).

    `#/$defs/<name>` is read in `root`. `<kind>.schema.json`, with `#/$defs/<name>` or nothing after it, is read in
    `schemas`, the mapping of kind to schema the caller passed, and that schema is the root of what it references.
    A reference with no mapping, or to a kind the mapping lacks, is a SchemaError: nothing is read from a file.
    """
    named = FILE.match(ref)
    if named:
        kind, fragment = named.group(1), named.group(2) or "#"
        if schemas is None or kind not in schemas:
            raise SchemaError("%s refers to a schema that was not given" % ref)
        root = schemas[kind]        # its own references are read in it, not in the referrer
        if fragment == "#":
            return root, root
        ref = fragment
    if not ref.startswith("#/$defs/"):
        raise SchemaError("only $defs references, local or by file, are supported: %s" % ref)
    name = ref[len("#/$defs/"):]
    try:
        return root["$defs"][name], root
    except (KeyError, TypeError):
        raise SchemaError("unresolved reference: %s" % ref)


def validate(value, schema: dict, root: dict = None, path: str = "$", schemas: dict = None, chain: tuple = ()) -> list:
    """Return a list of error strings; empty means valid. `schemas` maps a kind to the schema a `$ref` by file names.
    `chain` is the references followed so far at this value, so that a reference that comes round to itself is refused."""
    root = schema if root is None else root
    unknown = set(schema) - KEYWORDS - ANNOTATIONS
    if unknown:
        raise SchemaError("unsupported keyword(s) at %s: %s" % (path, sorted(unknown)))
    if "$ref" in schema:
        beside = set(schema) - ANNOTATIONS - {"$ref"}
        if beside:
            raise SchemaError("a $ref stands alone, and at %s it has %s beside it" % (path, sorted(beside)))
        target, root = _resolve(schema["$ref"], root, schemas)
        if id(target) in chain:
            raise SchemaError("%s comes round to itself at %s" % (schema["$ref"], path))
        return validate(value, target, root, path, schemas, chain + (id(target),))

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
        # A pattern is the schema's own, read from this Release's files, never the value's, and each is held to a limit
        # on a long value: tests/test_tools.py::test_no_schema_pattern_backtracks_on_a_long_value. S2631 reads a file as
        # outside data, so it is a false positive here.
        if "pattern" in schema and (re.search(schema["pattern"], value) is None or value.endswith("\n")):  # NOSONAR
            errors.append("%s: does not match %s" % (path, schema["pattern"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: below %s" % (path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: above %s" % (path, schema["maximum"]))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append("%s: fewer than %d items" % (path, schema["minItems"]))
        if schema.get("uniqueItems") is True and len({json.dumps(item, sort_keys=True) for item in value}) < len(value):
            errors.append("%s: an item is given twice" % path)
        if "items" in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], root, "%s[%d]" % (path, i), schemas)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append("%s: missing %s" % (path, name))
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            if name in props:
                errors += validate(item, props[name], root, "%s.%s" % (path, name), schemas)
            elif extra is False:
                errors.append("%s: unexpected %s" % (path, name))
            elif isinstance(extra, dict):
                errors += validate(item, extra, root, "%s.%s" % (path, name), schemas)
    return errors
