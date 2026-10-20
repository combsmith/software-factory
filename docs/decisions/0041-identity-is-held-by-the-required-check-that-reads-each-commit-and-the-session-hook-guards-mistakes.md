# 0041. Identity is held by the required check that reads each commit, and the session hook guards mistakes

Status: accepted. Taken as a working ruling on 2026-10-20, which the Maintainer may overturn in review, for
"Identity: every commit a pull request carries is the Maintainer's, checked outside the shell" (issue 204). It adds to
`docs/decisions/0023-a-lenss-verdict-and-the-secret-scans-rules-run-from-the-base.md` and to
`docs/decisions/0040-the-identity-hook-reads-where-the-shell-may-stand-and-a-program-it-does-not-read-may-write.md`,
whose Decisions stay in force, and settles what their rows left until this check was built: where identity is
enforced. The optional git hooks the issue names are not built: they would be helpers of the same class as the session
hooks, through a `core.hooksPath` every worktree shares, which the Maintainer has not asked for; they can be a story of
their own.

## Decision

| What | Decided | Because |
|---|---|---|
| Where identity is held | The required check: its job `commits` runs `tools/commits_are_the_maintainers.py` from a checkout of the base, never the head, as `verify` runs `tools/needs_passed.py`. It fetches the head from origin, the repo itself, reads each commit between the base and the head, and refuses unless each one's author and committer are the identity `config/hooks.json` names as the Maintainer. No identity is a literal in the code | A rule that matters is held by a required check; the session hook reads words, which cannot be exact, and the rulesets read no commit's author |
| The commits GitHub makes | Told by their place, never by the name they carry: on a merge group the head, which the queue made, is read for its author alone; on a pull request every commit between the base and the head is the pull request's. A commit whose committer is spelt as GitHub's anywhere else refuses, so an author cannot hide a commit by naming GitHub as its committer. The Maintainer does not use GitHub's "update branch", whose merge commit GitHub commits on the pull request's branch | A name can be forged in a commit; a place in the range cannot |
| What refuses | Another author or committer on any commit the pull request carries; a range that holds no commit; a head the check cannot fetch, a commit it cannot read, or a configuration it cannot read; an event other than pull_request or merge_group | The check fails closed: what it cannot read, it refuses |
| The session hook's scope | `tools/hooks/identity.py` stays a mistake guard: it catches an honest commit, push or GitHub write under the wrong identity before it is made, and a spelling built to hide one is out of its scope, as 0032 and 0040 say. This check reads what git recorded, whatever the spelling, after the fact | Hooks are helpers; only CI enforces a rule (the Maintainer, 2026-10-19) |

## Why

The session hook's rounds that ended in decision 0040 showed that reading a command's text cannot be made exact, and the boundary
decision 0023 named, the Stop check and the rulesets, read no commit's author. Authorship therefore rested on the
Maintainer reading each pull request. One job that reads git's own record of each commit closes that with a few
dozen lines, costs a minute of a runner, and runs from the base so that no change can pass its own verdict. The
commits the platform makes are the only ones not the Maintainer's, and they stand in known places.

## Boundaries

| Boundary | Check |
|---|---|
| Every commit between the base and the head, fetched from origin, is read, and another author or committer refuses with the commit named; on a merge group the head is read for its author alone; an empty range, an unfetchable head, an event the check does not know, and a configuration it cannot read refuse; the identity is the configuration's | `tests/test_tools.py::test_every_commit_a_pull_request_carries_is_the_maintainers` |
| The job checks out the base and runs the base's tool, and `verify` needs it | `tests/test_tools.py::test_the_required_check_that_has_drifted_from_its_example_is_caught`, `tests/test_tools.py::test_a_lens_job_that_judges_its_needs_runs_from_the_base` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
