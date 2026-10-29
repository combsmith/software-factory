# 0083. Thirty thread resolutions in a row meet no secondary limit

Status: accepted. The second machine-user window's P-23, under the orchestrator's rulings of 2026-10-28.

## Decision

| What | Decided | Because |
|---|---|---|
| P-23 | `trials/P-23.json`, pass as written: an App with `contents: write` resolved 30 threads it had opened, one after another as fast as GitHub answered, each 200 with no error, in 40 seconds, the GraphQL count rising from 8 to 37 of 5,000 | The burst the Factory's resolutions make at a merge meets no secondary limit |
| What it does not measure | An hour's rate: the burst lasted 40 seconds and reached no limit, and the threads were the App's own | A fixture says what it shows and no more |

## Why

The design budgets about 22 threads a pull request at the Factory's merge rate; a burst of 30 is above it and met no
limit, which is what the budget needs before an hour's rate is asked.

## Boundaries

| Boundary | Check |
|---|---|
| The fixture's writes are on canary nodes a read answered | `tools/check_trials.py` |
