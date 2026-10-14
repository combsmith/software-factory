# 0009. One fact, one place

Status: accepted. Source: decision 9 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

Each fact about the Factory is written once, as data, and everything else reads it. The set of
Roles is the listing of the Roles directory. Consumers, each Consumer's Ring and each Role's
triggers are each written once. A table of any of these in a document is generated.

## Why

In the proof of concept the list of agents existed in nine places and no two agreed. A copy is
correct on the day it is made.

## Boundaries

| Boundary | Check |
|---|---|
| A value held in both the authority table and the configuration agrees | `tools/check_authority.py` |
| Every data file under `config/` and `lifecycle/` is validated against a schema | `tools/check_examples.py` |
| The review standard is the rubric, and no page restates it | `tools/check_context.py` |
| A path or a test named in a document exists | `tools/check_context.py` |
| A generated table that is stale fails the required check | waiting on `roles/` |
