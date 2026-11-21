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
| A module under `kernel/` is UTF-8 and declares no other encoding, so that the text the check and every reader parse is what Python runs; one that declares another, or whose bytes are not UTF-8, is refused (issue 992) | `tools/check_purity.py`, `tests/test_tools.py::test_the_kernel_is_read_as_python_runs_it_utf_8_alone`, mutant: "a declared encoding is read as UTF-8", mutant: "bytes that are not UTF-8 are replaced" |
| What Python imports as `kernel` is what the check read: `kernel/` and each folder of it has its `kernel/__init__.py` or the folder's own, holds source and an `AGENTS.md` alone, and is no link; and the Kernel reads nothing off a value but a name of a module of its own, where an import by the Kernel's name binds it, never a relative one or another module's re-export, or by a built-in type's method it calls, so no generator's frame hands it a builtin: "The purity check does not ask that kernel/ is the package Python imports: a kernel.py at the root, or a compiled module beside a source, runs unread" (issue 851) | `tests/test_tools.py::test_the_kernel_is_the_package_python_imports_and_reads_nothing_off_a_value`, `tools/check_purity.py`, mutant: "the Kernel is not held as the package Python imports, and reads what it likes off a value" |
| Nothing here is installed: no dependency manifest, and every import is the standard library or this repo | `tools/check_repo.py` |
| No code or data file names the proof-of-concept repo; nothing is fetched from it | `tools/check_repo.py` |
| A `run:` block in a workflow is at most ten lines and holds no decision | `tools/check_workflows.py` |
| The repo's settings are what the design rests on: the check is required, secrets are scoped to an environment, the default token only reads | waiting on `adapters/settings.py` |
