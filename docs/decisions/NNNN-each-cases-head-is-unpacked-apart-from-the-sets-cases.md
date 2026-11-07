# NNNN. Each case's head is unpacked apart from the set's cases

Status: accepted. The Factory Builder's story of 2026-11-07, issue 623, "Each case's head is unpacked outside the folder that holds the set's case files". It is a sub-issue of issue 562, due before the first gate-v1 run.

## Decision

| What | Decided | Because |
|---|---|---|
| Where a head is | The eval job unpacks each case's head in `heads` under the runner's own temporary directory, `heads_place` in `harness/eval/__init__.py`, beside the scratch `heldout` that holds the set's cases, never inside it. Both the fetch, which unpacks, and the run step, which starts the CLI in a head, read it there. The canary keeps its head in a temporary directory apart from its case | The set's cases, answers and all, sat two folders above the folder the CLI starts in. Only the read tools' confinement (decision 0138, P-59) kept the model from them. A head apart from them puts no case file in the head's folder or in any folder above it short of the runner's temporary directory |
| What is refused | A heads folder that is the scratch or the workspace, is inside either, or holds either, the root among them, read by real path through any link and part by part, stops the step `scratch_in_workspace`, as a scratch inside the workspace does | A link must not put the heads back beside the cases |
| What it does not do | It does not hide the cases from a model whose confinement has failed outright: the runner's temporary directory holds both. It takes away the fixed relative path from a head to the cases, and the case files beside a head | The confinement is still the guard. This makes it not the only one, as the issue asks. Keeping the cases off the runner while the model is asked is a larger change than the issue's |

## Why

The issue names the gap: the answers lay a fixed two folders above every head the model read, so a confinement that slipped, at a CLI version bump for instance, would reach them at once. Unpacking heads apart from the scratch closes that path, and the check on the heads folder's real path keeps a link from opening it again.

## Boundaries

| Boundary | Check |
|---|---|
| The head the CLI starts in shares no folder with the scratch below the runner's temporary directory, and nothing but heads is beside it; the fetch and the run step both use `heads_place`; a heads folder that is the scratch or the workspace, inside either, or holding either, the root among them, through a link, is refused | `tests/test_evals.py::test_each_head_is_unpacked_apart_from_the_cases`, `harness/eval/__init__.py`, `harness/eval/run.py`, mutant: "the heads are unpacked beside the cases", mutant: "a heads folder inside the scratch is taken", mutant: "a heads folder inside the workspace is taken", mutant: "a heads folder that holds the scratch is taken", mutant: "a heads folder that is the scratch is taken", mutant: "the root is read as holding nothing", mutant: "the fetch unpacks each head in the scratch", mutant: "the run step looks for each head in the scratch" |
