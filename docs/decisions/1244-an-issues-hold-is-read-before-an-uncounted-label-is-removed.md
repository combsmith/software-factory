# 1244. An issue's Hold is read before an uncounted label is removed

Status: accepted. 2026-11-26, the Solution Architect; issue 1216. Extends decisions 1207 and 1224, and the brakes' Holds of decision 0003.

## Decision

Where an uncounted label would be removed, the issue Kernel first reads what it would decide without that act. If that is a Hold, the issue stays held and the label waits for the release (`kernel/issue.py`, `_decide`, `_after_labels`). This covers every Hold that comes from the Run the issue wants: `branch_not_pushed`, `run_needs_person`, and the brakes on a Run, such as `attempts_exhausted` and the Run ceiling.

The act ceiling is not such a Hold. It never stops an act that stops work, so the label is still removed at that ceiling.

The issue world plants a branch the Factory never pushed, and it tells `branch_pushed` from the opening Runs whose records it lists (`sim/issues.py`).

Limits: a person's own Hold already waits the removal out, as before. The removal is not made under a Hold, so the label stays shown until a person releases the issue. An issue held at the act ceiling still shows its derived State for the pass that removes such a label.

## Why

The simulator found it on seed 290. The issue was held on a planted branch, another App added `factory:triage`, and the Kernel reported `ready` for one pass to remove it. Only a person may move an issue out of `held`. Declaring that transition was rejected for that reason. Keeping the fault off the coincidence was rejected because it hides a gap already on main. Making the removal under a held Decision was rejected: no issue Decision acts while held today.

## Boundaries

| Boundary | Check |
|---|---|
| Each Hold the Run wanted places stands over an uncounted label; without the Hold the label is removed | `tests/test_issue.py::test_an_issues_hold_is_read_before_an_uncounted_label_is_removed`, `kernel/issue.py`, mutant: "an uncounted label is removed before an issue's Hold" |
| The act ceiling still lets an uncounted label go | Reversed by decision 1255: `tests/test_issue.py::test_an_uncounted_label_waits_at_the_act_ceiling`, `kernel/issue.py`, mutant: "an uncounted label is removed at the act ceiling" |
| The issue world plants a branch, holds on it, and never opens from it | `tests/test_issue_simulator.py::test_the_seeds_plant_a_branch_the_factory_never_pushed`, `sim/issues.py`, mutant: "a planted branch is told as pushed" |
| At the act ceiling the label waits too (decision 1255) | `tests/test_issue.py::test_an_uncounted_label_waits_at_the_act_ceiling`, `kernel/issue.py`, mutant: "an uncounted label is removed at the act ceiling" |
