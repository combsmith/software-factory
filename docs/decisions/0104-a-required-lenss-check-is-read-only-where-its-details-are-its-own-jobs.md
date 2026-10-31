# 0104. A required Lens's check is read only where its details are its own job's

Status: accepted. The Factory Builder's ruling of 2026-10-30 on "Checks port: a required Lens's check is read only where its details URL is the job's own, as P-35 found" (issue 439). It adds to `docs/decisions/0026-a-lens-is-read-from-its-own-app-and-workflow-its-job-judges-every-job-it-waits-on-and-only-what-gates-holds-a-merge.md` what its pin of the App and the file could not prove, as record `docs/decisions/0103-a-check-a-job-creates-reads-as-the-first-suites-workflow-an-upload-can-turn-codeql-neutral-and-the-queues-base-and-a-stale-dismissal-hold.md` found. Every check under the name must still pass.

## Decision

| What | Decided | Because |
|---|---|---|
| The read | `adapters/checks.py` reads each check's `detailsUrl`, its own id and its check suite's workflow run's id. Its details are its own job's only where the URL is `https://github.com/{owner}/{repo}/actions/runs/{run id}/job/{job id}`, whole, with that run id and its own id. Anything else is not: another form, a URL absent or malformed, an id that is none | A job's token can create a check that lands in another workflow's suite and borrows its name, App and file. GitHub kept such a check's details at `/runs/ID` whatever it was given, at the post or by PATCH, in the job's form with its own id, and a job's token cannot change a real job's (P-35: GitHub answers 200 and the field stands) |
| The rule | A check whose details are not its own job's is read with no file, `workflow` null, whatever file its suite names. So under a required Lens's name it is the foreign check decision 0026 already reads: the Lens is unreadable, `check_unreadable`, for the Maintainer, with the evidence `<lens>:from_workflow:unreadable`, whatever it or the Lens's own checks conclude, before a conflict or any Lens's failure, and only a push clears it. A Lens no workflow runs, `code-scanning`, reads no file already | No new fact: `facts/1` and the Kernel do not change, so held-out cases and the eval gate do not move, and no text from outside reaches a decision. The Factory Builder's ruling |
| What it costs | The evidence reads as any check with no readable file, so it does not itself say a job created this one. A person who looks sees why from the check's own URL. Accepted | The Factory Builder's ruling: a fact that said so would move the held-out cases and tie this to the Maintainer's next act |
| The release's read | `adapters/candidate.py`'s `verified` takes the rule: `verify`'s details must be its own job's, by the check run's id and its one workflow run's id, or the commit is `not_verified` | It reads the same check by the same pin, so a created check could pass as `verify` where the real one's run was replaced as the latest of its suite |
| `tools/` | Nothing to change. `tools/needs_passed.py` reads `needs` from GitHub's expressions, and no tool reads a check run | |
| An acceptance result | Not taken here: a result is still read by `reports_for`, its name, App and file, and its port is not built. It is "Acceptance: a result is read only where its check's details are its own job's (raised by record 0104)" (issue 445), which that port can meet the same way | Named so that it is not read as held |
| If GitHub changes the form | Every required Lens that a workflow runs goes unreadable, and every item holds for the Maintainer | The accepted failure: loud, and on the safe side. The form is what the attempts of P-35 showed, and this repo's own checks, a re-run's among them, read on 2026-10-30; it is no promise of GitHub's |

## Why

Decision 0026 pinned a Lens to its App and its file, and P-35 showed a job can borrow both. The details are the one thing such a check could not borrow when it was tried, so that is what tells the two apart, at the port, and anything that does not match fails closed as a foreign check does.

## Boundaries

| Boundary | Check |
|---|---|
| Details are a job's own only in the job's form, whole, with the run's id and the check's own; anything else is not, and an absent or malformed URL or id is not; a check keeps its file only where they are | `tests/test_adapters.py::test_a_checks_details_are_its_own_jobs_only_in_that_form_with_those_ids` |
| In P-35 a real job keeps its file, a created check is read with none, it does not pass a Lens, and the Kernel reads it as foreign | `tests/test_adapters.py::test_a_created_check_under_a_lens_name_does_not_pass` |
| `verify`'s details must be its own job's for a commit to be verified | `tests/test_release_step.py::test_verify_counts_only_from_verify_yml_as_the_kernels_lens_reads_it` |
| The fake models a created check, as the port reads it, beside a failure and alone before its job has a check run, and no action follows it | `tests/test_simulator.py::test_the_seeds_create_a_check_under_a_lens_name` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
