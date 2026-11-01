# 0052. A change to a model Lens's own inputs needs a different person's approval

Status: accepted. Replaces `docs/decisions/0046-a-change-to-a-model-lenss-own-inputs-needs-a-person.md`, and keeps
all of it but who may approve, by the Maintainer's ruling of 2026-10-22 on "Kernel: a change to a model Lens's own
inputs needs a person" (issue 140): "can't approve your own pr. Only a different person with write can approve."

## Decision

| What | Decided | Because |
|---|---|---|
| Which paths | `config/hooks.json`'s `lens_inputs` lists a model Lens's own inputs by the Lens that reads them, as it lists a deterministic Lens's. For `pr-review`: its manifest and its prompt beside it (`roles/pr-review.*`) and its own directory (`roles/pr-review/`); its rubric; the Harness whole (`harness/`), which decides what it is given and how its answer is taken; the gate, coverage and the authority table, which decide whether its Findings gate; and what makes the list: `config/hooks.json`, `config/defaults.json`, which says which Lens is a model Lens, and `tools/hooks/protected.py`, which reads both | One list, read by the session hooks and the Kernel from one function, leaves nothing to drift. Were the files that make the list off it, a change the Lens alone judged could take a row off it, or name another Lens the model Lens, and the next change would pass with no person (the security pass and the Claude review, 2026-10-21) |
| How the Kernel is told | As `model_lens_inputs`: the patterns of the entries whose Lens is a model Lens of `config/defaults.json`, built by `tools/hooks/protected.py` from the same reading as `protected_paths`, from the base branch and never the head. A list that is not a list of at least one readable pattern defers for the Maintainer, `protected_paths_unreadable`, and a queued item leaves the queue | A change cannot take itself off the list; a list that cannot be read would let a change to what a model Lens is given pass as any other |
| What it waits for | A pull request that changes one converges only once every model Lens has reviewed its current head, as for any path on the list, and a person has approved that head. It waits in `verifying`, `model_lens_input_needs_person`, naming each pattern it matched, the Maintainer's to see, and a queued item leaves the queue | With one model family, "another model family" does not exist: the only judge that is not the Lens is a person |
| Whose approval | An approval of this content that stands, by a person with write access other than the author and the last pusher: never the machine user, whoever made its approval, and never an App or a Lens's App. That person's latest verdict counts, so a later request for changes supersedes it, whoever dismissed the request, as the gate reads a request. Only a person's dismissal ends it: an App's, a Lens's among them, ends nothing a person did (L-17). A comment, a request for changes, an approval of an earlier head, or one by an account with no write access is not one. The Maintainer's own change to these paths needs a colleague's approval, or the Maintainer's merge by hand outside the Factory | The Maintainer, 2026-10-22: "can't approve your own pr. Only a different person with write can approve." Once the approving act exists ("The approving act: the machine user approves from a Run with no Engine, bound to the admitted commit", issue 195), the machine user's approval is also the Factory's own, so counting it would let the Factory approve a change to its own review and converge on that approval. Decision 0046 counted the machine user's approval as the Maintainer's, and this is the one rule it decides otherwise |
| The Factory's own approval | It never supplies the judgment: the machine user's approval is no judgment here at all, and no Decision issues an approval for such a change while no person's approval stands, since the wait is read before the approval is due | The Maintainer's ruling on ruling 3, 2026-10-21 and 2026-10-22 |
| The gating files | `kernel/gate.py`, `kernel/coverage.py` and `config/authority.json`, which decide whether the review's Findings gate, are among pr-review's own inputs too | The orchestrator's ruling of 2026-10-21, after the security pass and the Claude review: the cost is the Maintainer's approval on rare pull requests |

## Why

It decides one sentence of
`docs/decisions/0020-a-change-to-the-factorys-own-rules-or-a-lenss-inputs-is-reviewed-by-a-model-lens.md` otherwise, for
these paths only: a change to them converges once every model Lens has reviewed its head and a different person with
write access has approved it. Under decision 0020 a change to a path on the list converges once every model Lens has reviewed its head. The only model
Lens is `pr-review`, so from the day its manifest and prompt exist, it would judge a change to itself. When a second model
Lens of another family exists, its review of the head may stand for the person's, by a decision of its own then.

## Boundaries

| Boundary | Check |
|---|---|
| The scorer, the set's manifest and the eval's own code are listed paths too (decision 0110) | `tests/test_decide.py::test_a_change_to_what_grades_the_review_waits_for_a_person` |
| A change to each listed path, or a rename or copy out of one, waits for a person after the model review, naming each pattern it matched; another Role's file, or one further down, does not | `tests/test_decide.py::test_a_change_to_a_model_lenss_own_input_waits_for_a_person` |
| A standing approval of the current head by a different person with write access, as that person's latest verdict, lets it converge, an App's dismissal of it ending nothing; one a later request supersedes, an earlier head's, one a person dismissed, a comment, the machine user's, an App's, a Lens's, one with no write access, the author's or the last pusher's does not | `tests/test_decide.py::test_a_persons_approval_of_the_current_head_lets_it_converge` |
| A model review alone never suffices, and a queued item without a person's approval leaves the queue | `tests/test_decide.py::test_a_model_review_alone_never_suffices` |
| The Maintainer's own change waits for a colleague's approval | `tests/test_decide.py::test_the_maintainers_own_change_waits_for_another_judge` |
| The Factory's own approving act never supplies the judgment, and the machine user's approval never judges such a change | `tests/test_decide.py::test_the_factorys_own_approval_never_supplies_the_judgment`, `tests/test_decide.py::test_the_machine_users_approval_never_judges_a_change_to_a_model_lenss_input` |
| The list is the configuration's, never the change's, and the files that make it are on it | `tests/test_decide.py::test_the_list_is_the_configurations_never_the_change` |
| An unreadable list defers for the Maintainer, and a queued item leaves the queue | `tests/test_decide.py::test_an_unreadable_list_of_a_model_lenss_inputs_defers_for_the_maintainer` |
| The Controller builds the list from the base branch's `config/hooks.json` | waiting on `adapters/settings.py` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
