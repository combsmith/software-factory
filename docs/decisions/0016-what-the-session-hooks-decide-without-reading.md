# 0016. What the session hooks decide without reading

Status: proposed. The Maintainer accepts it by merging it, or strikes a row. It settles two items of
"Session hooks: git options that run a program, or move a local branch" (issue 90), under the
working ruling on "Session hooks that refuse: protected paths, merging, and the repo's own rules"
(issue 23): a hook guards against mistakes, and the Stop check and the rulesets are the boundary.

## Decision

A session hook reads a command's words. Two things it decides without reading further:

| What | Decided | Because |
|---|---|---|
| A git helper that runs a script, as `core.pager='sh x.sh'` does, or an option such as `grep -O` or `rebase -x` that names one | It is a program like any other. `tools/hooks/identity.py` refuses it, and `tools/hooks/protected.py` asks the person. Only `cat` and `less` pass: by their bare names in the first, and with no option that writes or loads in the second | A hook reads words, never a file. The script may be written in the same command, or between the hook's reading and git's running, and nothing a session needs runs a helper from a script given inline |
| The commits `git notes` and `git stash` make | Accepted by `tools/hooks/identity.py` without reading who makes them | They are on no branch, under refs/notes or at refs/stash, so no pull request carries one. Only a push takes one out of the clone, and the hook reads every commit a push sends, as it does a branch's |

## Why

Reading a script's file would make a hook's answer depend on a file the command itself can change,
and each new reading is a new spelling to get wrong; refusing costs only a configuration change made
in a command of its own, where the Maintainer sees it. Reading a notes or stash commit as a commit
would refuse a stash whenever the clone's identity is wrong, a mistake that cannot reach GitHub
without the push the hook already reads.

## Boundaries

| Boundary | Check |
|---|---|
| A helper that runs a script is refused by the identity hook and asked about by the other | `tests/test_hooks.py::test_a_helper_that_runs_a_script_is_a_helper_in_both_hooks` |
| A notes or stash commit passes, and a push that carries one by anyone but the Maintainer is refused | `tests/test_hooks.py::test_a_commit_on_no_branch_is_accepted_and_read_when_it_is_pushed` |
