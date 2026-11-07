# 0150. Only the callers a check lists reach a GitHub write, each the writers it lists

Status: accepted. The Factory Builder's rulings of 2026-11-07 on "Only the write steps call a write: a check that keeps GitHub writes to an allowlist of callers" (issue 587), made on a derivation of main at 228fdc34 by syntax. The issue's allowlist named the direct callers. This record reads callers transitively, which adds two, and it corrects the issue's line on `harness/queue_step.py`.

## Decision

| What | Decided | Because |
|---|---|---|
| A write | A request built by `adapters/github.py`'s `request` with POST, PUT, PATCH or DELETE. Two are not writes: a GraphQL POST whose query, a literal or a text constant of its own module or another's, starts with `query`; and a token minted or revoked (`/app/installations/%d/access_tokens`, `/installation/token`), which is a credential. Every GraphQL query in `adapters/` is a `query`, `adapters/seen.py`'s and `adapters/items.py`'s among them; the mutations are `adapters/queue.py`'s `ENQUEUE`, `DEQUEUE` and `RESOLVE` | A GraphQL read is a POST, and a token is no write to the repo |
| A writer | An adapter function that holds a write. A function reaches one when it calls it, names it as a value, or names a class one of whose methods reaches it, through any number of calls and modules. A class is followed so because syntax cannot follow an instance: `harness/approve_step.py` hands `approve.Port` to `approve.job`, which calls its `approve` | The check is of who reaches a write, not who names one |
| The callers | Outside `adapters/` and `tests/`, six reach a writer, each the ones `CALLERS` in `tools/check_writes.py` lists. `harness/apply_step.py` reaches `effects._review`, `_check` and `_comment`. `harness/approve.py` and `harness/approve_step.py` reach `effects.approve`. `harness/queue.py` and `harness/queue_step.py` reach `queue.enqueue`, `dequeue` and `resolve`. `release/move.py` reaches `tags.write` and `deployments.record`. Each of these three is a failure: a new caller; a caller that reaches a writer it does not list; a listing that is no longer true | A write a Role's Run reaches outside its Effects should never rest on a review alone |
| What the issue had | The issue listed four callers and said `harness/queue_step.py` reaches only credentials and reads. It reaches the queue's three mutations through `queue.Port`, as `harness/approve_step.py` reaches the approval through `approve.Port`. Both are on the list. `controller/__main__.py` and `harness/read.py` reach only credentials and reads, as the issue said | Read from the code, not the issue |
| Outside adapters/ | A request built by `adapters/github.py`'s `request` is a read, and no Python holds a write verb as a whole string, except `tools/hooks/identity.py` and `tools/hooks/protected.py`, which read a command's verb and send none. `tools/commits_are_the_maintainers.py` and `harness/head.py` build GETs, which pass | A write is an adapter's alone |
| What cannot be read | A method that is not a literal, a GraphQL query that is no text constant, an adapter module used as a value, or `import *` from one, is a problem, never a pass. `adapters/github.py`'s `Live.send` and `Replay.send` check again a request already built, and are named as the transport's own | The check fails closed |
| A change to the list | Adding a caller, or a writer to one, is a change to who writes to GitHub, and is the Maintainer's, in the change that makes it. Whether a listed step writes only what its Task permits stays with `apply`'s refusal and its tests | The list says who may, not what |
| Not held here: the Controller's writes | `adapters/effects.py`'s `apply`, `_dispatch`, `tracking` and `write_status`, entered from `.github/workflows/pass.yml` by `python3 -m adapters.effects`, have no caller in Python outside `adapters/`. `tools/check_workflows.py` holds what each workflow runs | Named, so that no one reads them as held here |
| Not held here: the workflows' dispatches | The `gh api -X POST …/poller.yml/dispatches` step in `.github/workflows/approve-job.yml`, `.github/workflows/run-jobs.yml` and `.github/workflows/queue-job.yml` is held by `tools/check_workflows.py`, as its template | Named, so that no one reads them as held here |
| Not held here: the trials' writes | `tools/trial_as_app.sh`, `tools/trial_p12_status.sh`, `tools/trial_p4_narrow.sh`, `tools/trial_p8_cost.sh` and `tools/trial_p58_edits.sh` write by curl or gh. Nothing holds them yet: each is run by hand by the Maintainer, on the canary, with an App's key | Named, so that no one reads them as held here |

## Why

A Role writes only through `apply`, which refuses an Effect its Task does not permit, and `tools/check_repo.py` keeps the network in `adapters/github.py`. Neither held who calls a write: a new call to an adapter function that writes, from code a Role's Run reaches, passed `make verify`, and only a review would see it. Read by syntax and transitively, the check holds who reaches a write, as the code is, not as an issue describes it.

## Boundaries

| Boundary | Check |
|---|---|
| On main, the six callers reach exactly the writers they list | `tests/test_tools.py::test_on_main_only_the_callers_listed_reach_a_write_and_each_what_it_lists` |
| A new module calling `effects.role_write` fails until it is listed | `tests/test_tools.py::test_a_new_caller_of_a_writer_fails_until_it_is_listed` |
| A writer two calls deep is reached through the modules between | `tests/test_tools.py::test_a_writer_two_calls_deep_is_reached_through_the_modules_between` |
| A class named reaches its methods | `tests/test_tools.py::test_a_class_named_reaches_its_methods` |
| A listed caller that reaches a new writer, or none, fails, and so does a listing of a module that is gone | `tests/test_tools.py::test_a_listed_caller_that_reaches_a_new_writer_or_none_fails` |
| A GraphQL `mutation` constant in a new reader is a write, a `query` by POST a read, and a query that is no constant a problem | `tests/test_tools.py::test_a_graphql_mutation_is_a_write_and_a_query_a_read` |
| A token minted or revoked is a credential, not a write | `tests/test_tools.py::test_minting_or_revoking_a_token_is_a_credential_not_a_write` |
| Outside adapters/, a request is a read and no write verb is held; in adapters/, a method that is not a literal is a problem | `tests/test_tools.py::test_outside_adapters_a_request_reads_and_no_verb_is_held` |
| An adapter module handed on as a value fails | `tests/test_tools.py::test_an_adapter_module_handed_on_as_a_value_cannot_be_read_and_fails` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
