# examples/

What each message looks like, and what must be refused.

| Rule | Held by |
|---|---|
| `<schema>.json` validates against the schema of that name in `schemas/`, and so does `<schema>.<what it shows>.json` | `tools/check_examples.py` |
| `invalid/<schema>.<what is wrong>.json` is rejected. Make it wrong in one way, named in the file name | `tools/check_examples.py` |
| `workflows/verify.yml` passes every workflow rule, and the workflow that runs is the same file word for word | `tools/check_workflows.py` |
| `workflows/invalid/<rule>.<what is wrong>.yml` breaks that rule and no other; every rule has one | `tools/check_workflows.py` |
| `workflows/verify.yml` is the example shown in `docs/standards/workflows.md`, word for word | `tests/test_tools.py::test_an_example_in_the_standard_that_has_drifted_is_caught` |
