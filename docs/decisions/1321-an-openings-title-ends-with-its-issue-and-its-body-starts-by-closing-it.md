# 1321. An opening's title ends with its issue and its body starts by closing it

Status: accepted. 2026-11-27, the Solution Architect and, for the body's headings, the Factory Builder; issue 838. Narrows decision 0238's "appends the one closing line": the line goes before the model's text. Extends 0238's bounds with the title's and the body's rules, `tools/pr_title.py`.

## Decision

`draft` in `harness/draft.py` builds the draft of a Result's `open_pull_request` from the admitted issue.

The title is the model's text, then ` (#N)`, the issue's number. The guard reads the model's text first (`guards/opening.py`). The whole title is then held to `problems` in `tools/pr_title.py`, CI's own code. Any problem refuses it by that problem's code; it is never cut.

The body is `Closes #N`, a blank line, then the model's text. The line comes first, not last. The whole body is held to the template's headings, `body_problems`, refused by a problem's code.

`apply` refuses a draft before any token is minted, and an opening on no issue's Run (`opening_not_on_issue`). Each code is the Role's attempt.

A Run whose Task permits an opening is told the title's rule, the room the suffix leaves, the body's headings and what the guard refuses (`harness/engine.py`).

`effect/1` still bounds the title at 256, what an Effect may carry. The 72 is a style rule, `LONGEST` in `tools/pr_title.py`.

This amends the wording of `schemas/effect.schema.json`, which still says `apply` appends the line.

Limits: the draft is held, not yet written: the writer port, which must open it in the issue's own repo, `apply`'s dispatch, the push loop and GitHub's bounds in bytes are to come.

## Why

A title or body that breaks the rule fails CI's `commits` job after the push, so the draft could never merge. One copy of the rule keeps the writer and CI from drifting. Cutting a long title was rejected: it changes what the model wrote.

A closing line after the model's text can be swallowed by a code fence the model left open. Before it, nothing that follows changes how it reads. `trials/P-46.json` shows GitHub reads a body's first line as a closing reference, and `trials/P-67.json` that the merge then closes its issue.

## Boundaries

| Boundary | Check |
|---|---|
| A draft's title ends with its issue, refused by the code of any problem of the title's rule | `tests/test_apply.py::test_a_drafts_title_ends_with_its_issue_and_is_refused_on_any_problem_of_the_titles_rule`, `harness/draft.py`, mutant: "a draft's whole title is not held to the title's rule" |
| The closing line comes first, a paragraph of its own, and still closes its issue | `tests/test_apply.py::test_the_closing_line_comes_before_the_models_text_and_still_closes_its_issue`, `harness/draft.py`, mutant: "the closing line comes after the model's body" |
| A draft's body is refused by the code of any problem of the template's headings, after the title | `tests/test_apply.py::test_a_drafts_body_is_refused_on_any_problem_of_the_templates_headings`, `harness/draft.py`, mutant: "a draft's body is not held to the template's headings" |
| A refused draft is the Role's attempt, held before any token; only an issue's Run opens one | `tests/test_apply.py::test_a_refused_draft_mints_nothing`, `harness/apply.py`, mutant: "an opening's draft is not held" |
| The Run is told the title's rule, the room the suffix leaves, the body's headings and what the guard refuses | `tests/test_apply.py::test_a_refused_draft_is_the_roles_attempt_and_its_run_was_told_the_rule`, `harness/engine.py`, mutant: "a Run that opens a draft is not told its title's rule" |
