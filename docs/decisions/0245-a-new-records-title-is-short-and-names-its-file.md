# 0245. A new record's title is short and names its file

Status: accepted. The Solution Architect's ruling of 2026-11-21, relayed by the Factory Builder, on the readability lane's plan, item 5, for "docs: keep new decision record titles short" (issue 1098).

## Decision

| What | Decided | Because |
|---|---|---|
| The title | From this record on, a record's title after `# NNNN. ` is at most 72 characters, counted as characters and with trailing spaces left out | Of the about 230 record file names on 2026-11-21, the median was 95 characters, the longest 154, and 94 were over 100. The table of contents of the records could not be scanned. 72 is the limit decision 0244 sets for a pull request's title |
| The file's name | From this record on, the file is `NNNN-` and the title lowercased, with every character but an ASCII letter (a to z), a digit, a space or a dash dropped, the spaces at either end left out, and then each run of spaces turned to one dash, then .md. A title with no letter or digit names nothing. Dashes in the title are kept as they are. Nothing else names it | A name made from the title cannot drift from it, and a reader of the folder reads the titles |
| Where it starts | `FIRST_SHORT` in `tools/check_context.py`, 245: this record holds to it, and so does every later one, whichever merges first | Records are never edited (`tools/check_decisions.py`), so the records before keep their titles and names |
| What it leaves | Whether a title is plain, and whether it says the decision rather than how it was reached, is the reviewers' judgment | A length and a name can be told without judgment; plainness cannot |

## Why

A record is read by its title, first in the folder's listing and then at its top. Long sentence titles made the listing a wall of text. Starting from the next number keeps every record as it was written and makes each new one short.

## Boundaries

| Boundary | Check |
|---|---|
| A title of 72 characters passes and one of 73 refuses; a file named otherwise than by its title refuses, a capital, a dash for a dropped character and a trailing dash among them; a record below `FIRST_SHORT` keeps a long title and any name; a title that names nothing, dashes alone among them, refuses; a leading space or dropped character leaves no dash; trailing spaces are not counted, and a leading one is; a record past a gap, or padded with zeros, is held by its own number as written | `tests/test_tools.py::test_a_new_records_title_is_short_and_names_its_file`, `tools/check_context.py`, mutant: "a new record's title may be of any length", mutant: "a new record's title of 72 characters refuses", mutant: "a new record's file may be named anything", mutant: "a record before the first short one is held to it", mutant: "the first short record is held to nothing", mutant: "a dropped character leaves a dash", mutant: "a name may keep its capitals", mutant: "the file of a short title is named by the whole first line", mutant: "the first short record is another", mutant: "a title that names nothing passes", mutant: "a title's trailing spaces are counted", mutant: "a name keeps a trailing dash", mutant: "a name keeps a leading dash", mutant: "a title of dashes names something", mutant: "a record padded with zeros is held to nothing", mutant: "a title's leading spaces are not counted", mutant: "adjacent dashes in a title are folded" |
