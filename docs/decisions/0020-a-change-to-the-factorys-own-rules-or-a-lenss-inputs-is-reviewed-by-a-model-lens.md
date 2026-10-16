# 0020. A change to the Factory's own rules or a Lens's inputs is reviewed by a model Lens

Status: accepted. The working rulings on issue 113,
"Kernel: a change to the Factory's own rules or a Lens's inputs needs a person",
with rule 3 decided by the Maintainer on 2026-10-16: no person is needed, and no push of one's own is
excused. It decides one row of decision 0018 otherwise: the row on a Role's change to a Lens's own
workflow file, and a change to a Lens's inputs, which it said needs a person. Under this decision no
person is needed: every model Lens's review of the change's head is.

## Decision

The facts carry `changed_paths`: one record for each file the pull request changes, each by its own
path once, from the top of the repo, with `previous`, the path a renamed or copied file had before,
or null. Every path and every previous one is matched against the list. Whether the list was
read in full is `complete.changed_paths`, read with the other flags: a list read short defers as
incomplete facts, and a queued item leaves the queue. A list read in full that is no list of text, or
holds a path one of whose names is empty, `.` or `..`, is unreadable: the Kernel defers for the
Maintainer, `paths_unreadable`, read where an unreadable review is, and a queued item leaves the
queue. So is a record not in that shape, and a list of more or fewer records than the diff has
files: such a list left a file out or misread one, whatever it says.

The Factory's own rules and the inputs of each deterministic Lens are one list, in
`config/hooks.json`: `protected`, which gains `config/apps.json`, and `lens_inputs`, each with the
Lens that reads it. verify reads what make reads (`GNUmakefile`, `makefile` or `Makefile`), every
place checks live, the Kernel the tests import, and whatever `python3 -m` imports from the top of
the repo before the standard library: a module, source, compiled or an extension, a regular package's
`__init__`, and the compiled modules in `__pycache__`, at the top or in a package there; and every package
at the top of the repo whole (`kernel/`, `sim/`, `tests/`, `tools/`). A directory with no `__init__` is a namespace package, which a module
found later on the path wins over, so it is not listed; the secret scan reads `.gitleaks.toml` and
`.gitleaksignore`. The session hooks ask about a protected path, and report a Lens's input as they
report what is listed at a stop. The Kernel is given the patterns of both as `protected_paths`, from
one function beside the hooks' own reader, in one syntax: a final `/` names a directory and all
below it, `*` any part of one name, and case is not compared, so the list holds more, never less.

The list is the Kernel's configuration, never the change's: the Controller builds `protected_paths`
from `config/hooks.json` as the base branch holds it, never as the pull request's head does, so a
change cannot take itself off the list. A list the Kernel is given that is not a list of patterns,
or is empty, or holds a pattern that could match nothing (an empty, `.` or `..` name, or a leading
`/`), defers for the Maintainer, `protected_paths_unreadable`, read before the paths it
judges, and a queued item leaves the queue.

A pull request that changes a path on the list converges only once every model Lens has reviewed its
current head, whatever its class. A dependency update is no exception: the class that otherwise needs
no model review needs it here. The machine user then approves it, as it approves every item: a
session pushing as the Maintainer never approves its own change, since the approval comes from
another account, and the machine user never pushes. There is no new approval, no new Hold and no
exception for a push of one's own. An item whose review of this head is missing waits for it as any
item does, and the wait names each pattern on the list that the change matched, never a path. A
queued item that changes the list is never read past a review of its head that it lacks.

## Why

The gap was a change judged by nothing but the Lens it edits. A dependency bot's security update
edits the pins in workflow files, and as class `dependency` had no model review: the verify Lens it
edits was its only judge, and GitHub runs the edited job from the path the Lens is pinned to
(decision 0018). A same-repo pull request could do the same to the Makefile, the checks and the
tests that verify runs. A review by another model, bound to the content, closes it without stopping
each change for a person; the load is small, since every class but a dependency update already needs
that review.

One list, read by both, leaves only the two matchers to drift, and a test holds them to each other.
A path is text from outside, so a Decision names the configuration's pattern instead. A queued item is
read past a missing review because GitHub read nothing of it on the way in and it was approved only
after one; a change to the list is not, so that an approval given before this rule, or before a path
joined the list, does not merge an unreviewed change to the rules.

What GitHub holds is still the Maintainer's: the `main` ruleset requires no review, so it accepts
whatever the Kernel enqueues. Requiring the machine user's approval of the latest push for a change
to a protected path is
"Ruleset: a change to a protected path needs the machine user's approval of the latest push",
with issue 62, "The Factory repo's rulesets hold the Release tags and each required check's App".
A deterministic Lens still runs from the change's own inputs; run from the base's, a change could
not weaken the Lens that judges it, and that story comes next.

## Boundaries

| Boundary | Check |
|---|---|
| A dependency update that changes a protected path waits for every model Lens's review of its head, and converges once it has one; one that changes nothing on the list does not | `tests/test_decide.py::test_a_change_to_a_protected_path_needs_the_model_review` |
| A Lens's input counts as a protected path does: below a directory however deep, and never a name that only starts with one | `tests/test_decide.py::test_a_lens_input_counts_like_a_protected_path` |
| `*` stands for any part of one name, none included, never across a `/`; case is not compared; the pieces between stars are found in order and never overlap | `tests/test_decide.py::test_a_pattern_matches_one_name_per_star_in_any_case`, `tests/test_decide.py::test_a_pattern_of_several_stars_matches_each_piece_in_order_once` |
| A package at the top of the repo, which verify imports before the standard library, is a Lens's input; a directory there with no `__init__` is not | `tests/test_decide.py::test_a_package_at_the_top_of_the_repo_counts_as_a_lens_input` |
| Every package at the top of the repo is a Lens's input whole: each of its modules and its cached bytecode | `tests/test_decide.py::test_a_module_of_a_package_at_the_top_of_the_repo_counts_as_a_lens_input`, `tests/test_tools.py::test_every_package_at_the_top_of_the_repo_is_a_lens_input_whole` |
| Either name of a rename or a copy counts | `tests/test_decide.py::test_either_name_of_a_rename_counts` |
| A dependency bot's update to a workflow's pin is reviewed by the model Lens before the machine user approves it, and what that review raises gates it | `tests/test_decide.py::test_a_dependency_update_to_a_workflow_pin_needs_the_model_review` |
| A queued change to the list whose head moved, or whose approval of this head came with no review of it, leaves the queue and waits for the review | `tests/test_decide.py::test_a_queued_change_to_the_list_whose_head_moves_leaves_the_queue` |
| A list of paths read short defers as incomplete facts, and takes a queued item out | `tests/test_decide.py::test_changed_paths_read_short_defer`, `examples/invalid/facts.no-completeness-for-changed-paths.json` |
| A list that is no list of text, or a path with an empty, `.` or `..` name, defers for the Maintainer, after what needs no paths, and takes a queued item out | `tests/test_decide.py::test_an_unreadable_changed_path_defers_for_the_maintainer` |
| A list of more or fewer records than the diff has files, or a path given twice, defers for the Maintainer, and takes a queued item out; a rename's record carries its previous path | `tests/test_decide.py::test_a_list_of_paths_with_a_record_for_each_file_and_no_other`, `examples/invalid/facts.a-changed-file-without-its-previous-path.json` |
| A list of protected paths that is empty, not there, or holds a pattern that could match nothing defers for the Maintainer, and takes a queued item out; a pattern named twice is named once | `tests/test_decide.py::test_an_unreadable_list_of_protected_paths_defers_for_the_maintainer` |
| The Controller builds `protected_paths` from the base branch's `config/hooks.json`, never the head's | waiting on `controller/` |
| A Role's change to a Lens's own workflow file, a change under `.github/`, or anyone's change to a Lens's inputs needs no person: it converges once every model Lens has reviewed its head, and the machine user approves it (decision 0018's row, decided otherwise) | `tests/test_decide.py::test_a_lens_input_counts_like_a_protected_path`, `tests/test_decide.py::test_a_dependency_update_to_a_workflow_pin_needs_the_model_review` |
| A Decision names each pattern of the configuration that matched, in its order, never a path | `tests/test_decide.py::test_a_decision_names_the_pattern_never_the_path` |
| The Kernel's matcher and the session hooks' agree on every file in the repo and on paths made from each pattern | `tests/test_tools.py::test_the_kernels_matcher_and_the_hooks_agree_on_one_corpus` |
| The Kernel is given every protected path and every Lens's input, from `config/hooks.json`, in the tests and the simulator alike | `tests/test_tools.py::test_the_kernel_is_given_every_protected_path_and_lens_input` |
| Each Lens's input names a required deterministic Lens; verify's cover what make reads, every place checks live, the Kernel, and a module, a package or a compiled module at the top of the repo by every suffix the import system knows, and the secret scan's its configuration and its ignore file | `tests/test_tools.py::test_each_lens_input_is_a_required_lens_and_verifys_cover_every_check`, `examples/invalid/hooks.a-lens-input-with-no-lens.json` |
| The workflow file each Lens is read from is a protected path | `tests/test_tools.py::test_each_lens_workflow_file_is_protected` |
| The session hooks ask about `config/apps.json`, and list a Lens's input at a stop without asking about it | `tests/test_hooks.py::test_an_edit_elsewhere_is_not_asked_about`, `tests/test_hooks.py::test_a_lens_input_changed_is_listed_as_reported` |
| In the simulator a Role, the dependency bot and the Maintainer change the list, the list is read short or leaves a path out, and nothing that changes it is approved, enqueued, left queued or merged without every model Lens's review of that head (I-45) | `tests/test_simulator.py::test_the_seeds_change_the_list_by_a_role_the_dependency_bot_and_the_maintainer` |
| The port reads every path the pull request changes, both names of a rename among them, and says when the list was cut short. "Port: the paths a pull request changes, and both names of a rename" | waiting on `adapters/` |
| `apply` refuses a Role's push to a protected path or a Lens's input that no model Lens has reviewed. "Harness: apply refuses a push to the list that no model Lens has reviewed" | waiting on `harness/` |
