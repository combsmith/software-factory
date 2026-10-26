# 0067. A Release is cut from main through the eval gate and never moved, and next is rolled back with no gate

Status: accepted. The working rulings of "Release: cut an immutable tag, move next, and roll back in one action"
(issue 197), with the Maintainer's answer of 2026-10-21 replacing rulings 4, 5, 9 and 10 by 4′, 4″, 5′, 9′ and 10′. It
holds rulings 2 to 8 and 11. It extends decision 0006, on one Release and one path, and decision 0010, on one line
serving each repo and family, and leaves both as they are.

## Decision

| What | Decided | Because |
|---|---|---|
| A Release and a Channel | A Release is a lightweight tag `factory/vMAJOR.MINOR.PATCH` on a commit of `main`; a Channel is `factory/vMAJOR-next` or `factory/vMAJOR-stable`. `next` serves this repo's `review-change`; `stable` serves nothing until slice 3 builds promotion. Both, and what each serves, are `release/rings.json` | Section 9.4 wants both Channels and the ring file from the first commit; FR-50 forbids `stable` before evidence |
| Immutable | A Release tag is held by a ruleset with no bypass, so once made nobody moves it, the release App and the Maintainer included; no step plans a write to one. A wrong cut is skipped, never reused | Section 2.4 rule 2 |
| Who moves `next` | One workflow, the release workflow, in its own environment, by one App, `combsmith-sf-release`, on the Maintainer's dispatch or an armed schedule; never a session. Its needs wait on that App's registration in `config/apps.json` | One identity through one path; the session mints nothing |
| The cut's rules | Pure, in `release/cut.py`: a Channel the ring file declares, never `stable`; a version newer than every Release, of the Channel's major; a commit of `main`, verified, carrying no Release; every commit a full sha. Each refusal is one code | The rules are tested and mutated as the Kernel's are |
| The eval gate | `next` moves only to a commit whose eval report passed every case of a non-empty set, judged for that Release. It is read before the tag is created, not after as ruling 4′ words it, so a closed gate burns no version. The review Intent's set is empty today, so the gate is closed | Section 9.1 item 5: a gate-deciding Intent does not serve without its eval set |
| Rollback | One step, with no gate, back to an existing Release below the one `next` is on, by default the greatest; never forward, and never from a Channel at no Release. It reads the refs alone, nothing at any tag. When the workflow cannot run, the Maintainer's admin login is the fallback | FR-49; recovery never depends on the Factory running (section 9.1) |
| A commit's Release | `release/current.py`: the one Release tag naming the commit. A Channel never counts, and two Releases on one commit are none; so a Channel moves only to a commit one Release names alone | L-45: what ran is one answer |
| A Run on another Release | The run job's reader names the Run's own Release, the one Release tag on the commit its own job checked out, `steps.commit()`, among the factory/ tags read with its own token; it is given no commit by the workflow, so no expression carries one. A Run whose own Release is not its pass record's builds no Task and ends superseded, `release_moved`, under its own Release; one whose own Release cannot be named builds none and stops `release_unresolved`, or `release_unreadable` before any key when its checkout cannot be read, never taking the pass record's. The run job uploads that outcome, `reader-outcome`, when it fails; `apply` downloads it, and its last step keeps it, held to `outcome/1`, this Run's and this Release's, over `run_failed`; a missing or other one changes nothing. `apply`'s own `environment`, `release_differs` stays: it is the `apply` job's Release disagreeing with the pass after the reader's agreed, the jobs' fault | L-46: a caller ran ahead of what it called. A Release moving under a Run is no fault, and is not counted as one |
| A called workflow's commit | Its first job checks out `factory/v0-next` once and hands its commit to every later job; that commit's Release is resolved by `release/current.py`, whose rules `steps.release` in `harness/steps.py` now applies to the checkout's own tags, so one implementation names a Release. A Channel moved away and back between the shim's call and that checkout is the one case missed, and is accepted | Section 2.2 and decision 0006: Factory files are read at the commit of the running workflow |

## Why

The Maintainer asked that a Release move through a workflow environment, automated, with approval gated by evals,
after the reference of combsmith/.github's own release workflow. This pull request holds the rules, the ring file, the
tags port and the skill; the workflow, the App's entry and the first cut's fixture follow it, the last once the App is
registered and the eval set holds cases.

## Boundaries

| Boundary | Check |
|---|---|
| A Release is cut only from a verified commit of `main`, newer than every Release, of the Channel's major | `tests/test_release.py::test_each_rule_of_a_cut_refuses_with_its_own_code` |
| `next` moves only through the eval gate, judged for that Release and read before anything is written | `tests/test_release.py::test_a_closed_eval_gate_refuses_every_cut_and_move_and_burns_no_version` |
| No step writes a Release tag, or moves `stable` | `tests/test_release.py::test_no_step_writes_a_release_tag_and_none_names_anything_but_a_channel`, `tests/test_release.py::test_stable_is_never_moved_until_promotion_is_built` |
| A step moves only a declared Channel, to a commit one Release names alone | `tests/test_release.py::test_only_a_channel_the_ring_file_declares_is_moved`, `tests/test_release.py::test_a_channel_moves_only_to_a_commit_one_release_names_alone` |
| A rollback passes no gate and moves only back | `tests/test_release.py::test_a_rollback_passes_no_gate_and_never_moves_forward` |
| A commit's Release is its one Release tag | `tests/test_release.py::test_a_commit_with_no_release_or_two_resolves_to_none` |
| The release App's needs wait on its registration | `tests/test_release.py::test_the_release_apps_needs_wait_on_its_registration` |
| Only the release workflow moves `next`, held to its shape | waiting on `.github/workflows/release.yml` |
| A Release tag is immutable to everyone | waiting on `.github/workflows/release.yml`, whose first cut's fixture reads the ruleset again |
| A Run on another Release than its pass's builds no Task and ends `superseded`, `release_moved`; one whose own Release cannot be named builds none either, never taking the pass's | `tests/test_steps.py::test_a_run_on_another_release_than_its_pass_builds_no_task`, `tests/test_steps.py::test_a_run_whose_own_release_cannot_be_named_builds_no_task` |
| Every step names its Release by `release/current.py`'s rules alone, over its checkout's own tags | `tests/test_steps.py::test_the_release_is_its_one_tag` |
| The reader takes its commit from its own checkout, before any key | `tests/test_steps.py::test_a_run_whose_own_release_cannot_be_named_builds_no_task` |
| The reader's outcome, from its step alone, reaches the last step, held to `outcome/1` | `tools/check_workflows.py`, `tests/test_steps.py::test_a_run_on_another_release_than_its_pass_builds_no_task` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
