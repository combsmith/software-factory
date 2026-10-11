# 0010. Built greenfield, cut over one repo and one Intent family at a time

Status: accepted. Source: decision 10 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

Factory code is written here. The proof of concept receives defect fixes and nothing else. The
first component is the review Intent, running on this repo, so that the Factory reviews everything
built after it. Cutover of a Consumer is pause, then repoint: for any repo and Intent family,
exactly one line serves it. Stopping is the Maintainer's decision, on adoption and use; no measure
stops the work automatically.

## Why

A rewrite in place inherits the rules it means to replace. A cutover in which both lines serve the
same work is the one failure that cannot be undone by reversing a switch.

## Boundaries

| Boundary | Check |
|---|---|
| Nothing here is read from the proof-of-concept repo | `tools/check_repo.py` |
| For any repo and Intent family, exactly one line serves it | waiting on `release/` |
| An Intent family is cut over only after its eval set exists | waiting on `evals/` |
