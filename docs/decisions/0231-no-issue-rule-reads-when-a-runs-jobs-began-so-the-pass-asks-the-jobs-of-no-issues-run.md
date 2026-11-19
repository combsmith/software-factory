# 0231. No issue rule reads when a Run's jobs began, so the pass asks the jobs of no issue's Run

Status: accepted. The Factory Builder's ruling of 2026-11-18 on "An issue's Runs are asked of the records port's jobs before issues are served" (issue 836), which offers this as its second way to be done: a record that no issue rule needs a Run's start before the first Intent is named for issues.

## Decision

| What | Decided | Because |
|---|---|---|
| What the issue rules read | `kernel/issue.py` reads a Run's `started_at` and nothing of when its jobs began, `began_at`: for the readiness Run behind a Factory `factory:ready`, for whether the investigation is current, for a verdict since it, for when the issue last moved, and, through `kernel/derive.py`'s `since_writer`, for the Runs the brakes count since a writer acted. `started_at` is the run list's own, given with no job asked. The brakes' count of acts reads the starts of the Runs that landed an act, an approval or a resolution, which no issue's Run is | `began_at` is read in one place in the Kernel, the rule that dates an approval of a pull request. The issue this record answers was filed on the reading that an issue rule needed it; none does |
| What the pass asks | The jobs of no issue's Run. The entry hands the records port the open pull requests alone, with issues served or not | Each Run asked counts against the fifty one read may ask, and one past that leaves the whole list not whole, which defers every pull request too. Asking for a field nothing reads would spend that bound, and lengthen a cold start, for no rule |
| When that changes | The first issue rule that reads `began_at` adds the served open issues to the items the entry hands the records port, in the same pull request, within the bound of fifty that decision 0196 keeps | Until then the Kernel would read a field that is absent on every issue's Run, and a rule that reads what is not asked decides on nothing |
| The row this answers | Decision 0196's last boundary row said the open issues join the items handed once the pass decides issues. The pass decides them now and they do not join: this record holds instead, and that row's check is the test below | 0196 foresaw the join before the issue rules were written. What they read settles it |

## Why

The run list is the Factory's history, and decision 0196 bounded the asking to what a pass has a use for. A pass has no use for an issue Run's beginning. Leaving issues out costs nothing today and keeps the bound for the pull requests, whose approvals are dated by it.

## Boundaries

| Boundary | Check |
|---|---|
| An issue's State and its Decision are the same whatever `began_at` its Runs carry: none, null, one before the Run's start or one long after it; and they do change with the Run's `started_at`. So at the attempts brake and one Run short of it | `tests/test_issue.py::test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry`, `kernel/issue.py`, `kernel/derive.py`, mutant: "the Runs since a writer acted are counted by when their jobs began", mutant: "the readiness Run behind a label is dated by when its jobs began", mutant: "the latest readiness Run is told by when its jobs began", mutant: "an investigation is current from when its Run's jobs began", mutant: "a verdict is since the investigation by when its Run's jobs began", mutant: "an issue last moved when a Run's jobs began" |
| With issues served, the entry hands the records port the open pull requests alone | `tests/test_controller.py::test_no_served_issues_runs_are_asked_when_they_began`, `controller/__main__.py`, mutant: "the entry asks the served issues' Runs when they began" |
