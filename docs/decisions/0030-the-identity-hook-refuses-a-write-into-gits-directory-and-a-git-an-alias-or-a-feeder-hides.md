# 0030. The identity hook refuses a write into git's directory, and a git an alias or a feeder hides

Status: accepted. It adds to `docs/decisions/0024-the-identity-hook-reads-where-a-push-goes-from-gits-configuration-and-refuses-a-git-the-command-may-redefine.md`,
which stays in force. It settles "Identity hook: spellings left after the push-reading story" (issue 148), whose
spellings the security pass on "Identity hook: a push with no refspec, and git redefined in the command" (issue 111)
found. As before, under the working ruling on "Session hooks that refuse: protected paths, merging, and the repo's own
rules" (issue 23): a hook guards against mistakes, and the Stop check and the rulesets are the boundary. Every reading
here reads the words the shell runs, and paths as whole words, never prose.

## Decision

| What | Decided | Because |
|---|---|---|
| A write into git's directory: its configuration from inside it (`cd .git` then `>> config`), `config.worktree`, or a hook (`cp x .git/hooks/pre-push`), in a command that commits or pushes | Refused by `tools/hooks/identity.py` (`git_directory_written`): a redirection that writes, or a word given to a program not on `TEXT_ONLY`, whose path has a `.git` component, as written or once resolved against the directory the hook tracks through cd, `..` and links taken out, in any case. An option's value after `=` is read too. A word is a path only from its start or a `/`, and a word with a space in it is prose, so "a write to .git/hooks" in a commit message is none; a reader (`cat .git/HEAD`) passes. A target the hook cannot expand, as `"$(git rev-parse --git-path hooks)/x"`, is left to the boundary, so that `git push > "$TMPDIR/log"` passes. This takes from 0024's "Left to the Stop check and the rulesets" a hook written in the same command; one configured earlier stays there | What git runs, and where a push goes, are read from git's configuration and its directory before the command runs. A write in the same command changes them after the hook has read them; making it in a command of its own costs one line |
| An alias whose value runs git or gh | One the hook cannot read, as 0024 reads a function or an alias for git: a name whose value holds a word of `REDEFINABLE` (`alias g=git`, `alias p='git push'`, zsh's `aliases[g]=git`), or a value the hook cannot read, which expands a variable or a command, is refused in a command that commits or pushes (`command_unreadable`). The value is read as the words the shell runs, by `shell.aliased`, in the command's text and in each script it runs; zsh's table only where an assignment stands. A function's body was already read in place | zsh expands an alias in a shell that is not interactive, so `g push` on a later line is a push the hook would read as a program named g |
| git under a wrapper that feeds it its input (`xargs`, `parallel`, `shell.FEEDERS`), given no command | `git_command_unknown`, refused whatever the command does, as an unknown command is. `xargs git add` and a plain `git --version` pass | `xargs git` given `push` on its input runs a command the words do not show |
| A loop's word list, and a case's word and patterns | Data: only what the body runs is read, as a command of its own. Before this, a read-only `for` loop that ran `git show` over file names holding "git" and "commit" was refused as a commit | A word a loop runs over is never a program |
| A gh alias (`gh alias set p 'pr create'; gh p`), or a gh extension | Left to the Stop check and the rulesets. An unknown gh command is not refused | An alias changes no account: gh writes with its token, and `gh p` only skips the account check every gh call already makes. Refusing an unknown gh command needs a list of gh's commands, which each release makes stale, refusing its new read-only ones |

After the one fix round of this story, a new spelling of the first three is answered on the pull request and closed
to the boundary, not filed.

## Why

Each of the issue's spellings is one case of a general one: a write that changes what the hook read, a name that runs
git under another word, a git whose command is not in the words. Reading each generally closes the group at once.
Reading more words has refused commit messages before, so each reading takes paths as whole words and prose as data,
and each rule has must-pass cases that spell it out in a commit message, a pull request's body, grep and echo.

## Boundaries

| Boundary | Check |
|---|---|
| A write into git's directory, by a redirection or a word given to a program that is not a reader, resolved through cd and links, is refused where the command commits or pushes; prose, a reader and a write in a command of its own pass | `tests/test_hooks.py::test_a_write_into_gits_directory_is_refused_where_the_command_commits_or_pushes` |
| An alias whose value runs git or gh, or one the hook cannot read, is refused; prose about one, and an alias that runs neither, pass | `tests/test_hooks.py::test_an_alias_whose_value_runs_git_or_gh_is_refused` |
| git given no command by xargs or parallel is refused; a verb in the words, and prose about it, pass | `tests/test_hooks.py::test_a_git_fed_its_command_by_xargs_is_refused` |
| A loop's word list is data, and its body is read | `tests/test_hooks.py::test_a_loops_word_list_is_data_and_its_body_is_read` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
