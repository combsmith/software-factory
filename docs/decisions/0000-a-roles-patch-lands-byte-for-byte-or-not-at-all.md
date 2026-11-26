# 0000. A Role's patch lands byte for byte or not at all

Status: accepted. 2026-11-25, the Solution Architect; issue 838. Extends decision 0188's residual, "the push's write must land exactly that patch".

## Decision

`guards/patch.py`'s `applied` lands a Role's patch on the files of the admitted commit, byte for byte, or gives one code why nothing lands. Nothing is searched for and nothing is guessed. Its docstring lists the narrower patch it reads, and refuses everything else.

`bundle_unreadable`, `patch_does_not_apply`, `push_not_a_file` and `push_path_collision` are the Role's. `push_tree_unreadable` covers a tree or bytes the port handed over in no shape, or a file the patch reads whose bytes it did not hand over. It is a person's: a Hold, never the Role's attempt nor an environment fault, because the same commit is read the same way again. The guard gives it its own code; the push port's table, `WHOSE`, says whose each code is.

A file may not land where it, or a directory above it, differs from another path the push leaves only by case, canonical form or an ignorable character. Names are folded as macOS folds them: decomposed, case-folded, decomposed again, wherever that is ASCII. The characters dropped are Unicode 13.0's Default_Ignorable_Code_Point ranges (`IGNORABLE`), dropped from both names. One such character with no twin holds nothing.

Limits: Apple's own table is untested. HFS+ drops fewer characters, and one added after Unicode 13.0, such as U+180F, is kept. A tree's empty directory holds no file, so none is lost.

## Why

Decision 0188 left landing exactly the patch to the write. `git apply` is no stand-in for that: it searches for a hunk that is out of place and joins a last line that has no newline. On macOS, two names that fold alike check out as one file, so one file would silently land over another. Refusing every name that holds an ignorable character was rejected, because an emoji name with U+FE0F would then hold every push.

## Boundaries

| Boundary | Check |
|---|---|
| A patch lands the bytes its hunks say, at the place they name, or nothing | `tests/test_guards.py::test_a_patch_lands_the_bytes_it_says_and_no_others`, `guards/patch.py`, mutant: "a last line with no newline lands with one" |
| Nothing that is not a file is written: a link, a submodule, a path under a file | `tests/test_guards.py::test_what_is_no_file_is_never_written`, `guards/patch.py`, mutant: "a link is copied as a file is" |
| No file lands beside a twin by case, canonical form or an ignorable character, in the tree the push leaves | `tests/test_guards.py::test_no_file_lands_beside_another_that_differs_by_case_alone`, `guards/patch.py`, mutant: "a character macOS passes over is kept in a name" |
| A name folds as decomposed, case-folded and decomposed again wherever that is ASCII, with Unicode 13.0's ignorable ranges dropped | `tests/test_guards.py::test_a_name_is_folded_as_macos_folds_it_wherever_that_is_ascii`, `guards/patch.py`, mutant: "only the first character of each ignorable range is passed over" |
| A port's read in no shape, or bytes not handed over, are refused under their own code, never one of the Role's | `tests/test_guards.py::test_what_a_port_did_not_read_is_refused_under_its_own_code`, `guards/patch.py`, mutant: "a person's code is one of the Role's" |
| What it lands is what git lands, on fixed seeds, of a patch as git writes it and of that patch broken | `tests/test_guards.py::test_a_patch_as_git_writes_it_lands_what_git_would`, `guards/patch.py`, mutant: "every file lands as a plain one, whatever its mode" |
