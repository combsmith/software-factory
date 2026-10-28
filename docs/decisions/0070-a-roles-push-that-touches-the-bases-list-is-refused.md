# 0070. A Role's push that touches the base's list is refused

Status: accepted. Taken as working rulings on 2026-10-26, which the Maintainer may overturn in review, for "Harness: apply refuses a Role's push to a protected path or a Lens's input that no model Lens has reviewed" (issue 139). It refuses earlier what `docs/decisions/0020-a-change-to-the-factorys-own-rules-or-a-lenss-inputs-is-reviewed-by-a-model-lens.md` holds at convergence, over the list `docs/decisions/0052-a-change-to-a-model-lenss-own-inputs-needs-a-different-persons-approval.md` extends.

## Decision

| What | Decided | Because |
|---|---|---|
| What is refused | A Role's push that changes a path on the list, or renames or copies one out of it, is refused, `push_protected`, a fault of the Role's. A path that cannot be read as one from the top of the repo (an empty name, `.`, `..`, a leading `/`, a control character, a backslash, or no text), or paths that are no list, are refused too | A push lands content no model Lens has reviewed, by construction: "no model Lens has reviewed" is simply "it touches the list". Such a change is a person's to push, and 0020 and 0052 then hold it at convergence |
| The list | `config/hooks.json` as the pull request's base commit holds it, never the head's, read by `adapters/rules.py`, `GET /repos/{repo}/contents/config/hooks.json?ref={base sha}`, through the transport with the token `apply` holds, the base sha taken from the trusted read of the pull request and never from the head, since GitHub answers `?ref=` with a commit of any fork: every protected path and every Lens's input, each once, so a model Lens's inputs among them. It is read and matched by `tools/hooks/protected.py`, the function and syntax the Kernel's `protected_paths` comes from | A change cannot take itself off the list (0020) |
| A list that cannot be read | A read that fails, a file of another path, size or encoding, or a text that is no list the hook reads, is `push_list_unreadable`, a fault of the Factory's; so is an empty list handed to the refusal, or one holding what the Kernel reads as no pattern (`kernel/derive.py`'s `readable_pattern`). Never an empty list, so never a push let through | An unreadable fact never yields an action |
| Where it is called | Nowhere yet: no Effect pushes. `harness/apply.py`'s `push_refusal` and `adapters/rules.py` stand before slice 2's push Effect, whose shape is that slice's design beside "Design: a Run with tools cannot both hide the model credential and hold writes (P-26, P-50, P-51); choose the run job's shape before the first Intent with tools" (issue 314); that Effect must call them, and a refusal then lands in the run record as every refusal does, each Effect listed refused with its reason. Issue 139 stays open for that | Fixing the push Effect's shape now would fix it before its design |

## Why

Decision 0020 left this out of its scope: it holds such a change once it is a pull request's head, until every model
Lens has reviewed it. A Role that could push to the list would still land, on a branch, a change to the rules that
judge it. Refusing the push is the same rule, read before anything is written.

## Boundaries

| Boundary | Check |
|---|---|
| A push that changes a path on the list, at any depth below a directory on it, in any case, or renames one out of it, is refused | `tests/test_apply.py::test_a_push_that_touches_the_list_is_refused` |
| A push that touches nothing on the list is not refused, at the glob's edges | `tests/test_apply.py::test_a_push_that_touches_nothing_on_the_list_is_not_refused` |
| A path that cannot be read as one is refused | `tests/test_apply.py::test_a_path_that_cannot_be_read_as_one_is_refused` |
| A list that is none, empty or holds what is no pattern refuses every push as unreadable | `tests/test_apply.py::test_a_list_that_is_none_or_empty_refuses_every_push` |
| The repo's own list holds the Kernel and the review Role's inputs | `tests/test_apply.py::test_the_repos_own_list_holds_the_kernel_and_the_review_roles_inputs` |
| The list is the base commit's, every protected path and Lens's input once | `tests/test_adapters.py::test_the_list_is_the_bases_every_protected_path_and_lens_input_once` |
| A list that cannot be read is unreadable, never empty, and coordinates that name no commit are not asked | `tests/test_adapters.py::test_a_list_that_cannot_be_read_is_unreadable_never_empty` |
| `apply` calls the refusal on every push Effect, and its refusal is in the run record | waiting on `harness/push.py` |
| A list pattern with a backslash or a control character, which no path may hold, refuses every push as unreadable, and the list that holds one cannot be read at all | `tests/test_apply.py::test_a_list_that_is_none_or_empty_refuses_every_push`, `tests/test_hooks.py::test_a_path_with_a_control_character_or_a_backslash_is_refused`, `tools/check_examples.py` |
| A list answered with no 200, or whose size is no integer, is unreadable, and a repo named `.` is not asked | `tests/test_adapters.py::test_a_list_that_cannot_be_read_is_unreadable_never_empty` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
