# 0088. A Finding that cites a criterion has the rubric's severity, or the Result is uncovered

Status: accepted. Adds to `docs/decisions/0049-a-reviewing-run-that-leaves-a-criterion-uncovered-has-not-reported-and-one-that-ran-and-left-no-outcome-is-an-attempt.md`
and keeps all of it. It holds the rule section 3.14 already states, "the severity comes from the rubric", which
nothing held:
"The executor takes the model's severity for a rubric-linked finding instead of the rubric's, so a downgrade skips the blocking thread"
(issue 373).

## Decision

A Finding that cites a criterion of the rubric has the severity the rubric gives that criterion,
`severity_if_violated`, never the model's (§3.14). `kernel/coverage.py`'s `covered` reads it: a
Finding that cites a criterion at another severity, or at none, leaves that criterion uncovered,
whether the criterion applies or not, named once beside the rest. `apply` then refuses the Result,
`item`, `uncovered`, before any Effect, as decision 0049 says of every uncovered Result. A Finding
that cites an id the rubric does not have is uncovered as a coverage entry for one already is, shown
as that id. A Finding that cites no criterion keeps the severity the model gives it: a rubric is a
floor, not a ceiling. The review Role's instructions say so (`roles/pr-review/prompt.md`).

A rubric is read only when each criterion gives a severity, one of `blocking`, `major`, `minor` and
`info`. One that does not is `unreadable`, the Factory's fault, `environment`; a review whose rubric
cannot be read is never asked (decision 0062).

The Result is refused. The rubric's severity is not put in its place.

## Why

Whether a Finding gates is read from its category and its severity (§4.2), and so is where `apply`
posts it: a thread for one that gates, an annotation for one that does not (§3.7). Read from the
model, a severity let a model steered by the diff it reads grade a `major` criterion's Finding
`minor` and post it as an annotation on a check run that succeeds. No thread holds the merge, and
the Kernel reaches `approval_due`.

Refused, not overridden. `apply` writes what a Result says or nothing, and never rewrites a Role's
words (decisions 0038 and 0050). Coverage already refuses a Finding that contradicts its criterion, as one
citing a criterion the Result says is `met` does. A Finding given the rubric's severity could need
another surface than the one the Result chose. One graded above the rubric is refused too: the
rubric says what the severity is, not its floor. The cost is an attempt, which `max_attempts`
bounds.

Not decided here: a Finding's category is not yet bound to its criterion's. Section 3.14 does not
say the category comes from the rubric. Every criterion of `config/rubric-pr-review.json` is
`major` or `blocking`, so a cited Finding gates whatever category it is given. But the category
still says who owns its Disposition (§3.8), and a Finding citing a `security` criterion under
another category escapes the guards that refuse a `security` Finding's decline. So the gap is
open, not closed. Issue 407 asks for the ruling:
"A Finding that cites a rubric criterion: is its category the criterion's, as its severity is? A ruling on §3.14".

## Boundaries

| Boundary | Check |
|---|---|
| A Finding that cites a criterion has the rubric's severity: below it, above it or none leaves the criterion uncovered, whether it applies or not, named once, every Finding read; one citing an id the rubric lacks is uncovered as that id; one citing none keeps the model's | `tests/test_coverage.py::test_a_finding_that_cites_a_criterion_has_the_rubrics_severity` |
| A rubric with a criterion that gives no severity among the four is unreadable, never covered | `tests/test_coverage.py::test_an_unreadable_rubric_is_unreadable_never_covered` |
| A cited Finding graded below its criterion and posted as an annotation, or above it on a review, writes nothing: `item`, `uncovered`; off the rubric, it is posted as the model graded it | `tests/test_apply.py::test_an_uncovered_result_writes_nothing` |
| Each part of the rule has a mutant a test kills | `tools/mutants.py` |
