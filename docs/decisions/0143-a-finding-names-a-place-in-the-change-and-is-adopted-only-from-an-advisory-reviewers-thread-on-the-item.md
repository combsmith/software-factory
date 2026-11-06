# 0143. A Finding names a place in the change, and is adopted only from an advisory reviewer's thread on the item

Status: accepted. The Factory Builder's ruling of 2026-11-05 on the harness review's story that a Finding's place and its adoption are held to the item. It adds to decision 0038's row "A raised Finding's path and an adopted surface's key admit no space and no control character" a bound on each and a check of each against the facts, and to the reasons `apply` refuses a Result three more. Nothing else in 0038 changes.

## Decision

| What | Decided | Because |
|---|---|---|
| A Finding's place | `apply` refuses a Result that posts a Finding whose `location.path` is not the path of a file the change holds, as `facts.changed_paths` names it: the head's side, so a renamed file by its new name, never its old, and a deleted file by the name the facts give it. The reason is `finding_not_on_change`, the Role's (`item`). `result/1` bounds the path to 4096 characters | A Finding names a place in the change: a place outside it is no Finding of this review. A review comment or an annotation is placed on the head's lines, and a fault a deletion causes sits on the changed lines of another file, which the change holds |
| An adopted Finding's reviewer | `apply` refuses a Result whose Finding is adopted from a reviewer `config/harness.json` does not name in `advisory`, as `adopted_lens_not_advisory`, the Role's. `result/1` bounds the name to 64 characters | Adoption is how a reviewer that writes its findings as prose gets them typed (design §3.7), and the configuration names who those reviewers are; no other name is one |
| An adopted Finding's surface | `apply` refuses a Result whose Finding is adopted from a surface other than a thread on this item that the adopted reviewer opened, as the facts show it, as `adopted_surface_not_on_item`, the Role's. An alert, an annotation, a check or a role is refused, since the facts read none of them yet. `result/1` bounds the key to 64 characters | A surface the facts cannot show on this item is no Finding of this review. The other surface types open when the facts read them, each under a record of its own |

## Why

A raised Finding's path and an adopted surface's key were held only to having no space and no control character, and the reviewer's name to a pattern, with no bound on any. `apply` posted the path as given and copied the adoption into the applied artifact, and checked neither against the item. Each now has to name something the facts show on this item, so a Result can point only at the change it reviews and at what that change's reviewers said on it. The bounds hold the schema the CLI is handed to the same shape before `apply` reads it.

## Boundaries

| Boundary | Check |
|---|---|
| A Finding on a path the change holds is posted, a renamed file's by its new name and a deleted file's by its own; one on a path outside the change, a renamed file's old name, a part or an extension of a changed path, or a path with a leading slash or a trailing space is refused; a Finding adopted from a reviewer not named advisory, from a surface other than a thread, from a thread not on the item, or from a thread another opened, a person of the reviewer's name among them, is refused; one not adopted needs no thread; `result/1` takes a path of 4096 characters and a name and a key of 64, and refuses one more | `tests/test_apply.py::test_a_finding_names_a_place_in_the_change_and_is_adopted_only_from_an_advisory_thread_on_it` |
| The apply step hands `apply` the reviewers the configuration names advisory | `tests/test_steps.py::test_apply_reads_with_reads` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
