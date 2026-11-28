# 1351. Only the list refuses a push; other Lens inputs wait for model review

Status: accepted. 2026-11-28, the Solution Architect; issue 838. Narrows a row of decisions 0018, 0022 and 0026, and one of decision 0020, to what 0020 and 0188 hold. It decides nothing new.

## Decision

Two older rows still read as if every Lens's input needed a person, or were refused at the push. This record narrows each by name to the rule in force. Their text stays as written.

- The row of decisions 0018, 0022 and 0026 that opens "A Role's change to a Lens's own workflow file" (issue 113). A change under `.github/` is a protected path, so a Role's push of it is refused (0188). A change to a model Lens's own input waits for a person's approval (0052, issue 140). A change to a path that is only a deterministic Lens's input needs no person: it is pushed, and held at convergence until every model Lens has reviewed its head (0020).
- The row of decision 0020 that opens "`apply` refuses a Role's push". The push is refused where it touches the list, the protected paths and each model Lens's input, whether or not a model Lens has reviewed it, and every push where the list cannot be read (0188). A path that is only a deterministic Lens's input is pushed and held at convergence.

`harness/bundle.py` and `harness/apply.py` hold the refusal; `kernel/derive.py` and `tools/hooks/protected.py` hold the wait at convergence.

Limits: the write that lands a push is not built yet, as 0188's "What waits" says. 0188's residual stands: a pushed change to what `verify` reads is held only by the model review.

## Why

Readers of the push work found that these rows, as worded, no test can hold. Decision 0020 ruled that a Role's change to a Lens's inputs needs a model review, not a person, and 0188 refuses only the list. Merged Boundary text is never reworded, and leaving the rows waiting would only postpone the gap.

## Boundaries

| Boundary | Check |
|---|---|
| A Role's push to `.github/`, the code owners, another protected path or a model Lens's input is refused; one to a path only a deterministic Lens reads passes the list | `tests/test_apply.py::test_a_push_is_held_to_the_bases_list_by_each_class_of_path`, `harness/bundle.py`, mutant: "a push the list refuses lands" |
| `apply` refuses a push that touches the list, and every push when the list is none or empty | `tests/test_apply.py::test_a_push_that_touches_the_list_is_refused`, `tests/test_apply.py::test_a_list_that_is_none_or_empty_refuses_every_push`, `harness/apply.py`, mutant: "a push that touches the list lands" |
| A change to a model Lens's own input waits for a person's approval | `tests/test_decide.py::test_a_change_to_a_model_lenss_own_input_waits_for_a_person`, `kernel/derive.py`, mutant: "a change to a model Lens's input waits for nobody" |
| A change to a path that is only a deterministic Lens's input waits for every model Lens's review before it converges | `tests/test_decide.py::test_a_lens_input_counts_like_a_protected_path`, `kernel/derive.py`, `tools/hooks/protected.py`, mutant: "a deterministic Lens's input converges unreviewed" |
