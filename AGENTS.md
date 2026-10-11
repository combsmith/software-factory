# software-factory

The decision core of the Factory: a set of agent Roles that turn an issue into a reviewed, merged
change, and a Kernel that decides what each Role may do next. So far this repo holds the Kernel,
its schemas, its checks and a simulator. Nothing here talks to GitHub or to a model yet.

It follows the org's standards, [petry-projects/.github/AGENTS.md](https://github.com/petry-projects/.github/blob/main/AGENTS.md),
except where `docs/decisions/0014-where-this-repo-departs-from-the-orgs-standards.md` says why not.

## Verify

```
make verify                  # every check and every test; SIM_SEEDS=40 make verify is quicker
python3 -m tools.mutants     # breaks each Kernel rule in turn; a test must notice. A minute or two
```

Both must pass before a change is finished. Python 3.9 or later; there is nothing to install.

## The rules that are never broken

Each rule names the check that holds it. A rule no check holds does not belong in this file.

| Rule | Held by |
|---|---|
| The Kernel does no I/O, reads no clock and keeps nothing between calls | `tools/check_purity.py` |
| State is derived from facts and run records at every call, never stored | `tests/test_decide.py::test_the_same_inputs_give_the_same_decision` |
| An unreadable fact yields a deferral or a Hold, never an action | `tests/test_decide.py::test_incomplete_facts_never_converge_or_admit` |
| A reason is a code, never a sentence, and no text from outside reaches a decision | `tools/check_examples.py` |
| Every message has a schema and an example, and counter-examples are rejected | `tools/check_examples.py` |
| The Lifecycle terminates; the Factory cannot cycle without a bound or a person | `tools/check_lifecycle.py` |
| Every category of Finding has one owner; no Role judges its own work | `tools/check_authority.py` |
| Every Kernel rule has a boundary test, and a mutant that the test kills | `tools/mutants.py` |
| The invariants hold under injected faults, on fixed seeds | `tests/test_simulator.py` |
| Nothing is installed or fetched; no secret is written down | `tools/check_repo.py` |
| A workflow is pinned, least-privileged and holds no logic | `tools/check_workflows.py` |
| Every rule, lesson and decision names its check; this file stays short | `tools/check_context.py` |

## Changing the Kernel

1. Read `kernel/AGENTS.md`. It names one existing rule to copy, part by part.
2. Write the boundary case in `tests/test_decide.py`. Run it and watch it fail.
3. Change the code in `kernel/`.
4. Add a mutant for the new rule to `tools/mutants.py`.
5. Run both commands under Verify.

## Where to read next

Before editing in a directory, read its `AGENTS.md`: it carries the rules of that place only.

| When you are | Read |
|---|---|
| Writing code, a test or a workflow, or touching a credential or a trust boundary | The one page in `docs/standards/` for it |
| Reviewing a change | `config/rubric-pr-review.json`. It is the review standard; there is no other |
| Asking why the structure is as it is | `docs/decisions/`, one decision to a file |
| About to repeat a mistake | `docs/lessons.md`: each failure, its rule and its check |
| Unsure what a capitalised word means | `docs/glossary.md`. One term, one meaning |
| Needing the design itself | `docs/architecture/software-factory-design.md`: section 0 is one page, and 1.2 says which sections are rules |

Not built yet, under names that are reserved: adapters, harness, controller, roles, release, evals
and the workflows. A rule that is waiting on one of them says so.
