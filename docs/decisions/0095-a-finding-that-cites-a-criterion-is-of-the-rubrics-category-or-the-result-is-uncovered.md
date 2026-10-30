# 0095. A Finding that cites a criterion is of the rubric's category, or the Result is uncovered

Status: accepted. The Factory Builder's ruling of 2026-10-29 on section 3.14, which the Maintainer may overturn in
review, on issue 407, "A Finding that cites a rubric criterion: is its category the criterion's, as its severity is? A ruling on §3.14".
It extends `docs/decisions/0088-a-finding-that-cites-a-criterion-has-the-rubrics-severity-or-the-result-is-uncovered.md`,
whose Decision stays in force, and closes the gap 0088 left open.

## Decision

| What | Decided | Because |
|---|---|---|
| A cited Finding's category | A Finding that cites a criterion of the rubric is of the category the rubric gives that criterion, as it has its severity (0088). `kernel/coverage.py`'s `covered` reads both: a Finding at another category, or at none, leaves that criterion uncovered, whether it applies or not, named once however many ways it is wrong. `apply` then refuses the Result, `item`, `uncovered`, before any Effect | The category says who owns a Finding's Disposition and which guards hold it (section 3.8). A Finding that cites the security criterion under another category escaped those guards, the refusal of an accepted decision on a `security` thread (`security_proposal_unread`) among them |
| Refused, never rewritten | The rubric's category is not put in place of the Finding's. A relabelled Finding is a defect of the Result, and the Run fails with the `item` outcome | `apply` writes what a Result says or nothing (decisions 0038 and 0050), as 0088 says of severity |
| A Finding off the rubric | One that cites no criterion keeps the category it gives, owned through the authority table as before (`tools/check_authority.py`) | A rubric is a floor, not a ceiling (section 3.14) |
| A rubric's category | A rubric is read only when each criterion gives a category among the Factory's, `kernel/terms.py`'s `CATEGORIES`. One that does not is `unreadable`, the Factory's fault, `environment` | A Finding citing a criterion with no category could be given none |
| The Role's words | The review Role's instructions say a cited Finding has its criterion's category, as they say of its severity (`roles/pr-review/prompt.md`) | So that an honest Result is not refused for a rule it was never told |

## Why

Decision 0088 bound a cited Finding's severity to the rubric and left its category to the model. Every criterion of
`config/rubric-pr-review.json` gates, so a relabelled Finding still gated. But its category decides who owns its
Disposition and whether a decline is allowed, and a security criterion's Finding labelled `functional` was held to a
functional Finding's rules. Section 3.14 now says both come from the criterion.

## Boundaries

| Boundary | Check |
|---|---|
| A Finding that cites a criterion is of the rubric's category: another, or none, leaves it uncovered, whether it applies or not, named once with a wrong severity too; the security criterion's Finding relabelled is uncovered; one off the rubric keeps its own | `tests/test_coverage.py::test_a_finding_that_cites_a_criterion_has_the_rubrics_category` |
| A rubric with a criterion that gives no category among the Factory's is unreadable, never covered | `tests/test_coverage.py::test_an_unreadable_rubric_is_unreadable_never_covered` |
| A cited Finding relabelled, and the security criterion's Finding under another category, write nothing: `item`, `uncovered`; of its own category it is taken | `tests/test_apply.py::test_an_uncovered_result_writes_nothing` |
| Each part of the rule has a mutant a test kills | `tools/mutants.py` |
