"""The mutants of `harness/draft.py`: tools/mutants.py runs them."""

TARGETS = ("harness/draft.py",)
T = "tests.test_apply.Opening."
TITLE = T + "test_a_drafts_title_ends_with_its_issue_and_is_refused_on_any_problem_of_the_titles_rule"
CLOSE = T + "test_the_closing_line_comes_before_the_models_text_and_still_closes_its_issue"
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
     'whole = title + SUFFIX % issue', 'whole = title', (TITLE,)),
    ("a draft's title is refused by a problem's sentence, not its code", 'harness/draft.py',
     'return found[0].split(":", 1)[0], None', 'return found[0], None', (TITLE,)),
    ("the room for a draft's title leaves none for the suffix", 'harness/draft.py',
     'return pr_title.LONGEST - len(SUFFIX % issue)', 'return pr_title.LONGEST', (TITLE,)),
    # The closing line goes before the model's text, a paragraph of its own.
    ("the closing line comes after the model's body", 'harness/draft.py',
     'return None, (whole, CLOSING % issue + body)', 'return None, (whole, body + "\\n\\n" + CLOSING % issue)', (CLOSE,)),
    ("the closing line has no blank line after it", 'harness/draft.py',
     'CLOSING = "Closes #%d\\n\\n"', 'CLOSING = "Closes #%d\\n"', (CLOSE,)),
]
