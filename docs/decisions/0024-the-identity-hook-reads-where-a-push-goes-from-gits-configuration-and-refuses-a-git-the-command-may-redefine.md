# 0024. The identity hook reads where a push goes from git's configuration, and refuses a git the command may redefine

Status: accepted. It adds to `docs/decisions/0017-the-session-hooks-read-every-commit-a-push-sends.md`, which
stays in force. It settles "Identity hook: a push with no refspec, and git redefined in the command" (issue 111).
As before, under the working ruling on "Session hooks that refuse: protected paths, merging, and the repo's own
rules" (issue 23): a hook guards against mistakes, and the Stop check and the rulesets are the boundary.

## Decision

| What | Decided | Because |
|---|---|---|
| A push that names no refspec, or no remote | `tools/hooks/identity.py` reads git's configuration once, by `push_configuration`, which `tools/hooks/protected.py` calls too, each hook with its own way of running git. It reads every remote's keys, not only those of the remote git would pick. A remote.*.mirror that is true is read as `--mirror`; each remote.*.push is read as a refspec the command gives, so a wildcard or a negative one refuses; and push.default as well, since a remote with no remote.*.push follows it: `matching` reads every branch, and unset, `simple`, `current`, `upstream`, `tracking` and `nothing` read HEAD. Any other value, or configuration git cannot give, refuses. Where a push that names no remote goes is read in the same call, as git picks it: the current branch's pushRemote, then remote.pushDefault, then the current branch's remote, then origin. A value that is not a configured remote refuses; another branch's says nothing of this push. `.` is this repository, so a push to it, named or configured (`git branch -u main`), writes nothing to GitHub and is not read. The hook does not run `git push --dry-run` | git's own answer covers includes, scopes and worktrees. A superset costs a rare refusal; a guess let a push carry another person's commit. A dry run in a hook reaches the network and the credential helper |
| Where a push goes, given in the command | Refused by the identity hook in a command that commits or pushes, by `-c` or `--config-env`, as `remote.*` is through its KEYS: push.*, remote.pushDefault, remote.*.push, remote.*.mirror and branch.*.merge, remote and pushRemote. One list, `PUSH_KEYS` in `tools/hooks/identity.py`, for both hooks: the protected hook asks of the same | The hook reads what is configured; setting it in a command of its own costs one line |
| A git the command may redefine | One the identity hook cannot read: in a command that commits, pushes or names a write, it refuses (`command_unreadable`) when the command defines a function or an alias for git, gh, a word that runs them or which, type and whence, in its text or in a script it runs (sh -c, eval, a substitution), its name read however it is quoted, every name zsh's function takes, zsh's tables and a hashed path among them; sets PATH, anywhere or for git alone, read from the words the shell runs as it expands them and never from quoted data, or writes a variable it names at run time; names git or gh, or a wrapper, by a path that is not the file on the hook's PATH; or runs git or gh under a prefix or a wrapper not on `AS_IS` in `tools/hooks/shell.py`: env with assignments only (and `--`), nice, nohup, timeout, stdbuf, caffeinate, time, and command without an option. git is the program only in command position, past the prefixes and wrappers that file reads; any other program runs itself, so `gitleaks git .` runs no git. So sudo, exec, env -i, env -C and xargs refuse. A program held in a variable or a command the hook cannot read is refused when it is given a commit or a push. `$(which git)` and its like, for a plain name or path, are read as the git on PATH; any other is the substitution it is. The definitions, aliases, wrappers, `$(which ...)` and variables are read by `tools/hooks/shell.py` for both hooks, as the protected hook read them for decision 0021 | The issue's spelling is one case of a general one, and a list allows what is named |
| Left to the Stop check and the rulesets | A git redefined outside the command (the profile, Claude Code's shell snapshot), configuration changed between the hook's reading and the push, and a pre-push hook already configured | The hook reads words and git's configuration, never the shell's state |

## Why

Before this, a push that named no refspec was read as HEAD whatever git's configuration said, so
`push.default=matching` or a remote.*.push could carry another person's commit past the hook; and a
command could define its own `git` and run the real one by `command git`, so that what the hook read
as HEAD was not what ran. Each was read by spelling. Reading git's configuration with git, and
allowing only the wrappers that are named, closes each group of spellings at once, and a session
pays for it only when it sets PATH, or a push setting, in the same command as a commit or a push.

## Boundaries

| Boundary | Check |
|---|---|
| A push that names no refspec reads what git would push: a mirror, every remote's remote.*.push, push.default, and where one that names no remote goes; any value it cannot read refuses | `tests/test_hooks.py::test_a_push_with_no_refspec_reads_what_git_would_push` |
| A push setting given in a command that commits or pushes is refused, and the protected hook asks of the same list | `tests/test_hooks.py::test_push_settings_given_in_the_command_are_refused` |
| The protected hook asks about a push that names no branch on the same reading of git's configuration | `tests/test_hooks.py::test_a_push_naming_no_branch_asks_unless_where_it_goes_is_read_exactly` |
| A function, an alias, PATH, a path or a wrapper that may make git another program is refused where the command writes; the wrappers on the list, and a function of another name, pass | `tests/test_hooks.py::test_a_git_the_command_may_redefine_is_refused` |
| A shell's attached option value (`-oemacs`, `+oemacs`, `-Oextglob`) is a value, never a bundle holding `-c`, so the script named after it is one the hook cannot see; `-o` and `-O` alone, and bash's `--rcfile` and `--init-file`, take the next word, so a `-c` there is a value too | `tests/test_hooks.py::test_four_more_ways_to_redefine_git_are_refused` |
| A name given to `autoload` or `functions`, or to `typeset` or `declare` with `-f`, is one the command defines, read as a function's name is, past the prefixes the hook steps over (command, builtin, exec, nohup, time); zsh's `noglob` and `nocorrect` are not among them, a case left to the boundary, and a name spelt through an expansion is out of scope as decision 0032 says | `tests/test_hooks.py::test_four_more_ways_to_redefine_git_are_refused` |
| A dynamic linker's variable set anywhere in a command that writes is read as PATH is: `LD_PRELOAD`, `LD_LIBRARY_PATH`, `LD_AUDIT`, `DYLD_INSERT_LIBRARIES`, `DYLD_LIBRARY_PATH`, `DYLD_FRAMEWORK_PATH`, `DYLD_FALLBACK_LIBRARY_PATH` and `DYLD_FALLBACK_FRAMEWORK_PATH`, a closed list; any other variable is left alone | `tests/test_hooks.py::test_four_more_ways_to_redefine_git_are_refused` |
| A definition on the line after a comment holding an apostrophe is read, since the comment is dropped from a script's text as from its words, where a `#` begins a word | `tests/test_hooks.py::test_four_more_ways_to_redefine_git_are_refused` |
| printf sets only the name `-v NAME` or `-vNAME` gives it, its subscript taken off; every other word it is given is text, so a message that spells `PATH=` sets nothing | `tests/test_hooks.py::test_four_more_ways_to_redefine_git_are_refused` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
