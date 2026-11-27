"""The mutants of `harness/draft.py`: tools/mutants.py runs them."""

TARGETS = ("harness/draft.py",)
T = "tests.test_apply.Opening."
TITLE = T + "test_a_drafts_title_ends_with_its_issue_and_is_refused_on_any_problem_of_the_titles_rule"
CLOSE = T + "test_the_closing_line_comes_before_the_models_text_and_still_closes_its_issue"
BODY = T + "test_a_drafts_body_is_refused_on_any_problem_of_the_templates_headings"
TOLD = T + "test_a_refused_draft_is_the_roles_attempt_and_its_run_was_told_the_rule"
MUTANTS = [
    # Issue 838, the Solution Architect's rulings of 2026-11-27: the title ends with the issue, held to the title's rule.
    ("a draft's whole title is not held to the title's rule", 'harness/draft.py',
     'found = pr_title.problems(whole)', 'found = []', (TITLE,)),
    ("a draft's own text is not held to the guard", 'harness/draft.py',
     'why = text.refusal(title, body)', 'why = None', (TITLE,)),
    ("a draft's body is not held to the guard", 'harness/draft.py',
     'why = text.refusal(title, body)', 'why = text.refusal(title, "x")', (TITLE,)),
    ("a draft's own title is not held to the guard", 'harness/draft.py',
     'why = text.refusal(title, body)', 'why = text.refusal("x", body)', (TITLE,)),
    ("a draft's title is not given the issue's number", 'harness/draft.py',
     'whole, written = title + SUFFIX % issue,', 'whole, written = title,', (TITLE,)),
    ("a draft's title is refused by a problem's sentence, not its code", 'harness/draft.py',
     'return found[0].split(":", 1)[0], None', 'return found[0], None', (TITLE,)),
    ("the room for a draft's title leaves none for the suffix", 'harness/draft.py',
     'return pr_title.LONGEST - len(SUFFIX % issue)', 'return pr_title.LONGEST', (TITLE,)),
    # The closing line goes before the model's text, a paragraph of its own.
    ("the closing line comes after the model's body", 'harness/draft.py',
     'written = title + SUFFIX % issue, CLOSING % issue + body',
     'written = title + SUFFIX % issue, body + "\\n\\n" + CLOSING % issue', (CLOSE,)),
    ("the closing line has no blank line after it", 'harness/draft.py',
     'CLOSING = "Closes #%d\\n\\n"', 'CLOSING = "Closes #%d\\n"', (CLOSE,)),
    # The Builder's ruling of 2026-11-27: the whole body is held to the template's headings, after the title.
    ("a draft's body is not held to the template's headings", 'harness/draft.py',
     'found = pr_title.problems(whole) or pr_title.body_problems(written)', 'found = pr_title.problems(whole)', (BODY,)),
    ("a draft's body is held before its title", 'harness/draft.py',
     'found = pr_title.problems(whole) or pr_title.body_problems(written)',
     'found = pr_title.body_problems(written) or pr_title.problems(whole)', (BODY,)),
    ("a draft's body is held without its closing line", 'harness/draft.py',
     'or pr_title.body_problems(written)', 'or pr_title.body_problems(body)', (BODY,)),
    ("a Run that opens a draft is not told the body's headings", 'harness/draft.py',
     'headings = ", ".join("## " + name for name in pr_title.HEADINGS)', 'headings = ""', (TOLD,)),
    ("a Run that opens a draft is told the body's headings out of order", 'harness/draft.py',
     'for name in pr_title.HEADINGS)', 'for name in reversed(pr_title.HEADINGS))', (TOLD,)),
]
