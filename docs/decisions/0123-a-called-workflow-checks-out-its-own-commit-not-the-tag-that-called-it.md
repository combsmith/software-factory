# 0123. A called workflow checks out its own commit, not the tag that called it

Status: accepted. The Factory Builder's ruling of 2026-11-02 on ruling 14 of "Workflows: the frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape" (issue 196), once trial P-55 answered it.

## Decision

| What | Decided | Because |
|---|---|---|
| The checkout | The first job of `.github/workflows/pass.yml`, of `.github/workflows/run-jobs.yml` and of `.github/workflows/approve-job.yml` checks out `${{ job.workflow_sha }}`, which GitHub resolved when it called the workflow. Each later job still checks out the commit the first handed on | A tag can move between the call and the checkout, and then a job would run other code than the file GitHub called. This value cannot. It needs no grant, where the OIDC claim needs `id-token: write` |
| What it changes | Decisions 0066 and 0120 say each first job checks out `factory/v0-next`, as 0071 did before 0120 replaced it, and 0115 says each goes on doing so until a change uses this value. This is that change. The miss 0066 and 0120 accept, a Channel moved away and back before the checkout, is gone with it. Their other rows stand | Those records keep what they ruled; only which ref the first checkout names moves here |
| A moved Channel | A Release's name is still read from the tags on the commit checked out. A Run runs the Release GitHub resolved when the Run was made, so `release_moved` now ends only a Run made after the Channel moved from its pass's Release | Nothing else about how a Release is named changes |
| What that gives up | A rollback no longer stops a Run already made and still waiting: it runs the withdrawn Release, with its keys, where the tag's checkout would have ended it `release_moved`. If that Release is writing harm, set the Pause first, as `.claude/skills/cut-a-release/SKILL.md` says. A re-run is no way back to it, since it resolves the tag again | One Run wholly on one Release is what this buys, and the Pause is the stop for harm |

## Why

P-55 read the value and did not check out at it, so the checkout was run on its own, on the canary: run 41531201858 of `combsmith/software-factory-canary`, called at a tag from a caller on another commit, on push with no environment, succeeded, with HEAD at the tag's commit and not the caller's. With `fetch-tags: true`, `git tag --points-at HEAD` read the tag; without it, nothing. `.github/workflows/pass.yml` and `.github/workflows/approve-job.yml` hold that input. `.github/workflows/run-jobs.yml`'s first job does not, and needs none, since `harness/read.py` names its Release from the commit through the API.

It lands before the first cut so the first Release holds it, since nothing calls these files yet and a failure here would otherwise first show on a live Factory.

Run 41549513297 of the canary moved the tag while the Run's first job waited, before the called job began. The called job was still the first commit's file, by its job's name and by `referenced_workflows`. Its re-run, with the tag then on the second commit, was the second commit's file. That probe did not read `job.workflow_sha` itself. GitHub's documentation gives the value as empty on GitHub Enterprise Server, where a checkout would fall back to the caller's commit; it has not been seen empty here.

A caller in another repo was not run: both were the canary. A Consumer's caller would likely need `repository: ${{ job.workflow_repository }}` as well, which slice 3 must try.

## Boundaries

| Boundary | Check |
|---|---|
| Each called workflow's first checkout is `${{ job.workflow_sha }}`, word for word, and the tag back on it is refused; each later job checks out the commit handed on | `tests/test_tools.py::test_the_pass_uploads_its_record_before_it_dispatches`, `tests/test_tools.py::test_the_approving_act_holds_the_approvers_token_alone`, `tests/test_tools.py::test_the_commit_a_later_job_checks_out_is_the_releases_own`, `tests/test_tools.py::test_the_runs_jobs_keep_each_key_apart_and_always_leave_the_outcome` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
