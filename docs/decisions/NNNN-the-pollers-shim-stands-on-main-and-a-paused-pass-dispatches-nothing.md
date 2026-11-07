# NNNN. The poller's shim stands on main, and a paused pass dispatches nothing

Status: accepted. The Factory Builder's rulings of 2026-11-07 on the plan for the shims of "Workflows: the frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape" (issue 196). This is its PR B, the poller's shim, after `docs/decisions/0157-an-acts-shim-is-the-runs-but-for-its-name-and-the-file-it-calls.md` put on `main` the three shims that dispatch a Run. It lands under the repo's own Pause, `FACTORY_PAUSED` set to `true` by the Maintainer, without waiting for the ruleset switch of "The ruleset switch: main requires the machine user's approval of the most recent commit, and slice 1's event is recorded" (issue 198). A live pass that admits nothing is worth seeing before slice 1's event, and a public repo's minutes are free.

## Decision

| What | Decided | Because |
|---|---|---|
| The shim | poller.yml stands on `main`, held word for word by `POLLER_SHIM` in `tools/check_workflows.py` and by its hash in `SHIMS`. It is ruling 4's text with record 0115's amendments: three schedule lines an hour, at minutes 13, 33 and 53; a dispatch with no input; the completion of `factory` and `ci`, never `sf-run`, since a Run's own `wake` job dispatches the poller; one job, `pass`, granted `actions: write` and `contents: read`, in the group `sf-poller` that cancels nothing, calling `.github/workflows/pass.yml` at `factory/v0-next` with `secrets: inherit` | A template states the rule and a mutant can break it. A hash freezes only what the Maintainer approved |
| It is live | From its merge, a pass runs at each tick, at each end of `factory` or `ci`, and at each Run's `wake`. This is the switch that makes the Factory run on its own repo | The other shims run only on a dispatch, and only a pass dispatches |
| A paused pass | Under the Pause, a pass reads the facts and the run records, and the Kernel decides every item `paused`. The pass uploads its record, `pass/1`, before any write. The effects port reads the Pause again and sends no dispatch, its successor's neither. It still writes each item's status and the tracking issue, which are no act, so that a person sees why nothing moves, and it uploads `written/1` | Decision 0003: a Pause starts nothing, even when Factory code is broken. The shims' own `if:` refuses a Run under the Pause too |
| Decision 0003's row on a Pause and a ceiling outside the Kernel | Split, as that story's ruling 13 gives it. The Pause for Runs is held now by the shims' `if:`. The Run ceiling outside `kernel/`, and the Pause for the Controller's own acts, wait on the Controller's brakes, which `controller/AGENTS.md` now names among its parts not built yet | The row waited on poller.yml, which now stands. Nothing outside the Kernel counts Runs yet, and the Controller's acts in a pass are stopped by the Kernel's Pause alone |
| CodeQL | The shim calls the Release at its Channel tag, as every shim does (decision 0006), so CodeQL raises `actions/unpinned-tag` on it. The `main` ruleset's code-scanning rule then blocks the merge until the Maintainer dismisses the alert | The tag rulesets guard the tag (decisions 0115 and 0124). Pinning a commit hash would undo the Channel |

## Why

The poller is the one shim that runs without a dispatch, so it is the switch. It lands alone, after the shims it would dispatch, and under a Pause. Its first passes show the Factory reading its own repo and dispatching nothing, before the Pause is cleared.

## Boundaries

| Boundary | Check |
|---|---|
| poller.yml stands on `main` as `POLLER_SHIM` and its hash: its ticks, its dispatch with no input, the ends it wakes on, its pass, its group and its grant | `tests/test_tools.py::test_the_pollers_shim_stands_as_its_template_and_its_hash`, `tools/check_workflows.py`, `.github/workflows/poller.yml`; mutant: "poller.yml is not held to its shim"; mutant: "the poller's template drops a tick"; mutant: "the poller's template wakes on a Run's end"; mutant: "the live poller wakes on no tick"; mutant: "the live poller takes an input" |
| The poller calls the pass, and nothing else | `tests/test_tools.py::test_the_pollers_shim_stands_as_its_template_and_its_hash`, `.github/workflows/poller.yml`; mutant: "the live poller calls another file than the pass" |
