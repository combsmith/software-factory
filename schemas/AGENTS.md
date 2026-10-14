# schemas/

One JSON Schema for each message that crosses a boundary, and for each data file.

| Rule | Held by |
|---|---|
| Use only the keywords `tools/jsonschema_lite.py` implements; any other is refused | `tests/test_tools.py::test_rejects_a_schema_it_cannot_enforce` |
| An object never accepts unknown fields: `additionalProperties` is false, or a schema | `tests/test_tools.py::test_a_schema_that_accepts_unknown_fields_is_caught` |
| Every schema has an example in `examples/`, or is the schema of a data file | `tools/check_examples.py` |
| What a schema exists to refuse is a file in `examples/invalid/`, which must be rejected | `tools/check_examples.py` |
| Facts and a Decision have no field for prose: no title, no body, no sentence | `examples/invalid/facts.carries-prose.json`, `examples/invalid/decision.sentence-as-reason.json` |
| A time is UTC to the second in one text format, so that times compare as text | `examples/invalid/facts.time-in-another-format.json` |
