# 0045. A change to a model Lens's own inputs needs a person

Status: accepted. Taken as a working ruling on 2026-10-21, which the Maintainer may overturn in review, for "Kernel: a
change to a model Lens's own inputs needs a person" (issue 140), re-scoped that day into slice 1, ahead of the third
pull request of "Harness: run and apply for the review Intent, and the model holds no credential that can write"
(issue 194), which creates the review Role's manifest and prompt. It decides one sentence of
`docs/decisions/0020-a-change-to-the-factorys-own-rules-or-a-lenss-inputs-is-reviewed-by-a-model-lens.md` otherwise, for
these paths only: a change to them converges once every model Lens has reviewed its head and a person has judged it.

## Decision

| What | Decided | Because |
|---|---|---|
| Which paths | `config/hooks.json`'s `lens_inputs` lists a model Lens's own inputs by the Lens that reads them, as it lists a deterministic Lens's: for `pr-review`, its manifest and its prompt beside it (`roles/pr-review.*`), its rubric, and the Harness code that decides what it is given and how its answer is taken (task.py and engine.py, in the Harness, which waits on `harness/`) | One list, read by the session hooks and the Kernel from one function, leaves nothing to drift, and the Lens a path belongs to is already beside it |
| How the Kernel is told | As `model_lens_inputs`: the patterns of the entries whose Lens is a model Lens of `config/defaults.json`, built by `tools/hooks/protected.py` from the same reading as `protected_paths`, from the base branch and never the head. A list that is not a list of at least one readable pattern defers for the Maintainer, `protected_paths_unreadable`, and a queued item leaves the queue | A change cannot take itself off the list; a list that cannot be read would let a change to what a model Lens is given pass as any other |
| What it waits for | A pull request that changes one converges only once every model Lens has reviewed its current head, as for any path on the list, and a person has judged that head. It waits in `verifying`, `model_lens_input_needs_person`, naming each pattern it matched, the Maintainer's to see, and a queued item leaves the queue | With one model family, "another model family" does not exist: the only judge that is not the Lens is a person |
| Who is a person's judgment | An approval of this content, standing, by a person with write access who is neither the author nor the last pusher; or the Maintainer's own change, which the Maintainer opened and whose head the Maintainer pushed. A dismissed approval, one of an earlier head, a comment, the machine user's, a Lens's, or one by someone with no write access is not | GitHub counts no author's approval of their own pull request, so without the second, the Maintainer's own change to these paths could never converge; anyone else's push puts content of theirs in it, which no person has judged |

## Why

Under decision 0020 a change to a path on the list converges once every model Lens has reviewed its head. The only model
Lens is `pr-review`, so from the day its manifest and prompt exist, it would judge a change to itself. When a second model
Lens of another family exists, its review of the head may stand for the person's, by a decision of its own then.

## Boundaries

| Boundary | Check |
|---|---|
| A change to each listed path waits for a person after the model review, naming each pattern it matched | `tests/test_decide.py::test_a_change_to_a_model_lenss_own_input_waits_for_a_person` |
| A person's standing approval of the current head lets it converge; an earlier head's, a dismissed one, a comment, the machine user's, a Lens's, or one with no write access does not; nor the last pusher's | `tests/test_decide.py::test_a_persons_approval_of_the_current_head_lets_it_converge` |
| A model review alone never suffices, and a queued item without a person's judgment leaves the queue | `tests/test_decide.py::test_a_model_review_alone_never_suffices` |
| The Maintainer's own change, opened and pushed by the Maintainer, is a person's judgment; anyone else's push is not | `tests/test_decide.py::test_the_maintainers_own_change_is_a_persons_judgment` |
| The list is the configuration's, never the change's | `tests/test_decide.py::test_the_list_is_the_configurations_never_the_change` |
| An unreadable list defers for the Maintainer, and a queued item leaves the queue | `tests/test_decide.py::test_an_unreadable_list_of_a_model_lenss_inputs_defers_for_the_maintainer` |
| The Controller builds the list from the base branch's `config/hooks.json` | waiting on `adapters/settings.py` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
