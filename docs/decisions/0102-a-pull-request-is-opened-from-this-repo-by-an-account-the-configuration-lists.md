# 0102. A pull request is opened from this repo by an account the configuration lists

Status: accepted. The Maintainer's approval of 2026-10-30, for "Identity: a keyless check that the pull request's opener and head repository are the Maintainer's (raised by 0087's review)" (issue 409). It extends `docs/decisions/0087-the-commits-job-holds-the-name-each-commit-carries-and-a-forged-name-is-a-risk-the-maintainer-accepts.md`, taking the option C it left not yet weighed. What 0087 holds of the commits' names stands, and so does its refusal of A and B.

## Decision

| What | Decided | Because |
|---|---|---|
| What is refused | A pull request whose opener is not on the list, by its login and its id, or whose head repository is not this repo: a fork, the Maintainer's own among them, or one GitHub no longer names. A payload or a list that cannot be read refuses too | GitHub writes both values, and the commit's maker writes neither |
| Who may open one | `openers` in `config/hooks.json`, as the base holds it, each with what the account is: today the Maintainer alone. The id is read beside the login, since a login can be renamed and taken. A refusal names everyone on the list and what each is | The list sits beside the Maintainer's name, on a path a change cannot take itself off (decision 0020) |
| When the Factory opens its own | A record adds that App's login, `name[bot]`, and its id to `openers`, when an Intent can open one. The schema and the check already read such a login, and nothing else changes. It lands with the writer of decision 0097 | The opener is then not always the Maintainer, and each account is added by a decision |
| Where it reads them | The event's payload, the file the runner leaves at `GITHUB_EVENT_PATH`, and not values the job is given, as 0087's option C had it. No expression is added, so the job's shape and what it is told stay as they were | A job's env is written in the workflow a pull request can change; the payload is not |
| Where it runs | Inside `tools/commits_are_the_maintainers.py`, the `commits` job's one step, which reports both verdicts and passes only on both. The commits are read just as before | A new job runs the base's tool, which the pull request adding it would not find, and it would fail itself; decision 0041's tool took two pull requests for that |
| On a merge group | The payload names no opener, so nothing is read, and the job says so. An event that says merge group over a payload that is not one refuses. What holds it is the pull request's own run: the ruleset requires `verify` of a pull request before it merges, an opener and a head repository cannot change once opened, and a fork's author cannot enqueue, having no write. That a queue refuses a pull request whose required check failed is GitHub's rule as documented, and not tried | Reading the number out of the queue's branch and asking GitHub would give this job a token to read what the pull request's run already read |
| A and B | Still not taken. Either needs the Maintainer's key in every checkout a builder commits from, and B's effect on a squash through the queue is not grounded (0087). This reaches as far, to a forger from outside, with no key to keep | The Maintainer's choice in 0087 stands, and this asks nothing of it |
| What it does not hold | That the Maintainer opened it: a holder of their login passes, as every builder here does by design. A pull request that rewrites `.github/workflows/verify.yml` can rewrite this job, since `pull_request` runs the workflow its merge commit holds; `.github/` is on the list, a change to it needs a model Lens, and an outside one waits on a person (`outside_not_admitted`). Not tried | A rule says what its check holds, and no more |

## Why

0087 left a forged name to the one gate a forger from outside meets, the Kernel's admission. This puts a second in front of it, at the required check, for no key and no token: a fork's forged commits now fail on who opened them, whatever names they carry. It also stops an account inside the repo opening under its own login, which the commits' names never could.

## Boundaries

| Boundary | Check |
|---|---|
| Each account on the list passes, an App's login among them; another account, a login with another's id, an id under another's login, a fork, or a head repository GitHub no longer names, refuses; a refusal names who may | `tests/test_tools.py::test_a_pull_request_is_opened_from_this_repo_by_an_account_the_configuration_allows` |
| A payload or a list that cannot be read, or another event, refuses; an empty list allows none | `tests/test_tools.py::test_a_pull_request_is_opened_from_this_repo_by_an_account_the_configuration_allows` |
| A merge group's payload passes with nothing read; one that is not a merge group's refuses | `tests/test_tools.py::test_a_pull_request_is_opened_from_this_repo_by_an_account_the_configuration_allows` |
| This repo's list holds the Maintainer alone, by the login and the id the configuration gives them elsewhere | `tests/test_tools.py::test_a_pull_request_is_opened_from_this_repo_by_an_account_the_configuration_allows` |
| The job refuses for the commits or for the opener, neither in place of the other, and says what it held | `tests/test_tools.py::test_the_job_refuses_for_the_commits_or_the_opener_and_says_what_it_holds` |
| The list is required, holds at least one account, and each has a login, an id and what it is | `tools/check_examples.py` |
| The Factory's App joins the list by a record when an Intent can open a pull request | waiting on `harness/push.py` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
