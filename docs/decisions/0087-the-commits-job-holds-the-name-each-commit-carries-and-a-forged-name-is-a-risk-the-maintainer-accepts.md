# 0087. The commits job holds the name each commit carries, and a forged name is a risk the Maintainer accepts

Status: accepted. The Maintainer's choice of 2026-10-29, for a finding of a CodeRabbit security scan,
"commits_are_the_maintainers.py takes self-declared Git author and committer identity as proof of maintainer authorship" (issue 374).
It adds to `docs/decisions/0041-identity-is-held-by-the-required-check-that-reads-each-commit-and-the-session-hook-guards-mistakes.md`,
whose Decision stays in force, and says what that check does not hold.

## Decision

| What | Decided | Because |
|---|---|---|
| What the `commits` job holds | That every commit a pull request carries names the Maintainer, as `config/hooks.json` gives them, as its author and its committer, GitHub's own commits told by their place as 0041 says. It catches the Factory's own identities, an agent's or an App's, committing under their own names, and any honest commit under another name | Those are the commits the Factory makes, and git records each one's names as the committing process set them |
| What it does not hold | That the Maintainer made the commit. The names are what the commit's maker wrote, and anyone can write the Maintainer's name and email into a commit. Such a commit passes the job | The names are not authenticated, and nothing the job reads is |
| What limits a forged name | No review: main's ruleset needs no approving review (`config/rulesets.json`), and a change converges on the model reviews and the machine user's approval (decision 0020). A pull request from a fork waits on the Kernel until a person admits it (`outside_not_admitted`). Inside the repo, any holder of write access can carry the Maintainer's name past this job, as the Factory's builders do by design, since they commit under it | The admission of an outside pull request is the one gate a forger from outside meets, and it reads the account that opened it, not the commits |
| The rule's words | AGENTS.md, `tools/AGENTS.md`, the check's own text, its refusals and its success, and the comment `.github/workflows/verify.yml` and the workflows standard share say the commits name the Maintainer, not that they are the Maintainer's | A rule says what its check holds, and no more |
| Considered and not taken | A: the Maintainer signs every commit with an SSH key, a file of allowed signers under `config/` holds its public half, and the job, still run from the base, refuses any commit git does not read as signed by that key (`gpg.format=ssh`, `gpg.ssh.allowedSignersFile`, `%G?`). B: a `required_signatures` rule on main's ruleset. Either needs the Maintainer to sign in every checkout a builder commits from, so a builder's checkout holds the key, and either stops a forger from outside alone. B's effect is not grounded: main merges by squash through the queue, so the commit that lands is GitHub's own, and whether the rule reads the pull request's commits at all has not been tried | The Maintainer chose to accept the risk and keep commits unsigned. Either can be taken later, by a record that says so |
| Not yet weighed | C, which needs no key: the job is given the pull request's opener and its head repository, which GitHub authenticates (`github.event.pull_request.user.login`, `head.repo.full_name`), as data, and refuses a pull request opened by another account or from a fork. It reaches as far as A and B, a forger from outside, and is the Maintainer's to weigh | Raised by the security pass on this record's pull request, after the Maintainer's choice |
| What else is not held | The commits are read against one base, on the `pull_request` event's default types. A pull request opened against another branch and retargeted to main is not read again, since `edited` is not among them. Not tried | It gives a forger nothing a forged name does not |

## Why

The scan was right: the names the job compares are self-declared, and decision 0041 itself says a name can be
forged. A key in every checkout the Factory's builders commit from would stop a forger from outside, not a builder,
which would hold the key. The Maintainer weighed that setup and chose to record the limit rather than add it. What a
forged name gains is no review: main needs none, and only a pull request from outside waits on a person.

## Boundaries

| Boundary | Check |
|---|---|
| Every commit's author and committer are read from git's record, and another name than the Maintainer's refuses; GitHub's commits are told by their place | `tests/test_tools.py::test_every_commit_a_pull_request_carries_is_the_maintainers` |
| What the check says when every commit passes is what it holds: the commits name the Maintainer, the committer where GitHub did not commit it | `tests/test_tools.py::test_every_commit_a_pull_request_carries_is_the_maintainers` |
| The job runs the base's tool, and `verify` needs it | `tests/test_tools.py::test_a_lens_job_that_judges_its_needs_runs_from_the_base` |
| Option C is taken by decision 0102: a pull request is opened from this repo by an account the configuration lists | `tests/test_tools.py::test_a_pull_request_is_opened_from_this_repo_by_an_account_the_configuration_allows` |
| A pull request retargeted to main is read again, by decision 0102 | `tests/test_tools.py::test_the_commits_job_reads_the_pull_requests_commits_from_the_base` |
