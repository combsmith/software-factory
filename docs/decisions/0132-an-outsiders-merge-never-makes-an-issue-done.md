# 0132. An outsider's merge never makes an issue done

Status: accepted. The Factory Builder's ruling of 2026-11-03 on "An approved outsider's description edit before the queue merges adds closing keywords, and GitHub closes those issues with the pull request as the closer" (issue 280), the last item of "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182), after trial P-48 failed. It narrows row 1 of the issue's States (decision 0028), where a merge is read as it stood at the merge.

## Decision

| What | Decided | Because |
|---|---|---|
| The rule | A merge counts toward `done` only where the Factory's own or a person's merge, in the first merge's second, closed the issue. Where only an admitted outsider's did, the issue reads `declined`, `closed_by_outsider_merge`, naming the outsider's merges, and needs a person, who decides whether the work is done | Only a pull request's author and those with write access can edit its description, and a person's approval covers its diff, not its description. P-48: an outsider's pull request, approved at its head, gained a closing keyword for a second canary issue after the approval, the approval still standing, and the queue's merge closed that issue with the pull request named the closer |
| What stays | The contradictions are read first, an outsider's merge among the rest: a person's close before it, an outsider's reopening or a Hold still read `merged_while_declined` or `merged_while_held`, and so does an outsider's merge that closed nothing while the issue stood closed. The Factory's and a person's merges read as before, beside an outsider's in the same second too, and are `done`'s evidence alone. An outsider's merge no person admitted still moves nothing, and its close reads as any other close, `closed`. An outsider's merge still counts toward the quiet wait for GitHub's close, `merge_closing` | Only what was `done` before changes |
| The Lifecycle | The issue Lifecycle declares `in_review` and `new` to `declined` by the platform: the queue's merge of an admitted outsider's ready pull request, whose late keyword may name an issue the Controller does not watch. From `held` and `not_served`, which only a person ends, the reading is "A platform close keeps the State a person set on an issue held or not served" (issue 522), where the Builder's lean is to keep the State the person set | The exploration makes both, from an issue in review and from an outsider's issue not yet accepted |
| Not by time | No rule reads when a closing reference was made against when the approval was given. P-48's timeline dates the second issue's cross-reference after the approval, but a bare mention made before the approval and turned into a keyword after it would date before it, and once the issue is closed every cross-reference reads `willCloseTarget` false, so the merged timeline cannot say which reference closed it | The rule rests on no timeline, so the mention-then-keyword case needs no trial |
| The cost | A legitimate outsider's fix is never `done`: the issue reads `declined` and asks a person, who is offered a reopening alone, since GitHub closed it already. A person who finds the fix good reopens it and closes it again, a person's close, which asks no one | The right default in slice 1, where the Factory serves only this repo |
| What is owed | Blocking an enqueue when the description was edited after the approval, as defence in depth, waits on a trial of `lastEditedAt`: "A description edited after the approval holds the enqueue and asks a person again" (issue 519) | It would stop the close, not only read it |

## Why

Row 1 made a merge count where the issue's timeline names it the closer. P-48 showed that an outsider can make GitHub name its pull request the closer of any issue, by an edit no one reviews. The class of the pull request's author is read already, and no timeline can be gamed into it.

## Boundaries

| Boundary | Check |
|---|---|
| An admitted outsider's merge that closed the issue reads `declined`, `closed_by_outsider_merge`, needing a person; the Factory's or a person's that closed it beside it is done; a person's close or Hold before it is read first; one before the life, empty or that closed nothing reads as before | `tests/test_issue.py::test_an_outsiders_merge_never_makes_an_issue_done` |
| Only a linked merge is done, an admitted outsider's no longer among them | `tests/test_issue.py::test_only_a_linked_merge_is_done` |
| The queue's merge of an admitted outsider's pull request is a change the issue Lifecycle declares | `tests/test_transitions.py::test_an_issue_explored_is_held_to_the_issue_lifecycle` |
| The feed asks a person whether to reopen | `tools/check_examples.py` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
