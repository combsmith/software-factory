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
| In what one Run carries (`task`, `result`, `effect`, `disposition`, `run-name`) a string is a code: an `enum`, a `const` or an anchored pattern, unless named `body` | `tests/test_tools.py::test_a_string_that_is_neither_a_code_nor_a_body_is_caught` |
| A Result names no Role, App, actor, content id or commit: each is the Task's. Effects are one list for each type | `examples/invalid/result.carries-a-commit-hash.json`, `tests/test_tools.py::test_each_effect_type_is_requested_by_its_own_list` |
| A definition is referenced by file, `<kind>.schema.json#/$defs/<name>`, in the mapping the caller passes, and read against that schema; nothing is read from disk | `tests/test_tools.py::test_a_reference_to_another_schema_is_followed` |
| A `$ref` stands alone, and one that comes round to itself is refused | `tests/test_tools.py::test_a_reference_with_keywords_beside_it_is_refused`, `tests/test_tools.py::test_a_reference_that_comes_round_to_itself_is_refused` |
