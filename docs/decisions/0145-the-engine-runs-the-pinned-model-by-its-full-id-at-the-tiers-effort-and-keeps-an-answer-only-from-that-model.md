# 0145. The Engine runs the pinned model by its full id, at the tier's effort, and keeps an answer only from that model

Status: accepted. Replaces `docs/decisions/0138-the-review-reads-the-pull-requests-head-with-the-read-tools-alone-held-to-it-by-restricted.md`. The Maintainer's ruling before the factory/v0.1.0 cut, "Pin the model", widened from the harness review by the Factory Builder on 2026-11-05: these choices freeze what the eval measures, so that a score is of one model at one effort. Of 0138 it overturns one thing: the list of names decision 0050's row "The environment" gives the CLI, which 0138 kept, now holds `DISABLE_UPDATES` too. Nothing else in 0138, or in the rows of 0050 it kept, changes.

## Decision

| What | Decided | Because |
|---|---|---|
| The model | `config/harness.json` names the model by its full id, `claude-opus-5-5`, and `schemas/harness.schema.json` admits nothing else: `^claude-[a-z]+(-[0-9]+)+$`, so `opus`, `best` or `opus[1m]` is refused | The pin said `opus`, an alias the CLI resolves at each call. At 2.1.306 the CLI's own catalog, in its binary, resolves it to `claude-opus-5-5` for a first-party login, and the same code reads an alias through a model list it is given at run time, so the alias is not fixed by the pin. Anthropic's models page lists `claude-opus-5-5` as both the id and the alias of Opus 5.5, and says each dateless id from 4.6 on is a pinned snapshot, so there is no dated form to name |
| Where a model is named | In `config/harness.json` alone, and in the counter-examples of its schema, which copy that id and no other. `tools/check_repo.py` refuses a model's full id anywhere else but a document or a fixture | L-34: a model named in one place is changed in one place. Its rule waited on the engine port, which now exists |
| The model that answered | `usage.answering_model` records the one model the CLI's `modelUsage` names, or null where it names none, more than one, or one in a form `schemas/result.schema.json` does not hold. An answer whose answering model is not the pinned one is no Result: `failed`, `engine_model`, its findings and Effects dropped, as one at another version is `engine_version`. A Run the CLI never answered, or that erred, is held to its own reason first | The pin names the model asked for; only the CLI's answer says which model answered. An eval score is of the model that answered, so an answer from another model, by a fallback, a remapped alias or a change on the vendor's side, cannot be scored as the pin's |
| The fault | `engine_model` is an Engine fault in the eval (`ENGINE_FAULTS`, the eval report's reasons), never the reviewer's | Decision 0106: a fault of the Engine is never the reviewer's |
| The effort | Each tier in `schemas/harness.schema.json` has an `effort`, one of the CLI's levels (`low`, `medium`, `high`, `xhigh`, `max`). Both are `medium`. A Task carries its tier's, `harness/engine.py` gives it to the CLI as `--effort`, and `usage.effort` records it | `medium` is the default the pinned CLI's catalog gives `claude-opus-5-5` today, so nothing a Run does changes. Named, the effort no longer moves when the CLI's default does. The pinned CLI lists `--effort <level>` with these five levels in its help |
| No update | The CLI is given `DISABLE_UPDATES=1` beside `DISABLE_AUTOUPDATER=1`: the names it is given are exactly `PATH`, `LANG`, `HOME`, `TMPDIR`, `DISABLE_UPDATES`, `DISABLE_AUTOUPDATER`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` and the model credential under `CLAUDE_CODE_OAUTH_TOKEN` alone | The pinned binary reads both names. The version is held before and after each call (L-35), and a CLI that does not try to update cannot fail that check by doing so |
| The CLI's version | Stays at 2.1.306 | Moving the pin is the Maintainer's call, after the cut |

## Why

The eval scores the review Role on held-out cases, and the cut rests on that score. A score means something only of the thing that will run: the same CLI, the same model and the same effort. The version was pinned and checked; the model and the effort were left to the CLI's defaults of the day. Each is now named, given to the CLI and recorded in `usage`, and the model that answered is checked against the pin.

What is owed: no trial has recorded `modelUsage` from a review Run under the read tools, or with `--effort` given. P-13 at 2.1.306 recorded one model in `modelUsage` with no tool. If a later pin names a second model there for a Run that uses one, such as a smaller model for a tool, every such Run fails `engine_model` until a record says how to read it.

## Boundaries

| Boundary | Check |
|---|---|
| The pin names a model by its full id, never an alias | `tools/check_examples.py`, `examples/invalid/harness.a-model-by-its-alias.json` |
| A model's full id stands in the pin and its counter-examples alone | `tests/test_tools.py::test_a_model_is_named_by_the_engines_pin_and_its_counter_examples_alone` |
| An answer is kept only from the pinned model, as `modelUsage` names it, and `usage` records the model that answered | `tests/test_harness.py::test_an_answer_is_kept_only_from_the_pinned_model` |
| `engine_model` is an Engine fault in the eval | `tests/test_evals.py::test_a_fault_of_the_engine_or_the_factory_is_not_the_reviewers` |
| The CLI is given the tier's effort once, and `usage` records it | `tests/test_harness.py::test_the_cli_is_given_no_tool`, `tests/test_harness.py::test_a_result_the_engine_wrote_is_filled_and_kept` |
| A tier, and a Task, has an effort the CLI knows, and `usage` names the effort and the model that answered | `tools/check_examples.py`, `examples/invalid/harness.an-effort-the-cli-does-not-know.json`, `examples/invalid/harness.a-tier-with-no-effort.json`, `examples/invalid/task.limits-with-no-effort.json`, `examples/invalid/result.usage-that-names-no-model-that-answered.json`, `examples/invalid/result.usage-with-no-effort.json` |
| The CLI is given `DISABLE_UPDATES=1` | `tests/test_harness.py::test_the_cli_is_given_exactly_the_named_environment_and_the_one_credential` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
