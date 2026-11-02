# 0122. A called workflow checks out its own commit, not the tag that called it

Status: accepted. The Factory Builder's ruling of 2026-11-02 on ruling 14 of "Workflows: the frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape" (issue 196), once trial P-55 answered it.

## Decision

| What | Decided | Because |
|---|---|---|
| The checkout | The first job of `.github/workflows/pass.yml`, of `.github/workflows/run-jobs.yml` and of `.github/workflows/approve-job.yml` checks out `${{ job.workflow_sha }}`, which GitHub resolved when it called the workflow. Each later job still checks out the commit the first handed on | A tag can move between the call and the checkout, and then a job would run other code than the file GitHub called. This value cannot. It needs no grant, where the OIDC claim needs `id-token: write` |
| What it changes | Decisions 0066, 0071 and 0120 say each first job checks out `factory/v0-next`, and 0115 says each goes on doing so until a change uses this value. This is that change. Each said it would give way once a trial found such a value. Their other rows stand | Those records keep what they ruled; only which ref the first checkout names moves here |
| A moved Channel | A Release's name is still read from the tags on the commit checked out. A Run that starts after `next` moves runs the Release GitHub resolved for it | Nothing else about how a Release is named changes |

## Why

P-55 read the value and did not check out at it, so the checkout was run on its own, on the canary: run 41531201858 of `combsmith/software-factory-canary`, called at a tag from a caller on another commit, succeeded, with HEAD at the tag's commit and not the caller's. With `fetch-tags: true`, `git tag --points-at HEAD` read the tag; without it, nothing. `.github/workflows/pass.yml` and `.github/workflows/approve-job.yml` hold that input. `.github/workflows/run-jobs.yml`'s first job does not, and needs none, since `harness/read.py` names its Release from the commit through the API.

It lands before the first cut so the first Release holds it, since nothing calls these files yet and a failure here would otherwise first show on a live Factory.

A caller in another repo was not run: both were the canary. A Consumer's caller would likely need `repository: ${{ job.workflow_repository }}` as well, which slice 3 must try.

## Boundaries

| Boundary | Check |
|---|---|
| Each called workflow's first checkout is `${{ job.workflow_sha }}`, word for word, and the tag back on it is refused; each later job checks out the commit handed on | `tests/test_tools.py::test_the_commit_a_later_job_checks_out_is_the_releases_own`, `tests/test_tools.py::test_the_runs_jobs_keep_each_key_apart_and_always_leave_the_outcome` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
