# 0017. What the session hooks decide without reading, and every commit a push sends is read

Status: accepted. Replaces `docs/decisions/0016-what-the-session-hooks-decide-without-reading.md`,
and keeps all of it but one row, which "Identity hook: a push refspec it cannot read is refused"
(issue 103) settles: the identity hook reads every commit a push sends, and refuses a refspec it
cannot read. It adds the rows that issue and "Session hooks: spellings left after the git-options
story" (issue 106) decide. The Maintainer accepts it by merging it, or strikes a row. As before, under
the working ruling on "Session hooks that refuse: protected paths, merging, and the repo's own
rules" (issue 23): a hook guards against mistakes, and the Stop check and the rulesets are the
boundary.

## Decision

A session hook reads a command's words. These things it decides without reading further:

| What | Decided | Because |
|---|---|---|
| A git helper that runs a script, as `core.pager='sh x.sh'` does, or an option such as `grep -O` or `rebase -x` that names one | It is a program like any other. When given by `-c` or an option, `tools/hooks/identity.py` refuses it; given by `-c`, an option or the environment, `tools/hooks/protected.py` asks the person. Only `cat` and `less` pass: by their bare names in the first, and with no option that writes or loads in the second. The settings that name a program are one list, in both hooks | A hook reads words, never a file. The script may be written in the same command, or between the hook's reading and git's running, and nothing a session needs runs a helper from a script given inline |
| The commits `git notes` and `git stash` make | Accepted by `tools/hooks/identity.py` without reading who makes them | They are on no branch, under refs/notes or at refs/stash, so no pull request carries one. Only a push takes one out of the clone, and the hook reads every commit a push sends, as it does a branch's: a mirror push ref by ref, refs/notes and refs/stash among them |
| A protocol allowed in the command (`protocol.*.allow`, GIT_ALLOW_PROTOCOL) or an ext:: URL, and `ssh.variant` | The first are refused by `tools/hooks/identity.py` for every git command. `ssh.variant`, refused until now, is not | The ext:: transport runs the command its URL names, and any command may run a transport: in a partial clone, cat-file, log or checkout fetch a missing object through it. `ssh.variant` says only how git calls ssh, and names no program |
| A push's refspec, or a remote, held in a variable or a command substitution, and a refspec with a wildcard | A variable an earlier command in the same command set to a plain value is read as that value. `$(git branch --show-current)`, `$(git rev-parse --abbrev-ref HEAD)` and `$(git symbolic-ref --short HEAD)` are HEAD where the push runs. Every other one, and a wildcard, `tools/hooks/identity.py` refuses | What git will push is not in words the shell has yet to expand, and a wildcard is a list of refs the hook does not make. A value the command itself set is as plain as the word, and the branch the shell is on is HEAD |

## Why

Reading a script's file would make a hook's answer depend on a file the command itself can change,
and each new reading is a new spelling to get wrong; refusing costs only a configuration change made
in a command of its own, and what holds is the Stop check and the rulesets. Reading a notes or
stash commit as a commit would refuse a stash whenever the clone's identity is wrong, a mistake that
cannot reach GitHub without a push. A protocol is a policy, not a program, but the one that allows
ext:: lets a URL run one, and the hook cannot tell which command will reach a transport. A refspec
the hook cannot read is refused rather than read as HEAD, which let a push carry another person's
commit; spelling it plainly costs the session a word.

## Boundaries

| Boundary | Check |
|---|---|
| A helper that runs a script is refused by the identity hook and asked about by the other | `tests/test_hooks.py::test_a_helper_that_runs_a_script_is_a_helper_in_both_hooks` |
| A notes or stash commit passes, and a push that carries one by anyone but the Maintainer is refused | `tests/test_hooks.py::test_a_commit_on_no_branch_is_accepted_and_read_when_it_is_pushed` |
| A protocol allowed is refused for every command, and `ssh.variant` for none | `tests/test_hooks.py::test_a_protocol_allowed_is_refused_for_every_command_and_ssh_s_variant_for_none` |
| The identity hook refuses every setting the protected hook knows to name a program: one list | `tests/test_hooks.py::test_every_helper_setting_the_protected_hook_knows_is_refused` |
| A mirror push reads every ref it sends, refs/stash and refs/notes among them | `tests/test_hooks.py::test_a_mirror_push_reads_every_ref_it_sends` |
| A push refspec in a variable no earlier command set, in a command substitution, or with a wildcard is refused | `tests/test_hooks.py::test_a_push_refspec_the_hook_cannot_read_is_refused` |
| A push refspec in a variable an earlier command set to a plain ref is read as that ref, and the branch the shell is on as HEAD | `tests/test_hooks.py::test_a_push_refspec_in_a_variable_the_command_set_is_read` |
| A remote held in a variable is read from what the command set, or refused | `tests/test_hooks.py::test_a_remote_held_in_a_variable_is_read_from_what_the_command_set_or_refused` |
