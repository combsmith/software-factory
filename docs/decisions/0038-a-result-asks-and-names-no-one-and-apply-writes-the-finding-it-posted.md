# 0038. A Result asks and names no one, and `apply` writes the Finding it posted

Status: accepted. Taken as a working ruling on 2026-10-18, which the Maintainer may overturn in review, for
"Schemas for Task, Result, Effect and Disposition" (issue 19). It decides three sentences of the design otherwise, each
amended in the same change: a Role's Finding record lives in its Run's the applied artifact (applied.json, §3.10), not its Result (result.json) (§3.3,
§3.7); a Disposition in a Result carries no `by` and no `content_id` (§3.8); and the run-name carries the whole
content id and the Run id with their own prefixes (§3.10).

## Decision

A Result holds what the Role judged, and only that. The Engine writes `schema`, `run`, `status` (`completed`,
`incomplete` or `refused`), `reason`, `dispositions`, `findings`, `effects` and `coverage`. The Harness fills `release`
and `usage` from the Task and from the CLI's own answer, and on an answer that does not validate writes the whole
Result itself: `failed`, `result_invalid`, empty lists and `usage`. `superseded` is written only by the Harness or
`apply`. No field in a Result holds a Role, an App, an actor, a `content_id` or a commit: the schema has no such field,
so a model cannot claim one, and `apply` takes each from the Task.

A Role raises a Finding in its Result as `{ref, location, category, severity, criterion, adopted_from}`, `ref` local
to the Result, with no `id`, `source`, `surface` or `content_id`. The one Effect that posts it names its `ref`. After
`apply` reads the posted surface back it writes the full `finding/1` into the applied artifact: the `id` from the source and
the surface key, the `source` from the Task's Role and its App, the `content_id` from the Task. The facts port joins a
thread's category and severity from that record. `finding/1` does not change, and `kernel/coverage.py` reads only
`criterion`, which a raised Finding has under the same name.

The four schemas, `task/1`, `result/1`, `effect/1` and `disposition/1`, and `run-name/1`, use only the keywords P-13
proved in front of the CLI. In them a string is a code, held by an `enum`, a `const` or a pattern anchored at both ends,
unless it is a property named `body`; a body goes out to GitHub or in to the model as data, and nothing reads one
back. `effect/1` is one list for each type, every list optional and each item strict, with `$defs/type` the enum of its
property names: with no `oneOf`, it is the only shape in which a `resolve_thread` with no thread is refused. A
`submit_review` has no event and no commit, and a `create_check_run` no name and no conclusion. A Disposition in a
Result is one half, `proposal` or `decision`, each with an optional reason code; the schema accepts neither half and
both, so `apply` checks that exactly one is given and that it is the half this Run's Role may make. `bundle` and
`preflight` wait for the author Intents, as do the other Effect types; a field added later is optional, or the major
version goes up.

One definition is referenced by file. `tools/jsonschema_lite.py` resolves `<kind>.schema.json` and
`<kind>.schema.json#/$defs/<name>` in a mapping of kind to schema the caller passes, and the referenced schema is the
root of its own references. A reference with no mapping, or to a kind the mapping lacks, is a `SchemaError`. The
validator still reads no file. The Harness hands the CLI a copy with the references resolved and the fields it fills
removed, so P-13's proven form, with no `$ref`, is what the model sees.

Where the rulings left a shape open, the closed form is taken: `usage` requires every field, and the model and the
session are strings even for a Run the CLI never answered, because the Harness names both before the call and passes
the session id in; a count and the cost are null only then, and `seconds`, the measured duration, is never null. A
raised Finding's path and an adopted surface's key admit no space and no control character. The run-name is the string
`sf <repo>#<number> <intent> <role> <content_id> <run>`, each field copied from the Task, and the Task's `item.repo`
admits only what the run-name does. A `$ref` stands alone: a keyword beside one would be a promise nothing enforces.
A reference that comes round to itself, or one the codes-only walk cannot follow, is refused, since the validator
follows a reference only where a value reaches it.

## Why

Decision 0004 says a model "is able to ask, in a form a schema can refuse". A `by: pr-review` written by the model is
the model saying who it is, and a `source` on a Finding is the same claim; `apply` already knows both from the Task,
and taking them from the Result would let text the Run read decide who owns a Finding. A Finding's `id` is derived
from its surface key (§3.7), and a Role's Finding has no surface until `apply` posts it, so the record is written once,
when all of it is known, rather than written twice and joined. Only a `body` is text because that is the rule "no text
from outside reaches a decision", held in the structure of what one Run carries. P-13 proved the validator's keywords
and no conditional, so every shape is closed without one, and the one check a schema cannot make is named for `apply`.
Decision 0029 asks for `coverage/1` by reference, and the pass record of the control room will carry `facts/1`, which
a copy would double. The content id is whole in the run-name because the records port fills the run record from it and
the Kernel compares it with the facts'; a shortened one would never match. GitHub's limit on a run-name's length is
unverified: about 160 characters at the longest, and P-17's were shorter.

## Boundaries

| Boundary | Check |
|---|---|
| A text of no trust class, a permitted Effect a Result cannot request, a Run id in another form and a Task with no release are refused | `examples/invalid/task.text-of-no-trust-class.json`, `examples/invalid/task.a-permitted-effect-a-result-cannot-request.json`, `examples/invalid/task.a-run-id-in-another-form.json`, `examples/invalid/task.no-release.json` |
| A Result with a sentence as its reason, a commit hash, a Finding that names its source, a status the design does not know, or a usage without the tokens written to the cache is refused | `examples/invalid/result.sentence-as-reason.json`, `examples/invalid/result.carries-a-commit-hash.json`, `examples/invalid/result.a-finding-that-names-its-source.json`, `examples/invalid/result.a-status-the-design-does-not-know.json`, `examples/invalid/result.usage-without-the-tokens-written-to-the-cache.json` |
| An act of the Controller, a review that approves, a thread named in words and a check run with a conclusion are refused as Effects | `examples/invalid/effect.an-act-of-the-controller.json`, `examples/invalid/effect.a-review-that-approves.json`, `examples/invalid/effect.a-thread-named-in-words.json`, `examples/invalid/effect.a-check-run-with-a-conclusion.json` |
| A Disposition with a sentence as its reason, one that names who decided, a result in words and an outcome the author cannot propose are refused | `examples/invalid/disposition.sentence-as-reason.json`, `examples/invalid/disposition.names-who-decided.json`, `examples/invalid/disposition.a-result-in-words.json`, `examples/invalid/disposition.an-outcome-the-author-cannot-propose.json` |
| The workflow's own name, as P-17 saw it listed, and a Run id in another form are not run-names | `examples/invalid/run-name.the-workflows-own-name.json`, `examples/invalid/run-name.a-run-id-in-another-form.json` |
| A reference by file, and by file and fragment, is followed, valid and invalid, and a referenced schema's own references are read in it; one with no mapping, or to a kind the mapping lacks, is refused | `tests/test_tools.py::test_a_reference_to_another_schema_is_followed`, `tests/test_tools.py::test_a_reference_to_a_schema_not_given_is_refused` |
| A reference that comes round to itself is refused, not left to recurse; one with a keyword beside it is refused | `tests/test_tools.py::test_a_reference_that_comes_round_to_itself_is_refused`, `tests/test_tools.py::test_a_reference_with_keywords_beside_it_is_refused` |
| In what one Run carries, a bare string and an unanchored pattern are caught, through a reference too, and a `body` passes. A pattern is anchored by its structure, not its first and last characters: an alternative outside the anchors or an escaped closing dollar is not anchored. A reference the walk cannot follow, one that comes round to itself and a keyword beside one are caught, in a branch no example takes too | `tests/test_tools.py::test_a_string_that_is_neither_a_code_nor_a_body_is_caught` |
| A failed Result with no duration is refused | `examples/invalid/result.a-run-with-no-duration.json` |
| Each Effect type is requested by its own list, and `$defs/type` names exactly those lists | `tests/test_tools.py::test_each_effect_type_is_requested_by_its_own_list` |
| A raised Finding's category and severity are finding/1's | `tests/test_tools.py::test_a_raised_finding_with_a_category_nobody_owns_is_caught` |
| The Harness hands the CLI `result/1` with its references resolved and the fields the Harness fills removed, `status` narrowed to `completed`, `incomplete` and `refused`, and `effects` narrowed to the Task's `permitted_effects` | waiting on `harness/` |
| The Harness fills `release` and `usage` from the CLI's own answer, and writes a `failed` Result, `result_invalid`, for an answer that does not validate | waiting on `harness/` |
| `apply` refuses a Result whose `run` or `release` is not the Task's, an Effect type the Task does not permit, an Effect `id` or a Finding `ref` given twice, a raised Finding posted other than exactly once, or one that does not gate posted on a thread | waiting on `harness/` |
| `apply` refuses a Disposition with neither half or both, or a half its Role may not make: an author proposes and the owner of the category decides (`config/authority.json`); one on a Finding the Task does not list, or given twice | waiting on `harness/` |
| `apply` refuses an Effect whose thread, or the thread it comments on, is not on the Task's item: a thread id is global, and the App's token reaches every item it is installed on | waiting on `harness/` |
| The Harness refuses a `completed` Result with a reason, and one of any other status without; it gives a text its trust class from the facts' actor, never from the text | waiting on `harness/` |
| `apply` submits a Role's review as a comment on the admitted commit, never an approval | waiting on `harness/` |
| `apply` writes each posted Finding's `finding/1` into the applied artifact, its source from the Task | waiting on `harness/` |
| The facts port joins a thread's category and severity from the applied artifact; the Controller names a Run by `run-name/1`, and the records port parses it | waiting on `adapters/timeline.py`, `adapters/records.py` |
