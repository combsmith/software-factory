# 0001. One repo, and a Kernel that does no I/O

Status: accepted. Source: decision 1 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

The Factory lives in this repo alone: Lifecycle, Role manifests, schemas, configuration, Kernel,
adapters, Harness, Controller, release tooling and their tests. The Kernel is Python 3 with the
standard library only. All I/O is in adapters. Shell is step glue.

## Why

A decision that does no I/O can be run thousands of times against a fake world before it is
trusted with a real one. A repo that reads nothing from another can be verified from one commit.

## Boundaries

| Boundary | Check |
|---|---|
| No module under `kernel/` opens a file, a process, a socket or the environment, or reads a clock | `tools/check_purity.py` |
| Nothing here is installed: no dependency manifest, and every import is the standard library or this repo | `tools/check_repo.py` |
| No code or data file names the proof-of-concept repo; nothing is fetched from it | `tools/check_repo.py` |
| A `run:` block in a workflow is at most ten lines and holds no decision | `tools/check_workflows.py` |
| The repo's settings are what the design rests on: the check is required, secrets are scoped to an environment, the default token only reads | waiting on `adapters/` |
