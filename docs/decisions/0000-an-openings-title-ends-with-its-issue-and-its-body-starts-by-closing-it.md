# 0000. An opening's title ends with its issue and its body starts by closing it

Status: accepted. 2026-11-27, the Solution Architect; issue 838. Narrows decision 0238's "appends the one closing line": the line goes before the model's text. Extends 0238's bounds with the title's rule, `tools/pr_title.py`.

## Decision

`draft` in `harness/draft.py` builds what `apply` writes of a Result's `open_pull_request`, from the issue the Decision admitted.

The title is the model's text, then ` (#N)`, the issue's number. The guard reads the model's text first (`guards/opening.py`), so the model writes no number. The whole title is then held to `problems` in `tools/pr_title.py`, the rule CI's `commits` job holds it to, by that same code. A title with any problem is refused by that problem's code, never cut.

The body is `Closes #N`, a blank line, then the model's text. The line comes first, not last.

`apply` refuses a draft among its Effect checks, before any token is minted, and an opening on no issue's Run (`opening_not_on_issue`). Each code is the Role's, so a refused draft counts toward its attempts.

A Run whose Task permits an opening is told the title's rule and the room the suffix leaves (`harness/engine.py`).

`effect/1` still bounds the title at 256, what an Effect may carry. The 72 is a style rule, `LONGEST` in `tools/pr_title.py`.

Limits: the draft is held, not yet written: the writer port, `apply`'s dispatch, the push loop and GitHub's bounds in bytes are to come. The body is not held to the template's headings.

## Why

A title that breaks the rule fails CI's `commits` job after the push, so the draft could never merge. One copy of the rule keeps the writer and CI from drifting. Cutting a long title was rejected: it changes what the model wrote.

A closing line after the model's text can be swallowed by a code fence the model left open. Before it, nothing that follows changes how it reads, and no fence need be parsed. `trials/P-46.json` shows GitHub closes the issue a body's first line names.

## Boundaries

| Boundary | Check |
|---|---|
| A draft's title ends with its issue, refused by the code of any problem of the title's rule | `tests/test_apply.py::test_a_drafts_title_ends_with_its_issue_and_is_refused_on_any_problem_of_the_titles_rule`, `harness/draft.py`, mutant: "a draft's whole title is not held to the title's rule" |
| The closing line comes first, a paragraph of its own, and still closes its issue | `tests/test_apply.py::test_the_closing_line_comes_before_the_models_text_and_still_closes_its_issue`, `harness/draft.py`, mutant: "the closing line comes after the model's body" |
| A refused draft is the Role's attempt, held before any token; only an issue's Run opens one | `tests/test_apply.py::test_a_refused_draft_is_the_roles_attempt_and_its_run_was_told_the_rule`, `harness/apply.py`, mutant: "an opening's draft is not held" |
| The Run is told the title's rule and the room the suffix leaves | `tests/test_apply.py::test_a_refused_draft_is_the_roles_attempt_and_its_run_was_told_the_rule`, `harness/engine.py`, mutant: "a Run that opens a draft is not told its title's rule" |
