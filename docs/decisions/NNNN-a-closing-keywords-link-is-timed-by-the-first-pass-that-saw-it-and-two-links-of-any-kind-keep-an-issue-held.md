# NNNN. A closing keyword's link is timed by the first pass that saw it, and two links of any kind at an issue's merge keep it held

Status: accepted. The Factory Builder's rulings of 2026-11-10 on "Facts: a closing keyword's link timed by the first pass that saw it, and the Consumer entry at the merge (after the first cut)" (issue 552): its design, and rulings (1) to (3). It amends decision 0174's rows "The same second" and "What carries no time", for a closing keyword's link.

## Decision

| What | Decided | Because |
|---|---|---|
| The facts | Each linked pull request in `issue-facts/1` carries `keyword`, whether its references name the issue by a closing keyword now, and `keyword_seen_at`, the `now` of the first pass whose record listed it with its keyword, or null where none has. Each pass record already holds each issue's facts, so it carries the closing references that pass read. A keyword not a flag, or a time not a time or before the pull request opened, defers, `linked_unreadable` | GitHub dates a cross-reference at the first mention of the issue, not when it became a keyword (`trials/P-48.json`), so the only time a keyword link has is the Factory's own record of first seeing it, which no edit after can move back |
| Row 1 at the merge | A keyword link stood at the first merge where a pass saw it before the merge's second, as a link by hand stood where it was made before that second (decision 0174). Two links of either kind, neither closed before it, keep the issue `held`, `merged_while_held`, under the rest of decision 0174: an outsider's counts only where a person had admitted it by then, and a person's hands-off beside them excuses them | Done from `held` is a change by the platform the issue Lifecycle does not declare |
| An edit after the merge | Once a pass has seen a pull request's keyword the port keeps listing it, with `keyword` false after an edit takes the keyword out, so no edit after the merge moves the issue, and a keyword first seen after the merge reaches back to nothing | Ruling (1): an admitted outsider who could release the hold by an edit would move held to done, a stranger's change the Lifecycle does not declare |
| The same second | A keyword first seen in the merge's second, or by no pass, is no link before it, and decision 0132's Factory's or person's merge beside another in its second is still `done` | In one second no order can be told |
| Ending the hold | A person's close of the rival after the merge releases it, read only where the closer is a person (ruling (2) (a)). The close's actor is a fact that "Facts: a linked pull request's close and reopening, so that row 1 reads a rival as it stood at the merge" (issue 672) adds, grounded by trial P-61; until then the hold reads as before, and a writer's reopening, a new life, ends it | A keyword link cannot be unlinked by hand, and an edit no longer ends it |
| What waits | The issue port that reads `keyword_seen_at` from the pass records, which is not built; the issue world gives every keyword link a null time, so it reads as before. The Consumer entry stays as ruled: not read at the merge (ruling Q2 on the issue the Status names) | Ruling (3) |

## Why

Record 0174 placed a link by hand at the merge and left a closing keyword's link with no time. The Factory's pass records are a history GitHub does not keep, and they already hold each issue's linked pull requests, so the first pass that saw a keyword gives its link a time a stranger cannot reach back past.

## Boundaries

| Boundary | Check |
|---|---|
| Each linked pull request carries whether a keyword names the issue now, and when a pass first saw one, a time no earlier than it opened, or null; one that cannot be read defers | `tests/test_issue.py::test_an_unreadable_linked_pull_request_defers`, `kernel/issue.py`, mutant: "a pull request's keyword is not read", mutant: "a keyword of any kind is read", mutant: "a keyword seen at any time is read", mutant: "a keyword seen before the pull request opened is read" |
| Two keyword links a pass saw before the merge's second, or one beside a link by hand, keep the issue held; one taken out after the merge still holds; one first seen after the merge, in its second or by no pass, an outsider's admitted after it, and the merge's own seen in its second, leave it done | `tests/test_issue.py::test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it`, `kernel/issue.py`, mutant: "a keyword link is not read at the merge", mutant: "a keyword first seen in the merge's second stands before it", mutant: "a keyword no pass saw stands before the merge", mutant: "a keyword taken out after the merge releases it" |
| The issue port reads each linked pull request's keyword time from the pass records, and keeps listing one whose keyword a pass saw | waiting on `adapters/issues.py` |
