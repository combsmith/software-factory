# 0032. The identity hook reads a write where and when the shell makes it

Status: accepted. It adds to `docs/decisions/0030-the-identity-hook-refuses-a-write-into-gits-directory-and-a-git-an-alias-or-a-feeder-hides.md`,
whose Decision stays in force. It settles "Identity hook: spellings left after the .git-write story" (issue 160), whose
spellings the reviews of "Identity hook: a write into git's directory, an alias that runs git, and xargs git are
refused" (pull request 156) found, as its working rulings say, which the Maintainer may overturn in review. As before,
under the working ruling on "Session hooks that refuse: protected paths, merging, and the repo's own rules" (issue 23):
a hook guards against mistakes, and the Stop check and the rulesets are the boundary. No new kind of word is read: each
part reads only a path a program of `PATH_WRITERS` writes, or a redirection, in a command that commits or pushes, or the
program an alias names; prose, patterns and a loop's words stay data.

## Decision

| What | Decided | Because |
|---|---|---|
| One rule | A write is resolved where and when the shell makes it, and a reading the hook would cut short is one it cannot read, and is refused | In each spelling a write was resolved in the wrong place or at the wrong moment, or read short |
| A loop's variable over more than `LOOP_MOST` words, in a path a writer is given | `git_directory_written`: the loop is too long to read. The words are not cut short | A path past the cap was never read. Its one false refusal: a commit command whose loop over more than 256 words writes a path holding its variable |
| `popd`, `pushd` with no directory or with +N or -N, and `cd -` or `cd +N` | The hook keeps no stack and does not guess: a relative write, and a commit or a push, are read in every directory the command has stood in, so one that would be in git's directory in any of them is refused, and one in a directory outside a repository cannot be read. A later cd to a plain path is read again | A popped directory is one the command stood in, and a stack is more code for the same answer. Its cost: once a command has stood in `.git`, a relative write after `cd -` is refused |
| A writer whose words name no output | A column of `PATH_WRITERS`: `unzip` with no `-d`, `tar` extracting with no `-C`, `curl -O` or `-J` with no `--output-dir`, `wget` with no `-O` or `-P`, and `patch` with no file or output write where they stand, which is a place written. `-` is the standard output, and no place | `cd .git && unzip x.zip` wrote into git's directory with no path to read |
| A command substitution in a case's pattern | `shell.commands` lists it where the pattern stands, not before every command, so a write in it is resolved after a cd before it. The pattern stays data. `tools/hooks/protected.py` reads the same list, and gains the same | The order is the shell's |
| tar's old-style bundle | A first word with no dash, all letters, is read as tar reads it: each letter an option, and each that takes a value takes the next word in turn, so `tar xfC h.tar .git` is `-x -f h.tar -C .git` and is refused, and `tar cf out.tar .git` reads `.git` as a source and passes. Read as one dashed bundle, `-xfC` would give `C` to `-f`, as getopt does, and miss `.git` | The ruling's note that `_options` already decodes the bundle holds for a dashed bundle only |
| An alias whose value is a feeder, a shell, `source`, `.` or `eval` | Read as its value where its name stands as the program, by `shell.alias_values`: after `alias x=xargs`, `x git` fed `push` is git given no command, and an alias for `sh` fed `git push` is a shell that reads a script the hook cannot see. eval named by an alias is read as such a shell. An alias for git or gh is refused always, as 0030 says | An alias for git was already read; one for what runs git hid it the same way |
| A bracket expression in a path | Read as the shell matches it: a range stays a range (`.gi[s-u]`), a POSIX class is the letters it holds (`.gi[[:alpha:]]`), and a class the hook cannot read, an equivalence class or a collating symbol, or a range it cannot order, may match anything | `-` was escaped, so a range matched only its ends, and a class closed the bracket early |
| A double-quoted command substitution that holds quotes of its own | Read as a script of its own, as the shell does: `git commit -m "$(printf '%s\n' 'echo '"'"'git push'"'"'')"` is one word, and its text is data; a parenthesis a quote of the script's holds does not end it | A printf's text, quoted as a session quotes it, was refused as a command that could not be split. A false refusal is fixed in the story that finds it |
| Left to the Stop check and the rulesets | An archive's own entry names; a directory the hook cannot expand, the shell's own stack and an `OLDPWD` from before the command among them; and a writer the list does not name, such as `python3 -c` | The hook reads words, never a file or the shell's state |

## Why

Each spelling read the right path in the wrong place, or the right words at the wrong moment, or fewer words than the
shell runs. Resolving a write where the shell makes it closes them as one rule, and a reading cut short is refused, as
every reading the hook cannot finish within its budget already is. False refusals stay rare because a part refuses only
a path that resolves into `.git`, which no ordinary command writes beside a commit, and each part has must-pass cases
that spell it out in a commit message by `-m` and `-F`, a pull request's body, grep, echo, and printf into a file and
into a message's substitution.

## Boundaries

| Boundary | Check |
|---|---|
| A loop's variable over more words than the hook reads, in a path a writer is given, is refused; a loop that writes no such path passes | `tests/test_hooks.py::test_a_loop_too_long_to_read_that_writes_through_its_variable_is_refused` |
| After popd, pushd with no directory or ±N, or cd -, a write and a commit are read in every directory the command stood in | `tests/test_hooks.py::test_a_write_after_the_hook_loses_the_directory_is_read_in_every_directory_the_command_stood_in` |
| A writer whose words name no output writes where it stands | `tests/test_hooks.py::test_a_writer_that_names_no_output_writes_where_it_stands` |
| A substitution in a case's pattern runs where the pattern stands, in both hooks | `tests/test_hooks.py::test_a_substitution_in_a_case_pattern_runs_where_the_pattern_stands`, `tests/test_hooks.py::test_a_command_that_writes_a_protected_path_asks` |
| tar's old-style bundle is read as tar reads it | `tests/test_hooks.py::test_tars_old_style_bundle_is_read_as_tar_reads_it` |
| An alias for a feeder, a shell, source or eval is read as its value | `tests/test_hooks.py::test_an_alias_for_a_feeder_a_shell_source_or_eval_is_read_as_its_value` |
| A bracket expression is read as the shell matches it, and one the hook cannot read may match anything | `tests/test_hooks.py::test_a_bracket_expression_is_read_as_the_shell_matches_it` |
| A double-quoted substitution with quotes of its own is one word, read as a script of its own | `tests/test_hooks.py::test_a_substitution_in_double_quotes_is_read_with_quotes_of_its_own` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
