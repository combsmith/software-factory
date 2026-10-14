# Code

How code is written here. Each rule shows its example first, then says what holds it.
An org standard is cited from combsmith/.github at commit 9e2daad, by file and heading.

## A decision is a pure function

```python
def admitted(facts: dict) -> bool:
    """An outside item is admitted only after its author's latest push."""
    if facts["class"] != "outside":
        return True
    if t.LABEL_ADMIT not in facts["labels"] or facts["admitted_at"] is None:
        return False
    return facts["admitted_at"] > facts["last_push_at"]
```

Facts in, answer out. No file, socket, process, environment variable or clock: the time is the
argument `now`. Nothing is kept between calls, so a module's top level holds constants only.

Org standard: the org's AGENTS.md, "Decision Logic Lives in a Pure, Tested Script". Stricter here: no clock, no environment and nothing kept either, and a tool asserts it.
Held by: `tools/check_purity.py`, `tests/test_decide.py::test_the_same_inputs_give_the_same_decision`

## Unreadable is its own answer

```python
# No. A missing reading becomes zero, and zero looks like "plenty of room".
active = context.get("active_runs", 0)

# Yes. A missing reading is a deferral with a reason.
active = context.get("active_runs")
if active is None:
    return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
```

Never give a default to something that was read from outside. An unreadable fact yields `defer`
or `hold`; it never yields `admit` or `act`.

Org standard: the org's AGENTS.md, "Fail Loud, Never Fake". Stricter here: the org allows a fallback that is disclosed; the Kernel has none.
Held by: `tests/test_decide.py::test_unreadable_capacity_defers`, `tests/test_decide.py::test_incomplete_facts_never_converge_or_admit`

## A reason is a code

```python
return {"state": t.HELD, "reason": "empty_diff", "evidence": []}        # yes
return {"state": t.HELD, "reason": "The diff has no files.", "evidence": []}   # no
```

A reason matches `^[a-z_]+$`. People read a rendering of it, made elsewhere. If the reason means
a person must act, add it to `NEEDS_YOU_REASONS` in `kernel/decide.py`.

Org standard: none. This rule is this repo's own.
Held by: `examples/invalid/decision.sentence-as-reason.json`

## A limit is data

```python
if len(attempts) >= limits["max_attempts"]:     # yes: config/defaults.json
if len(attempts) >= 3:                          # no
```

The only numbers written in the Kernel are 0 and 1. Every other number is a limit, lives in
`config/defaults.json`, and is described by `schemas/config.schema.json`.

Org standard: the org's AGENTS.md, "Pull Request Limits (automation open-PR cap)", which says never to hardcode or restate a cap. Stricter here: every number but 0 and 1.
Held by: `tests/test_tools.py::test_a_limit_written_into_the_kernel_is_caught`

## Nothing is installed

```python
from __future__ import annotations

import json
import pathlib

from kernel import terms as t
```

The standard library and this repo, and nothing else. A standard-library module not yet in use is
added to `STDLIB` in `tools/check_repo.py` in the same change. The syntax is Python 3.9's. This is
why the org's linters, type checker and test runner are not used here: each is an install.

Org standard: none for the rule. It departs from the org's AGENTS.md, "Pre-Commit Quality Checks", and the Python instructions, "Testing (pytest)": `docs/decisions/0014-where-this-repo-departs-from-the-orgs-standards.md`.
Held by: `tools/check_repo.py`, `tests/test_tools.py::test_syntax_newer_than_the_oldest_python_is_caught`

## A check returns its problems

```python
def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    for path in sorted((root / "kernel").glob("*.py")):
        ...
            problems.append("%s:%d imports %s" % (path.name, node.lineno, mod))
    return problems
```

A check is a module `tools/check_<name>.py` with `run()` returning a list of sentences, empty when
all is well. It takes the repo root as an argument so that a test can run it against a planted
fault. It is registered in `CHECKS` in `tools/verify.py`. It collects every problem and never
stops at the first.

Org standard: none. This rule is this repo's own.
Held by: `tests/test_tools.py::test_every_check_is_run_by_verify`, `tests/test_tools.py::test_every_check_has_a_test_in_which_it_fails`

## A name is defined once

```python
class Ceilings(unittest.TestCase):
    def test_rounds_are_bounded(self): ...
    def test_rounds_are_bounded(self): ...    # replaces the first without a word
```

Python keeps the last definition and drops the others, so a duplicated test silently stops
running. Replace a function; never append a second copy.

Org standard: the org's duplicate-declaration gate, scripts/check-duplicate-decls.sh, which holds shell functions, headings and JSON keys in two repos. The same idea, for Python definitions and JSON keys.
Held by: `tests/test_tools.py::test_a_second_definition_is_caught`
