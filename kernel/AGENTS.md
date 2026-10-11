# kernel/

Every decision the Factory makes, as pure functions. `derive.py` works out the State of a pull
request; `decide.py` works out what happens next; `terms.py` holds the codes.

## Rules of this place

- **No I/O.** No file, socket, process, environment variable or clock. The time is the argument
  `now`. Only `__future__`, `typing` and `kernel` may be imported.
- **Nothing is kept.** A module's top level holds constants only: text, a tuple, a `frozenset`.
- **Facts in, Decision out.** Plain dictionaries and lists, already validated against `schemas/`.
  Never change an argument.
- **No text from outside.** No function here takes a comment body or a title.
- **Codes, not sentences.** A reason matches `^[a-z_]+$`.
- **Fail to a deferral or a Hold.** Never give a default to a fact that was read from outside.
- **No numbers but 0 and 1.** A limit is read from `config`, which is `config/defaults.json`.

All held by `tools/check_purity.py`, `tools/check_examples.py` and the tests.

## Adding a rule: copy this one

"An empty diff never converges" is a whole rule in three parts. Find each and write its twin.

1. The boundary case: `tests/test_decide.py::test_empty_diff_never_converges`. Written first.
2. The rule: the line in `derive.py` that returns the reason `empty_diff`.
3. The mutant: the entry "an empty diff converges" in `tools/mutants.py`. It names the file, the
   exact text of the rule, and what to put in its place. The text must appear once in the file.
   A rule that acts in two places gets a test and a mutant for each.

Then, only if your rule needs it:

- A person must act on the new reason: add it to `NEEDS_YOU_REASONS` in `decide.py`.
- It reads a new fact: add the field to `schemas/facts.schema.json`, `examples/facts.json`,
  `facts()` in `tests/support.py` and `facts()` in `sim/world.py`, in the same change.
- It reads a new limit: add it to `config/defaults.json` and `schemas/config.schema.json`.
- It makes a new transition between States: declare it in `lifecycle/pull_request.json`.
- It is a boundary of a record in `docs/decisions/`: add a row there naming your test.

`derive()` answers "where does this item stand"; its checks run in order and the first that
applies wins. `decide()` answers "what now", and holds every brake.
