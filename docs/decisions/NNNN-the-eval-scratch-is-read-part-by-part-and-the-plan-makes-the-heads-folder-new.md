# NNNN. The eval scratch is read part by part, and the plan makes the heads folder new

Status: accepted. The Factory Builder's story of 2026-11-08, issue 626, "The eval scratch is held part by part, the heads folder is made fresh, and the canary's head is held apart". It follows the reads of issue 623, "Each case's head is unpacked outside the folder that holds the set's case files" (decision 0163).

## Decision

| What | Decided | Because |
|---|---|---|
| How the scratch is held apart from the workspace | `scratch` in `harness/eval/__init__.py` refuses a scratch that is the workspace, is inside it, or holds it by `os.path.commonpath` over their real paths, as `heads_place` does, no longer by a prefix with a separator | The root's own path ends in its separator, so a `heldout` linked to the root was taken by the prefix test, though the root holds the workspace |
| Where the heads folder is made | The plan makes `heads` beside the scratch, new and mode 0o700, as it makes the scratch. One an earlier job left stops the plan `scratch_unreadable`, as a scratch it left does, and the heads are placed and made before the scratch, so that one that stops it leaves no scratch | A heads folder left on a reused runner would have been taken, with its own modes and contents. Hosted runners are discarded after each job, so this guards a runner that is not |
| The canary | A test holds the canary's head and its case in folders that share none below the system's temporary directory | The canary keeps them apart already (decision 0163); nothing held it |

## Why

The reads of decision 0163's change found that `heads_place` read containment part by part while `scratch`, beside it, still read it by a prefix, and that the plan made the scratch new but left the heads folder to the fetch, which took one already there. Each is held now as the other was, and the canary's layout, which nothing tested, is tested.

## Boundaries

| Boundary | Check |
|---|---|
| A scratch that is the workspace, inside it or holding it, the root among them through a link, is refused | `tests/test_evals.py::test_a_set_of_no_case_ends_the_run_before_anything_is_read`, `harness/eval/__init__.py`, mutant: "the scratch is held to the workspace by its separator", mutant: "the scratch may be in the workspace", mutant: "a workspace inside the scratch is allowed", mutant: "a workspace that is the scratch is allowed" |
| The plan makes the heads folder, mode 0o700, and one an earlier job left stops it, with no scratch made | `tests/test_evals.py::test_each_head_is_unpacked_apart_from_the_cases`, `harness/eval/__init__.py`, mutant: "the plan makes no heads folder", mutant: "a heads folder an earlier job left is taken", mutant: "the heads folder is made open to all", mutant: "the scratch is made before the heads" |
| The canary's head shares no folder with its case below the system's temporary directory | `tests/test_evals.py::test_the_canarys_head_is_apart_from_its_case`, `harness/eval/canary.py`, mutant: "the canary unpacks its head beside its case" |
