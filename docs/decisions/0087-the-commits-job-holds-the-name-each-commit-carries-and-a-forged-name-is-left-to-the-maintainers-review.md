# 0087. The commits job holds the name each commit carries, and a forged name is left to the Maintainer's review

Status: accepted. The Maintainer's choice of 2026-10-29, for a finding of a CodeRabbit security scan,
"commits_are_the_maintainers.py takes self-declared Git author and committer identity as proof of maintainer authorship" (issue 374).
It adds to `docs/decisions/0041-identity-is-held-by-the-required-check-that-reads-each-commit-and-the-session-hook-guards-mistakes.md`,
whose Decision stays in force, and says what that check does not hold.

## Decision

| What | Decided | Because |
|---|---|---|
| What the `commits` job holds | That every commit a pull request carries names the Maintainer, as `config/hooks.json` gives them, as its author and its committer, GitHub's own commits told by their place as 0041 says. It catches the Factory's own identities, an agent's or an App's, committing under their own names, and any honest commit under another name | Those are the commits the Factory makes, and git records each one's names as the committing process set them |
| What it does not hold | That the Maintainer made the commit. The names are what the commit's maker wrote, and anyone can write the Maintainer's name and email into a commit and open a pull request from a fork. Such a commit passes the job, and is caught only by the Maintainer's review of the pull request, which every change to main already needs | The names are not authenticated, and nothing the job reads is |
| The rule's words | AGENTS.md, `tools/AGENTS.md` and the check's own text say the commits name the Maintainer, not that they are the Maintainer's | A rule says what its check holds, and no more |
| Considered and not taken | A: the Maintainer signs every commit with an SSH key, a file of allowed signers under `config/` holds its public half, and the job, still run from the base, refuses any commit git does not read as signed by that key (`gpg.format=ssh`, `gpg.ssh.allowedSignersFile`, `%G?`). B: a `required_signatures` rule on main's ruleset, so GitHub merges only commits it verified, with the committer's email owned by the signing account. Either needs the Maintainer to sign in every checkout a builder commits from | The Maintainer chose to accept the risk and keep commits unsigned. Either can be taken later, by a record that says so |

## Why

The scan was right: the names the job compares are self-declared, and decision 0041 itself says a name can be
forged. Holding authorship against a forger needs a key the Maintainer alone holds, and so a signing setup on every
checkout the Factory's builders commit from. The Maintainer weighed that against what a forged name gains, a pull
request that still waits on their review, and chose to record the limit rather than add the setup.

## Boundaries

| Boundary | Check |
|---|---|
| Every commit's author and committer are read from git's record, and another name than the Maintainer's refuses; GitHub's commits are told by their place | `tests/test_tools.py::test_every_commit_a_pull_request_carries_is_the_maintainers` |
| The job runs the base's tool, and `verify` needs it | `tests/test_tools.py::test_a_lens_job_that_judges_its_needs_runs_from_the_base` |
