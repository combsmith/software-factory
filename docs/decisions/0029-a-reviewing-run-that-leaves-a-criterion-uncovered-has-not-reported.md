# 0029. A reviewing Run that leaves a criterion uncovered has not reported

Status: accepted.

## Decision

A reviewing Result reports coverage: for each criterion of its rubric that applies, `met`, a
Finding that cites it, or `not_applicable` with a reason that is a code (§3.14, I-37). Coverage is
`coverage/1`, `schemas/coverage.schema.json`: a list of `{criterion, verdict, reason}`, `verdict`
one of `met`, `finding` and `not_applicable`, `reason` a code or null. It lives in the Result, never
in the facts: the Kernel never reads a Result (§3.9), and the facts gain no field.

Whether a Result is covered is one pure function, `kernel/coverage.py`'s
`covered(rubric, coverage, findings, changed)`, which says `covered`, `uncovered` with the ids it
left uncovered, or `unreadable`. A criterion applies when it has no `applies_when`, or when a path
the change touches, a renamed file's previous path among them, is what one of its patterns names,
read with `matches`, the one matcher; one whose `applies_when` cannot be read applies. A criterion
that applies is uncovered when it has no entry, or two; when its verdict is `finding` and no Finding
cites it; when a Finding cites it and its verdict is not `finding`; and when its verdict is
`not_applicable` and its reason is not a code. So is an entry for an id the rubric does not have,
named by that id, or as `unreadable` when it is none. An entry for a criterion that does not apply
is passed over. A rubric that cannot be read, or paths not read whole, are `unreadable`.

The path syntax gains one form: `**` as a whole name stands for any run of names, none included.
`matches` reads it, and the session hooks' matcher reads it alike, so the rubric's `**/*.py` reaches
a Python file at any depth. No path the hooks protect or report may use it yet: where a command
writes below a directory, the hooks read each name of a path as one name. `kernel/coverage.py` is a
protected path.

`apply` asks `covered` before any Effect. An uncovered Result ends its Run with conclusion `failure`
and outcome `item`: those are the run record's fields that say so, and no field is added. An
unreadable one ends it `failure` and `environment`, the Factory's fault, which spends none of the
item's attempts (I-23).

A required model Lens has reported on this content only through a Run of its review of this content
that succeeded. After a review Run that failed, whatever its conclusion, the item stays `verifying`
and `awaiting_review`, and the same Lens's review is admitted again. Each one that failed by the
item is an attempt of `review-change`: at `max_attempts` since a person with write access acted,
the item is held, `attempts_exhausted`, with those Runs' ids, for the Maintainer. Each counts toward
the Run ceiling and stops under a Pause. A review Run that failed with no outcome is no report and
no attempt, and the Run ceiling bounds it. A review of this content that succeeded and names an
outcome contradicts itself: it is `run_unreadable`, read where the wait for a review is read, a
deferral for the Maintainer with the Run's id as evidence, and it takes a queued item out.

## Why

A Result is the model's word, so the Kernel reads only what follows from it, the run record, as it
reads every other Run. A Result that does not say what it looked at cannot be told from one that
did not look (§3.14). The schema can say what an entry is, but not that every criterion that applies
has one, so the rule is a function with an example the function covers and a counter-example, valid
to the schema, that it refuses. Its evidence is criterion ids and codes, which `apply` can post.

A broken rubric is the Factory's fault, and must not spend the item's attempts. A model's output
varies, so an uncovered review is tried again, and the brakes that bound every other Run bound it:
no lower limit for reviews is set until its cost shows. Read as reporting, a review whose Result
was refused would let content converge on a review that applied nothing.

`fits` read `**/*.py` as one wildcard within one name, then another, so PR-3 applied only to a
Python file one directory deep. The matcher the Kernel and the hooks share is the one place to fix
it, and the test that holds the two to one corpus now reads the rubric's patterns too.

The working ruling on "Kernel: a reviewing Run that leaves a rubric criterion uncovered has not
reported" (issue 16) gave the record the next number, 0029. Coverage is the Result's, and the Result's
schema is "Schemas for Task, Result, Effect and Disposition" (issue 19), which waits on trials for
usage, not coverage, so coverage has its own schema now.

## Boundaries

| Boundary | Check |
|---|---|
| A review Run that failed, timed out or was cancelled, each by the item, has not reported; a later one on the same content that succeeded has. Each is an attempt, held at the limit with their ids; one that failed with no outcome is no attempt, and the Run ceiling holds it | `tests/test_decide.py::test_a_review_run_that_failed_has_not_reported`, `tests/test_decide.py::test_item_faults_exhaust_attempts` |
| A review of this content that succeeded and names an outcome is `run_unreadable`, a deferral for the Maintainer naming the Run, beside a review that reported or not, and takes a queued item out; one on other content, or of another Intent, is not read | `tests/test_decide.py::test_a_review_that_succeeded_with_a_fault_is_unreadable` |
| A criterion that applies is covered only by one entry that reports on it; an entry for an id the rubric lacks is uncovered, and one for a criterion that does not apply is passed over; an `applies_when` that cannot be read applies | `tests/test_coverage.py::test_a_criterion_that_applies_must_be_covered` |
| A renamed file's previous path makes a criterion apply | `tests/test_coverage.py::test_a_renamed_files_old_path_makes_a_criterion_apply` |
| `not_applicable` needs a reason that is a code | `tests/test_coverage.py::test_not_applicable_needs_a_reason_code` |
| `finding` needs a Finding that cites the criterion, and a Finding that cites one needs the verdict `finding` | `tests/test_coverage.py::test_a_finding_verdict_needs_a_finding_that_cites_it` |
| A rubric that cannot be read, or paths not read whole, are unreadable, never covered | `tests/test_coverage.py::test_an_unreadable_rubric_is_unreadable_never_covered` |
| `**` as a whole name stands for any run of names, none included, in the Kernel's matcher and the hooks' alike, on the rubric's patterns too | `tests/test_tools.py::test_two_stars_as_a_whole_name_stand_for_any_run_of_names`, `tests/test_tools.py::test_the_kernels_matcher_and_the_hooks_agree_on_one_corpus` |
| A protected or reported path with `**` as a whole name is refused by the hooks, until their reading of a directory that holds a protected path reads it | `tests/test_hooks.py::test_a_protected_or_reported_path_with_two_stars_is_refused` |
| The coverage example is covered against the rubric, the Finding example and the paths of the facts example; the counter-example, valid to the schema, is refused by `covered` | `examples/invalid/coverage.a-criterion-that-applies-left-out.json`, `tests/test_tools.py::test_a_coverage_that_leaves_a_criterion_uncovered_is_caught` |
| Under faults, a review is now and then uncovered; it is admitted again and, at its attempts, held. An approval or a merge has a review of that content that succeeded by every required model Lens, a Lens's thread comes only from one that succeeded, and uncovered review Runs since a writer acted are at most `max_attempts` | `tests/test_simulator.py::test_the_seeds_serve_a_review_that_left_a_criterion_uncovered`, `tests/test_simulator.py::test_invariants_hold_under_faults` |
| `apply` calls `covered` before any Effect, and ends an uncovered Run `failure` and `item`, an unreadable one `failure` and `environment` | waiting on `harness/` |
| The port reads the outcome of a Run that did not succeed | waiting on `adapters/artifacts.py` |
| The Result's schema takes `coverage/1` by reference, in "Schemas for Task, Result, Effect and Disposition" (issue 19) | `schemas/result.schema.json`, `tools/check_examples.py` |
