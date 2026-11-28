# 1391. A called workflow passes where each caller is gated or released

Status: accepted. 2026-11-28, the Solution Architect's ruling (P) and option A on the poller; issue 838. Narrows decision 1390's row "Every job of a workflow `workflow_call` may start" and its Limits, and decision 1378's row "Every other event refuses it".

## Decision

Decision 1390 still refuses a command in a workflow that `workflow_call` starts, and the poller's `workflow_run`. So every push here was refused. Two more workflows now pass whole, on the base's list.

- A workflow whose one trigger is `workflow_call` passes where every job in the folder that names it is a caller of one of two forms: it calls the file by its `./` path from a workflow itself gated, or it calls the home repo's file at a Release or Channel tag, word for word. At least one caller must exist.
- Any other job that names the file refuses it: a branch, a commit, another repo or a tag of another shape. So does a chain of callers past `DEPTH`, three callers up, or one that comes back.
- The poller's frozen shim passes word for word but for its comments. A test pins it to `POLLER_SHIM`.

`guards/workflows.py` holds both.

Limits: callers are read in the files given, so reading the base's and the branch head's is the caller's. A repo outside the folder that calls a workflow here, at any ref, runs it with its own secrets; for a Consumer that is a term of the grant. Whoever can move a Release tag changes what the shim and each home call run. A caller of another form also refuses on its own read, so refusing the file it names is defence in depth.

## Why

A tag call runs the Release's file, never this commit's, so no work branch reaches it. The poller wakes on `workflow_run` a median 0.4 minutes after CI, against 153 minutes on its schedule alone. Its shim checks out nothing and reads nothing of what woke it, so a work branch gains only the timing. Dropping `workflow_run` was rejected on that data.

## Boundaries

| Boundary | Check |
|---|---|
| A called workflow passes where every job naming it is a home-tag call or a gated `./` call, at least one | `tests/test_guards.py::Gated.test_a_called_workflow_passes_where_every_job_naming_it_is_gated_or_at_the_home_tag`, `guards/workflows.py`, mutant: "a called workflow with no caller passes" |
| A job naming it in any other form, a chain past the depth, or a trigger beside the call refuses it | `tests/test_guards.py::Gated.test_a_called_workflow_passes_where_every_job_naming_it_is_gated_or_at_the_home_tag`, `guards/workflows.py`, mutant: "a caller in another form passes" |
| The poller's shim passes on the list, word for word but for its comments | `tests/test_guards.py::Gated.test_the_pollers_shim_passes_word_for_word_on_the_list`, `guards/workflows.py`, mutant: "the poller's shim is read as any workflow" |
