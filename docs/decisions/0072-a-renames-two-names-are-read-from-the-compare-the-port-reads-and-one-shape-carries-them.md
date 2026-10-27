# 0072. A rename's two names are read from the compare the port reads, and one shape carries them

Status: accepted. Taken as working rulings on 2026-10-27, which the Maintainer may overturn in review, for "Port: the paths a pull request changes, with both names of a rename" (issue 138). It grounds what `docs/decisions/0020-a-change-to-the-factorys-own-rules-or-a-lenss-inputs-is-reviewed-by-a-model-lens.md` reads, and names the shape decision 0070, a Role's push refused where it touches the base's list, takes.

## Decision

| What | Decided | Because |
|---|---|---|
| The grounding | `trials/P-43.json` holds, read after the trial and read-only, the compare `adapters/pull.py`'s `changed_paths` reads the files by, "Facts port: the snapshot's diff and files pinned to the head commit, so a head pushed away and back is seen" (issue 284): pull request 48 of the canary, its base commit against its head, with a rename, a copy GitHub lists as added, and an edit. The port reads it whole, the rename with both its names, `{path, previous}`, as the pull request's own list of files names them | Until now a test held only that the fixture had a rename; the port was driven by rows of another trial's shape |
| One source of a rename's two names | A changed path is `{path, previous}`: `previous` the name a renamed or copied file had before, else null. The port gives it so, from GitHub's `previous_filename`, and the Kernel matches both names (0020). The push refusal of decision 0070, not yet on main, takes the same two names as two lists, a push's paths and their previous paths; slice 2's push Effect hands it them | A rule that saw only one name would read a rename out of the list as a new file |
| A list of more files than a compare holds | Read short by the pull request's count alone, as 0020 rules: a compare lists at most 300 files, as GitHub documents it (unverified: no trial records it), and pages its commits, not its files. "Paginated in full" is met as "never read whole unless it holds every file" | No answer GitHub gives for a change of more can be read whole from a compare |

## Why

The issue asked for the port and a fixture that grounds its rename. The port was built to pin the snapshot to its head commit, and its rules
were recorded in decision 0020; the fixture recorded the pull request's list of files, which the port does not read.
The compare it does read is now recorded too.

## Boundaries

| Boundary | Check |
|---|---|
| The compare the port reads gives a rename both its names, and the list is whole, as the pull request's own list names them | `tests/test_adapters.py::test_a_renamed_file_is_read_with_its_old_name_from_a_fixture` |
| The Kernel matches either name of a rename | `tests/test_decide.py::test_either_name_of_a_rename_counts` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
