# 0045. A change to a model Lens's own inputs needs a person

Status: accepted. Taken as a working ruling on 2026-10-21, which the Maintainer may overturn in review, for "Kernel: a
change to a model Lens's own inputs needs a person" (issue 140), re-scoped that day into slice 1, ahead of the third
pull request of "Harness: run and apply for the review Intent, and the model holds no credential that can write"
(issue 194), which creates the review Role's manifest and prompt. It decides one sentence of
`docs/decisions/0020-a-change-to-the-factorys-own-rules-or-a-lenss-inputs-is-reviewed-by-a-model-lens.md` otherwise, for
these paths only: a change to them converges once every model Lens has reviewed its head and a person has approved it.

## Decision

| What | Decided | Because |
|---|---|---|
| Which paths | `config/hooks.json`'s `lens_inputs` lists a model Lens's own inputs by the Lens that reads them, as it lists a deterministic Lens's. For `pr-review`: its manifest and its prompt beside it (`roles/pr-review.*`) and its own directory (`roles/pr-review/`); its rubric; the Harness whole (`harness/`), which decides what it is given and how its answer is taken; and what makes the list: `config/hooks.json`, `config/defaults.json`, which says which Lens is a model Lens, and `tools/hooks/protected.py`, which reads both | One list, read by the session hooks and the Kernel from one function, leaves nothing to drift. Were the files that make the list off it, a change the Lens alone judged could take a row off it, or name another Lens the model Lens, and the next change would pass with no person (the security pass and the Claude review, 2026-10-21) |
| How the Kernel is told | As `model_lens_inputs`: the patterns of the entries whose Lens is a model Lens of `config/defaults.json`, built by `tools/hooks/protected.py` from the same reading as `protected_paths`, from the base branch and never the head. A list that is not a list of at least one readable pattern defers for the Maintainer, `protected_paths_unreadable`, and a queued item leaves the queue | A change cannot take itself off the list; a list that cannot be read would let a change to what a model Lens is given pass as any other |
| What it waits for | A pull request that changes one converges only once every model Lens has reviewed its current head, as for any path on the list, and a person has approved that head. It waits in `verifying`, `model_lens_input_needs_person`, naming each pattern it matched, the Maintainer's to see, and a queued item leaves the queue | With one model family, "another model family" does not exist: the only judge that is not the Lens is a person |
| Whose approval | A person with write access who is neither the author nor the last pusher, approving this content in a review that stands, as that person's latest verdict: a later request for changes supersedes it, whoever dismissed the request, as the gate reads a request. Only a person's dismissal ends it: an App's, a Lens's among them, ends nothing a person did (L-17). A comment, a request for changes, an approval of an earlier head, the machine user's, a Lens's, or one by someone with no write access is not one. The Maintainer's own change waits for another person too | A session pushes as the Maintainer (L-44), so opening and pushing a change judges no head: the clause that read the Maintainer's own change as a person's judgment was taken out in review. GitHub counts no author's approval of their own pull request, so the Maintainer's own change to these paths needs a second person, or is merged by the Maintainer's own hand outside the Factory |
| Not covered here | `kernel/gate.py`, `kernel/coverage.py` and `config/authority.json`, which decide whether the review's Findings gate, are on the list as protected paths, reviewed by every model Lens, and not as the model Lens's own inputs | Raised by the security pass and the Claude review; whether they join the list is the orchestrator's to rule, as it widens the story |

## Why

Under decision 0020 a change to a path on the list converges once every model Lens has reviewed its head. The only model
Lens is `pr-review`, so from the day its manifest and prompt exist, it would judge a change to itself. When a second model
Lens of another family exists, its review of the head may stand for the person's, by a decision of its own then.

## Boundaries

| Boundary | Check |
|---|---|
| A change to each listed path, or a rename or copy out of one, waits for a person after the model review, naming each pattern it matched; another Role's file, or one further down, does not | `tests/test_decide.py::test_a_change_to_a_model_lenss_own_input_waits_for_a_person` |
| A person's standing approval of the current head, as their latest verdict, lets it converge, an App's dismissal of it ending nothing; one a later request supersedes, an earlier head's, one a person dismissed, a comment, the machine user's, a Lens's, one with no write access, the author's or the last pusher's does not | `tests/test_decide.py::test_a_persons_approval_of_the_current_head_lets_it_converge` |
| A model review alone never suffices, and a queued item without a person's approval leaves the queue | `tests/test_decide.py::test_a_model_review_alone_never_suffices` |
| The Maintainer's own change waits for another person | `tests/test_decide.py::test_the_maintainers_own_change_waits_for_another_person` |
| The list is the configuration's, never the change's, and the files that make it are on it | `tests/test_decide.py::test_the_list_is_the_configurations_never_the_change` |
| An unreadable list defers for the Maintainer, and a queued item leaves the queue | `tests/test_decide.py::test_an_unreadable_list_of_a_model_lenss_inputs_defers_for_the_maintainer` |
| The Controller builds the list from the base branch's `config/hooks.json` | waiting on `adapters/settings.py` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
