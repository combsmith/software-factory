# 0017. The session hooks read every commit a push sends

Status: accepted. Replaces `docs/decisions/0016-what-the-session-hooks-decide-without-reading.md`,
and keeps its rulings. It settles what 0016 left to "Identity hook: a push refspec it cannot read is
refused" (issue 103): the identity hook reads every commit a push sends, and refuses a refspec it
cannot read. It adds what that issue and "Session hooks: spellings left after the git-options story"
(issue 106) decide about variables. As before, under the working ruling on "Session hooks that
refuse: protected paths, merging, and the repo's own rules" (issue 23): a hook guards against
mistakes, and the Stop check and the rulesets are the boundary.

## Decision

A session hook reads a command's words. These it decides without reading further:

| What | Decided | Because |
|---|---|---|
| A git helper that runs a script, as `core.pager='sh x.sh'` does, or an option such as `grep -O` or `rebase -x` that names one | It is a program like any other. When given by `-c` or an option, `tools/hooks/identity.py` refuses it; given by `-c`, an option or the environment, `tools/hooks/protected.py` asks the person. Only `cat` and `less` pass: by their bare names in the first, and with no option that writes or loads in the second. The settings that name a program are one list, in both hooks | A hook reads words, never a file. The script may be written in the same command, or between the hook's reading and git's running, and nothing a session needs runs a helper from a script given inline |
| The commits `git notes` and `git stash` make | Accepted by `tools/hooks/identity.py` without reading who makes them | They are on no branch, under refs/notes or at refs/stash, so no pull request carries one. Only a push takes one out of the clone, and the hook reads every commit a push sends, as it does a branch's: a mirror push ref by ref, refs/notes and refs/stash among them |
| A protocol allowed in the command (`protocol.*.allow`, GIT_ALLOW_PROTOCOL) or an ext:: URL, and `ssh.variant` | The first are refused by `tools/hooks/identity.py` for every git command. `ssh.variant`, refused until now, is not | The ext:: transport runs the command its URL names, and any command may run a transport: in a partial clone, cat-file, log or checkout fetch a missing object through it. `ssh.variant` says only how git calls ssh, and names no program |
| A push's refspec or remote, a fetch's refspec, a `-C` directory, a `-c` setting or an option held in a variable, or set from a command substitution | Read only when the value is one the hook has read: a variable set by a bare assignment or by export, readonly, declare or typeset, that runs unconditionally at the top level of a plain `;`/newline sequence (inside no compound command's body), exactly once, before any use of it, to a word the shell uses as it stands; or, for a push refspec, the current-branch substitution (`$(git branch --show-current)` and its like) where the push runs. A current-branch variable is that. Anything else the hook cannot read, and refuses (identity) or asks (protected): a variable set in a subshell, a condition, a pipeline, a background, a loop, a group or a function, set more than one way, touched by read, for, getopts, unset, eval, source and the like, by `${X:=v}` or arithmetic, set by a prefix before a special built-in or by `local` (shells differ on whether it persists), a command substitution, or a wildcard. A write to a variable whose name is computed at run time (`printf -v "$N"`, `declare -n`, `${!N:=v}`, `(( $N = 1 ))`) makes every variable unknown. Such a variable still counts as set: an unset ends one only when it runs unconditionally at the top level before any git or gh. A here-document's body is data | What git will send or go to is not in words the shell has yet to expand, and a value the command itself set plainly, once and unconditionally, is as plain as the word. Reading a refspec the hook could not resolve as HEAD let a push carry another person's commit; spelling it plainly costs the session a word |

## Why

Reading a script's file would make a hook's answer depend on a file the command itself can change,
and each new reading is a new spelling to get wrong; refusing costs only a configuration change made
in a command of its own, and what holds is the Stop check and the rulesets. Reading a notes or
stash commit as a commit would refuse a stash whenever the clone's identity is wrong, a mistake that
cannot reach GitHub without a push. A protocol is a policy, not a program, but the one that allows
ext:: lets a URL run one, and the hook cannot tell which command will reach a transport. A variable
is read only where the shell's own order makes its value plain, so that what a hook trusts is what
will run, and everything else is refused rather than guessed.

## Boundaries

| Boundary | Check |
|---|---|
| A helper that runs a script is refused by the identity hook and asked about by the other | `tests/test_hooks.py::test_a_helper_that_runs_a_script_is_a_helper_in_both_hooks` |
| A notes or stash commit passes, and a push that carries one by anyone but the Maintainer is refused | `tests/test_hooks.py::test_a_commit_on_no_branch_is_accepted_and_read_when_it_is_pushed` |
| A protocol allowed is refused for every command, and `ssh.variant` for none | `tests/test_hooks.py::test_a_protocol_allowed_is_refused_for_every_command_and_ssh_s_variant_for_none` |
| The identity hook refuses every setting the protected hook knows to name a program: one list | `tests/test_hooks.py::test_every_helper_setting_the_protected_hook_knows_is_refused` |
| A mirror push reads every ref it sends, refs/stash and refs/notes among them, and a matching refspec reads every branch the remote shares | `tests/test_hooks.py::test_a_mirror_push_reads_every_ref_it_sends`, `tests/test_hooks.py::test_a_matching_refspec_reads_every_branch_the_remote_shares` |
| A push refspec in a variable no earlier command set unconditionally, in a command substitution, or with a wildcard is refused | `tests/test_hooks.py::test_a_push_refspec_the_hook_cannot_read_is_refused` |
| A push refspec in a variable the command set unconditionally to a plain ref is read as that ref, and the branch the shell is on as HEAD | `tests/test_hooks.py::test_a_push_refspec_in_a_variable_the_command_set_is_read`, `tests/test_hooks.py::test_a_branch_variable_from_a_substitution_is_read_as_head` |
| A remote held in a variable is read from what the command set, or refused | `tests/test_hooks.py::test_a_remote_held_in_a_variable_is_read_from_what_the_command_set_or_refused` |
| Only an assignment that runs unconditionally at the top level, once, with a plain value, is trusted; a conditional, subshell, pipeline, function, compound body or repeated one is not | `tests/test_hooks.py::test_only_an_unconditional_top_level_assignment_is_trusted`, `tests/test_hooks.py::test_a_variable_the_command_sets_twice_or_reads_is_not_known`, `tests/test_hooks.py::test_nothing_in_a_compound_body_is_trusted` |
| A prefix assignment persists past its command only before a special built-in or a function, and then with its value unread; an `unset` ends a variable only when it runs unconditionally at the top level before any git or gh | `tests/test_hooks.py::test_a_prefix_assignment_before_a_special_builtin_persists`, `tests/test_hooks.py::test_a_prefix_assignment_applies_only_to_the_command_it_precedes`, `tests/test_hooks.py::test_an_unset_ends_a_variable_only_when_it_surely_runs_first`, `tests/test_hooks.py::test_an_unset_after_a_git_command_does_not_take_back_what_it_ran_with` |
| A variable that may be set anywhere (a condition, a body, `${X:=v}`, arithmetic) counts as set | `tests/test_hooks.py::test_a_name_set_anywhere_it_may_persist_is_present`, `tests/test_hooks.py::test_a_name_exported_in_a_condition_or_a_body_is_still_set`, `tests/test_hooks.py::test_a_default_value_expansion_assigns_its_variable` |
| A here-document's body is data: an assignment or unset in it changes nothing | `tests/test_hooks.py::test_a_here_document_body_is_data_to_the_variable_reader` |
| A variable is read in the order the shell runs it: one used before its assignment is unknown | `tests/test_hooks.py::test_a_variable_is_read_in_the_order_the_shell_runs_it` |
| A write to a variable named at run time makes every variable unknown | `tests/test_hooks.py::test_a_write_to_a_variable_named_at_run_time_makes_every_variable_unknown` |
