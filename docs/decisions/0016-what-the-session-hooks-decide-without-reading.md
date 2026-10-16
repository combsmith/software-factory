# 0016. What the session hooks decide without reading

Status: replaced by `docs/decisions/0017-the-session-hooks-read-every-commit-a-push-sends.md`, which holds the
rule in force and its boundaries. It settled three items of "Session hooks: git options that run a
program, or move a local branch" (issue 90), under the working ruling on "Session hooks that refuse:
protected paths, merging, and the repo's own rules" (issue 23): a hook guards against mistakes, and
the Stop check and the rulesets are the boundary.

## Decision

A session hook reads a command's words. Three things it decides without reading further:

| What | Decided | Because |
|---|---|---|
| A git helper that runs a script, as `core.pager='sh x.sh'` does, or an option such as `grep -O` or `rebase -x` that names one | It is a program like any other. When given by `-c` or an option, `tools/hooks/identity.py` refuses it; given by `-c`, an option or the environment, `tools/hooks/protected.py` asks the person. Only `cat` and `less` pass: by their bare names in the first, and with no option that writes or loads in the second | A hook reads words, never a file. The script may be written in the same command, or between the hook's reading and git's running, and nothing a session needs runs a helper from a script given inline |
| The commits `git notes` and `git stash` make | Accepted by `tools/hooks/identity.py` without reading who makes them | They are on no branch, under refs/notes or at refs/stash, so no pull request carries one. Only a push takes one out of the clone, and the hook reads every commit a push of plain refspecs sends, as it does a branch's. A refspec in a variable or a command substitution it does not yet read: "Identity hook: a push refspec it cannot read is refused" (issue 103) |
| A protocol allowed in the command (`protocol.*.allow`, GIT_ALLOW_PROTOCOL) or an ext:: URL, and `ssh.variant` | The first are refused by `tools/hooks/identity.py` for every git command. `ssh.variant`, refused until now, is not | The ext:: transport runs the command its URL names, and any command may run a transport: in a partial clone, cat-file, log or checkout fetch a missing object through it. `ssh.variant` says only how git calls ssh, and names no program |

## Why

Reading a script's file would make a hook's answer depend on a file the command itself can change,
and each new reading is a new spelling to get wrong; refusing costs only a configuration change made
in a command of its own, and what holds is the Stop check and the rulesets. Reading a notes or
stash commit as a commit would refuse a stash whenever the clone's identity is wrong, a mistake that
cannot reach GitHub without a push. A protocol is a policy, not a program, but the one that allows
ext:: lets a URL run one, and the hook cannot tell which command will reach a transport.

## Boundaries

| Boundary | Check |
|---|---|
| A helper that runs a script is refused by the identity hook and asked about by the other | `tests/test_hooks.py::test_a_helper_that_runs_a_script_is_a_helper_in_both_hooks` |
| A notes or stash commit passes, and a push that carries one by anyone but the Maintainer is refused | `tests/test_hooks.py::test_a_commit_on_no_branch_is_accepted_and_read_when_it_is_pushed` |
| A protocol allowed is refused for every command, and `ssh.variant` for none | `tests/test_hooks.py::test_a_protocol_allowed_is_refused_for_every_command_and_ssh_s_variant_for_none` |
