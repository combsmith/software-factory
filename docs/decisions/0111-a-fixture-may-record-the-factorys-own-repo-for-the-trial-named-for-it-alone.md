# 0111. A fixture may record the Factory's own repo, for the trial named for it alone

Status: accepted. Preparing "Trial P-30: one identity cuts a Release and moves a channel tag under the tag ruleset" (issue 189), on the orchestrator's ruling of 2026-10-31.

## Decision

| What | Decided | Because |
|---|---|---|
| Where P-30 records it ran | `combsmith/software-factory`, a third value of a fixture's `repo` | It cuts a Release under the tag ruleset of the repo that holds the Releases. The canary has neither, and a label that said otherwise would misstate what ran |
| Which trials may | Those `TRIALS_OF_THE_FACTORY` names in `tools/check_trials.py`, P-30 alone. Any other trial that records this repo is refused, and so is P-30 recorded anywhere else | The schema cannot tie a value to a trial; this check can. A trial still runs in the canary unless a change names it here |
| What holds it | Every rule of a fixture of the canary, with this repo in the canary's place: the owners and repos it reads and is answered with, an App's reach, and a GraphQL write held to a node of this repo by its id, `FACTORY_ID` | A wider place to run earns no wider reads |
| What stays | P-8, P-37 and P-43 keep the canary's label, though they read this repo. Nothing here relabels them | This names P-30 alone, and a relabelling is a change of its own |

## Why

Section 6 and the skill both said P-30 needs the Factory's own repo, and the fixture's schema had no value for it. It was
decided before the run, so that the fixture is held to a rule and not excused from one.

## Boundaries

| Boundary | Check |
|---|---|
| Another trial that records this repo is refused | `examples/invalid/trial.another-trial-in-the-factorys-repo.json` |
| P-30 recorded on the canary is refused | `examples/invalid/trial.a-trial-of-the-factory-on-the-canary.json` |
| P-30 reading another owner's repo is refused | `examples/invalid/trial.a-trial-of-the-factory-reading-another-owners-repo.json` |
| A write in such a fixture is held to a node of this repo | `tests/test_tools.py::test_a_write_in_a_fixture_of_the_factory_is_held_to_a_node_of_the_factory` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
