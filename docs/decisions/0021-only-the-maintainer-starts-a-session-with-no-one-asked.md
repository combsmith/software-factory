# 0021. Only the Maintainer starts a session with no one asked

Status: accepted. Decided after a review of pull request 115,
"Session hooks: under bypassPermissions, the protected hook tells and asks nothing", found that a
session the Maintainer did not set to bypassPermissions could start one that is, by a command the
protected hook did not ask about.

## Decision

`tools/hooks/protected.py` asks about a command that runs Claude Code with no one asked. Claude Code
runs when the program is one that `config/hooks.json` names under `sessions`, by its name, its path
or its package. The program is read as the shell reads it: with what the hook knows put in for each
variable, a value split into words; past a prefix and its options (`exec -a NAME`); past a wrapper,
xargs, or npx and its like, whose first program it is; inside a command string (`sh -c`, `env -S`,
`npx -c`, eval); as `$(which claude)` or a variable set to it; or as an alias or a function the
command defines that runs it. Such a command is asked about when Claude Code is given:

- a word `config/hooks.json` lists under `sessions` (`--dangerously-skip-permissions`,
  `--allow-dangerously-skip-permissions`, `bypassPermissions`), read as text in each word it is
  given, and as JSON when the word is JSON, so `--permission-mode` and settings written inline are
  read;
- a word the hook cannot read, or words a feeder such as xargs gives it;
- a settings file, which the hook does not read;
- or when a variable listed there, which says where it reads its settings (CLAUDE_CONFIG_DIR,
  HOME), is set anywhere in the command, a script or a subshell among them.

A program the hook cannot read, in a command that names Claude Code, is asked about too, since it may
be Claude Code: a variable it cannot read, or eval of one. A word given to any other program is data, a here-document's body among them: a commit message, a
search, a pull request's body or a test's name that names one of these words starts nothing. Under
bypassPermissions this reason, like every other, is told and not asked (decision 0019).

## Why

Decision 0019 tells rather than asks only because a session under bypassPermissions is one the
Maintainer set to run without them. A session in any other mode could start one that is, and that
session's edits to the Maintainer's paths and its pushes would be told to nobody who reads them.
Asking about the start keeps that choice the Maintainer's. Asking about every command that only
names a word, as the first reading of this did, asked about commit messages and searches; reading
only what Claude Code is given asks about the start and nothing else. What the hook cannot read,
a word, a file or a configuration directory, it asks about, as it does everywhere.

## Boundaries

| Boundary | Check |
|---|---|
| Claude Code given a listed word asks, however it is run: by name or path, a wrapper, npx and its like, a shell's script, `$(which claude)`, an alias or a function, the word in a variable or inline settings | `tests/test_hooks.py::test_a_command_that_runs_claude_code_with_no_one_asked_asks` |
| Claude Code given a word the hook cannot read, a feeder's words or a settings file asks; so does one run with a listed variable set anywhere in the command, or a program the hook cannot read where Claude Code is named | `tests/test_hooks.py::test_claude_code_given_what_the_hook_cannot_read_asks` |
| A word given to any other program, a here-document's body among them, or past the first program a wrapper runs, is not asked about | `tests/test_hooks.py::test_a_word_given_to_any_other_program_is_data` |
| Under bypassPermissions it is told with the code and sentence it would be asked with | `tests/test_hooks.py::test_under_bypass_permissions_every_reason_is_told_as_it_would_be_asked` |
