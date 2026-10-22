# 0006. One Release, one path

Status: accepted. Source: decision 6 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

The Factory is released as one line. A Release is an immutable tag, `factory/vX.Y.Z`. A Channel is
a moving tag, `factory/v<MAJOR>-next` or `factory/v<MAJOR>-stable`, moved through one path by one
identity. Workflows, Kernel, Harness, prompts, manifests, Lifecycle and configuration all ride the
same Release. This repo is served by `next`; Consumer repos by `stable`. A Consumer repo carries
no Factory file.

## Why

The proof of concept shipped each agent on its own line, and a Run could execute a workflow from
one version with prompts from another. One Release makes "what ran" one answer, and moving a
Channel back is the whole of a rollback.

## Boundaries

| Boundary | Check |
|---|---|
| Every action is pinned to a full commit hash, and one of the org's own reusable workflows to its channel tag | `tools/check_workflows.py` |
| Every Run records the Release it ran | `tests/test_harness.py::test_a_result_the_engine_wrote_is_filled_and_kept`, `tests/test_harness.py::test_the_job_writes_the_result_and_its_digest_and_nothing_else` |
| Inside a Release, Factory files are read at the commit of the running workflow, never at a branch | waiting on `release/` |
| The only files that run from the default branch are thin callers: each job `uses:` a pinned reusable and declares no steps | waiting on `release/` |
| A candidate reaches `stable` only with an eval result for each Intent whose inputs changed, and verified Effects from the `next` ring | waiting on `release/` |
| Rollback executes no file from the Release being rolled back | waiting on `release/` |
