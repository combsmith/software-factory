# 0135. A description edited after the first approval since a person looked holds the item

Status: accepted. The Factory Builder's rulings of 2026-11-03 on "A description edited after the approval holds the enqueue and asks a person again" (issue 519), part of "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182). It holds what decision 0132 only reads afterwards, and narrows I-28.

## Decision

| What | Decided | Because |
|---|---|---|
| The rule | A pull request reads `held`, `description_edited_after_approval`, needing a person, while its description's last edit is later than its anchor. On an outsider's pull request the anchor is a person's last look itself; on any other, the machine user's first approval, dismissed since or not, after a person last looked. A person looks by approving, as a person with write access, or by admitting an outsider's pull request. A person's approval after the edit clears it. A queued item leaves the queue on it. Whoever made the edit, a reviewer App's among them | An approval covers the diff, not the description, whose closing keywords GitHub acts on at the merge (trials/P-48.json). An edit is not made safe by its editor's kind: a reviewer App writes from the pull request's own text (trials/P-58.json) |
| The first approval, never the latest | A fresh machine approval never moves the anchor | A push or a dismissal brings a fresh approval, which would otherwise clear the edit with no person looking |
| Two anchors | On the Factory's and a maintainer's own pull requests, an edit before the first approval since a person looked holds nothing. On an outsider's, any edit after the admission or a person's approval holds, before any approval too | Reviewer Apps edit about 23 seconds after opening (P-58), long before any approval, so the Factory's own pull requests stay autonomous. An outsider's pull request already costs a person's look, and its description's author is the threat: an edit between the admission and the first approval would otherwise pass with no person seeing it |
| In one second | A person's look in the edit's second does not clear it, and does not start the anchor again | No order can be read within a second: the reading that stops work wins |
| The fact | `description_edited_at` in `facts/1`, the latest `editedAt` among the pull request's `userContentEdits`, keyed on `editedAt`, since the opening text's entry is created only with the first later edit (P-58). Absent or null, it is no edit; any other value that is not a time defers, `description_unreadable` | An unreadable fact never yields an action |
| I-28, narrowed | A stranger's act moves no item on; it may only stop one, into a Hold only a person ends. The pull request Lifecycle declares converged and queued to held by a stranger, bound person | Only the author or a writer can edit a description, so a stranger here is an outsider editing their own pull request: the worst they can do is hold it until a person looks |
| **It holds nothing yet** | The facts port does not read `userContentEdits`, so it gives no `description_edited_at`, and the rule holds nothing until it does: "The facts port reads a pull request's description edits" (issue 526). P-58 was read through the Maintainer's login; the reader App's leg is owed, and is being recorded | Stated outright, since a field that is absent turns the rule off silently |
| The cost | A description edited after the first approval, a reviewer App's summary after a push among them, needs a person's approval before the enqueue | It is what this rule is for |

## Why

Decision 0132 reads an outsider's merge as never done, after GitHub has closed the issues its description named. This stops the merge before it, wherever the description changed since the approval it would merge on.

## Boundaries

| Boundary | Check |
|---|---|
| An edit after the first approval since a person looked holds the item, needing a person; one before it or none read holds nothing, but on an outsider's pull request one after the admission holds, and its twin on the Factory's does not; a push's or a dismissal's fresh approval clears nothing; a person's approval after the edit clears it, one in its second does not; a person's look starts the anchor again; an outsider's own edit of an admitted, approved pull request holds it; a queued item leaves the queue; an unreadable time defers | `tests/test_decide.py::test_a_description_edited_after_the_approval_holds_until_a_person_approves` |
| A stranger only stops an item, into a Hold a person ends, and the Lifecycle declares it | `tests/test_transitions.py::test_a_stranger_only_stops_an_item_into_a_hold_a_person_ends` |
| The feed asks a person to approve, or to close | `tools/check_examples.py` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
