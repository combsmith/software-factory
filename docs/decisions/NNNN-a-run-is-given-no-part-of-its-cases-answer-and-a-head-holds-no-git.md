# NNNN. A Run is given no part of its case's answer, and a head holds no `.git`

Status: accepted. The Factory Builder's story of 2026-11-07, issue 614, "A test that a Run is given no part of a case's `expected`, and that its head holds no `.git`". It tests what keeps a held-out case's answer from the model, which nothing tested.

## Decision

| What | Decided | Because |
|---|---|---|
| The answer | A case's `expected` reaches neither the Task `harness/eval/run.py` builds, nor the prompt the CLI is given, nor any file in the head the CLI is started in, which is all the read tools can reach (decision 0138). A test runs a case whose answer holds a marker through the job, as the workflow runs it, and looks for the marker, and for the answer whole, in each. Cases that differ in their answer alone, in each of its fields, a Finding against a clean change among them, give the model the same Task, prompt and head, the Run's fresh id and session held still | The Task is built from the case's facts, diff and head alone. A change that passed the case whole, or put its answer in a text, would hand the model the answer, and nothing would say so |
| The head | `harness/head.py` refuses an archive with a member named `.git`, at the top or below, in any case of its letters. The eval's head of such an archive is `head_unreadable`, and the case asks nothing | Git never archives its own folder, so no head the commit gives holds one. The eval's head is not held to the commit's tree as a live Run's is (decision 0142), so without the refusal a head holding a history would reach the model, and a test that the head holds no `.git` would test nothing. A case-blind file system reads `.GIT` as `.git` |

## Why

The issue names the gap: what keeps the answer from the model was true by construction and held by no test. The test reads what the model is given at the call itself, so a change anywhere between the case and the CLI is caught. The refusal closes the one path by which a head could carry what its commit does not.

## Boundaries

| Boundary | Check |
|---|---|
| No marker of a case's answer, and not the answer whole, is in the Task, the prompt or a file of the head at the call; cases that differ in their answer alone are given the same; the head holds no `.git`; a head whose archive holds one is `head_unreadable` and asks nothing | `tests/test_evals.py::test_a_run_is_given_no_part_of_its_cases_answer_and_its_head_no_history`, `harness/eval/run.py`, mutant: "the Task carries the case's answer", mutant: "the prompt carries the case's answer", mutant: "a part of the case's answer reaches the prompt" |
| The unpacker refuses a member named `.git`, a folder or a file, at the top or below, in any case | `tests/test_harness.py::test_each_archive_the_unpacker_refuses_it_refuses_whole`, `tests/test_evals.py::test_a_run_is_given_no_part_of_its_cases_answer_and_its_head_no_history`, `harness/head.py`, mutant: "the head may hold git's folder", mutant: "git's folder is refused only as git names it", mutant: "git's folder is refused only with something under it" |
