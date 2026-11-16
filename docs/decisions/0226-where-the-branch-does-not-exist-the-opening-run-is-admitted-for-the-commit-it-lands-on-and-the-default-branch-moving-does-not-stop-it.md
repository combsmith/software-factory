# 0226. Where the branch does not exist, the opening Run is admitted for the commit it lands on, and the default branch moving does not stop it

Status: accepted. Decided for "The opening Run lands its one commit and opens the draft: the push write, apply's dispatch and `#342`'s writer (slice 2, S6)" (issue 838), by the Factory Builder's rulings of 2026-11-14 and 2026-11-16. It adds to `docs/decisions/0031-what-is-admitted-on-an-issue-and-when-apply-refuses.md`, which admits the opening Run for the branch head it will push to: where there is no branch yet, that head is null, and nothing said which commit the Run's one commit stands on.

## Decision

| What | Decided | Because |
|---|---|---|
| The fact | `issue-facts/1` may carry `base_head`: the default branch's head as the pass read it, a name. It is never null: the default branch always has a head, so a pass that has none to give leaves the field out | The Run's patch is made against the commit its read tools were held to, and `apply` lands it on that commit. One reader must name it, once, before the Run starts |
| The rule | In `ready`, with `branch_head` null, the opening Run is admitted only where `base_head` reads, and its admission carries it. Left out, null, empty or no text, the issue defers, `base_unreadable` | An unreadable fact yields a deferral, never an action. A commit guessed at would be another commit than the one the Run read |
| Where the branch stands | With `branch_head` a commit, no base is asked for, read or not, and none is carried | An earlier Run's commit stands on the branch: this Run pushes none and opens the draft from what is there (decision 0031) |
| At `apply` | `still_admitted` leaves `base_head` out of what it compares. The default branch moving while the Run was in flight stops nothing; the branch made meanwhile, new content, a label removed and a Hold stop it as before; a default branch that cannot be read when asked again is no admission | Nothing holds the default branch still while a Run is in flight, and it moves many times a day: holding the Run to it would discard nearly every Run. The commit lands on the commit the Run read, and the draft's own merge state says what the move means for it |
| Not required | The schema does not require the field, and refuses a null one (`examples/invalid/issue-facts.a-base-head-that-is-null.json`, `examples/invalid/issue-decision.a-base-head-that-is-null.json`). A pass that does not carry it reads as unread, and only the opening Run of a branch that does not exist waits on it | The issues port's read of it is not built. Until it is, nothing that works today changes, and that one Run defers |
| What is left | The issues port's read of the default branch's head; the reader's unpack of the admission; the push port taking it as the parent of the one commit; and `apply`'s one read that the commit is still on the default branch, an ancestor of its head or equal, refusing otherwise | Each waits on a part of that issue not yet built |

## Why

The opening Run of an issue with no branch has no admitted head. Its patch is made against some commit of the default branch, and the push must parent the one commit on exactly that commit, or the bytes that land are not the bytes the Run wrote against. The Kernel's admission is the one place both the Run and `apply` read, so the commit is named there.

## Boundaries

| Boundary | Check |
|---|---|
| With no branch, the opening Run is admitted for `base_head` and carries it; a base that is empty, null, no text or left out defers, `base_unreadable`; an unreadable branch head is said first; with a branch that stands no base is asked for or carried; no other State's Run waits on it | `tests/test_issue.py::test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on`, `kernel/issue.py`; mutant: "an unreadable base is admitted"; mutant: "an empty base is read"; mutant: "a base that is no text is read"; mutant: "the opening Run is admitted for no base"; mutant: "a base is asked for where the branch stands" |
| The default branch moving does not stop the opening Run; an unreadable base at the second asking, the branch made, new content and a Hold do; only the base is left out of the comparison; an admission that is no mapping is none | `tests/test_issue.py::test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does`, `kernel/issue.py`; mutant: "the default branch moving stops the opening Run"; mutant: "the branch head is left out with the base"; mutant: "an admission that was no mapping is asked of its parts"; mutant: "an admission that is no mapping now is asked of its parts" |
