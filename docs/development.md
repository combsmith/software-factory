# Development practices

How a change to this repo is made, from a branch to a merge. The table lists the practices a check
holds. The sections after it are advice that no check holds. A practice that gains a check moves up into
the table in the same pull request as the check.

How code, tests and workflows are written is in `docs/standards/`, and the Kernel's own steps and the
desk's commands are in `AGENTS.md`. This page does not repeat them.

## Held by a check

| Practice | Held by |
|---|---|
| A change merges only once the required check, `factory / verify`, passes, and it fails unless every job it needs passed: `make verify` and the commits job on the pull request and the merge group, and every mutant shard on the merge group | `tests/test_tools.py::test_this_repos_rulesets_agree_with_its_lenses`, `tests/test_tools.py::test_the_required_check_fails_unless_every_job_it_needs_passed`, `tests/test_tools.py::test_on_a_pull_request_the_mutants_decline_and_on_a_merge_group_every_shard_runs` |
| Every commit a pull request carries names the Maintainer, and an account `config/hooks.json` lists opened it from this repo | `tests/test_tools.py::test_every_commit_a_pull_request_carries_is_the_maintainers`, `tests/test_tools.py::test_the_job_refuses_for_the_commits_or_the_opener_and_says_what_it_holds` |
| A diff over `max_diff_lines` (4000) or `max_diff_characters` (60000) in `config/defaults.json`, or one GitHub cuts short, is held, `too_large`, and never reviewed in part. Split such a change into parts | `tests/test_decide.py::test_truncated_or_oversized_diff_is_held_without_a_run`, `tests/test_decide.py::test_a_diff_no_task_can_carry_whole_is_held_and_one_at_the_bound_is_reviewed` |
| A change to a model Lens's own inputs, the paths under `lens_inputs` in `config/hooks.json` whose Lens is a model Lens and those under `person_only`, waits after the model review for a standing approval of its current head by a person with write access other than its author and its last pusher. The machine user's approval never counts (`docs/decisions/0052-a-change-to-a-model-lenss-own-inputs-needs-a-different-persons-approval.md`) | `tests/test_decide.py::test_a_change_to_a_model_lenss_own_input_waits_for_a_person`, `tests/test_decide.py::test_the_maintainers_own_change_waits_for_another_judge`, `tests/test_decide.py::test_the_machine_users_approval_never_judges_a_change_to_a_model_lenss_input`, `tests/test_decide.py::test_a_persons_approval_of_the_current_head_lets_it_converge` |
| A person's review thread counts as open until that person resolves it, whoever else resolves it, so leave it for them (`docs/decisions/0014-where-this-repo-departs-from-the-orgs-standards.md`) | `tests/test_decide.py::test_a_persons_thread_resolved_by_anyone_but_that_person_stays_open` |
| A session asks the person before it edits a protected path, one under `protected` in `config/hooks.json`. In bypass mode the hook tells the session instead and asks nothing (`docs/decisions/0019-under-bypass-permissions-the-protected-hook-tells-and-asks-nothing.md`). The hook guards against mistakes; the required check, the approving review and the rulesets are the boundary | `tests/test_hooks.py::test_from_the_front_door_an_edit_to_a_protected_path_asks_and_a_clean_one_is_silent`, `tests/test_hooks.py::test_under_bypass_permissions_the_hook_tells_the_session_and_asks_nothing` |
| A decision record takes the number of the pull request that adds it, and a pull request adds one at most. The commits job, `tools/commits_are_the_maintainers.py`, holds this; `tools/check_context.py` refuses two records of one number. Numbers leave gaps (`docs/decisions/1121-a-decision-record-takes-the-number-of-the-pull-request-that-adds-it.md`) | `tests/test_tools.py::test_each_record_a_pull_request_adds_is_numbered_by_it`, `tests/test_tools.py::test_no_two_records_share_a_number` |
| A decision record and a lesson take the shape `docs/AGENTS.md` gives them | `tests/test_tools.py::test_a_decision_with_no_boundary_is_caught`, `tests/test_tools.py::test_a_lesson_with_no_check_is_caught` |
| From record 1166 on, a record keeps to a budget: a Status of 40 words, a Decision and Why of 300 (450 to replace), Decision tables of 8 rows and 40 words to a cell, and a Boundary of 30 words naming one mutant (`docs/decisions/1166-a-new-record-is-a-short-why-log-held-to-a-word-budget.md`) | `tests/test_tools.py::test_a_new_records_status_is_held_to_its_words`, `tests/test_tools.py::test_a_new_records_decision_and_why_are_held_to_their_words`, `tests/test_tools.py::test_a_new_records_decision_table_is_short`, `tests/test_tools.py::test_a_new_records_boundary_rows_are_short_and_name_one_mutant` |
| A trial's fixture is named for its trial, validates and holds no credential. Each other rule in `trials/AGENTS.md` names its own test there, and the skill `.claude/skills/run-a-platform-trial/SKILL.md` says how a trial is run | `tests/test_tools.py::test_a_fixture_that_is_misnamed_or_invalid_is_caught`, `tests/test_tools.py::test_a_credential_in_a_fixture_is_caught` |
| A pull request whose body was edited after its first approval since a person looked is held until a person approves | `tests/test_decide.py::test_a_description_edited_after_the_approval_holds_until_a_person_approves` |

Advice that follows from the last row, not a check: write a pull request's body in full before its
first review. Once it has been approved, even if that approval was later dismissed, do not edit the
body; close the pull request and open a new one from the same branch, which is reviewed and approved
afresh on its own body, and ask anyone whose thread was still open to look at the new one, and wait for them before it merges. That keeps
the hold rather than getting round it: never edit a body and then reopen to get past a hold that
already stands. The hold is `docs/decisions/0140-the-facts-port-reads-a-pull-requests-description-edits-and-an-edits-absence-is-never-read-as-none.md`,
which replaces 0135, and `docs/decisions/0168-the-simulators-world-dates-an-approval-by-the-acts-run-and-the-kernels-anchor-takes-the-records-always.md`,
which replaces 0158. Only a person releases it.

## Advice no check holds

No check holds these, so they are advice for whoever makes a change, and nothing in this repo
depends on them.

- **Run the desk's two commands in `AGENTS.md`, under Verify, before a change is finished,** as
  `AGENTS.md` asks. No check sees whether they ran at the desk; CI runs the same checks, but a
  failure found at the desk costs a minute rather than a run of CI.
- **Keep the main checkout on `main`, and work in a separate git worktree.** A session runs the main
  checkout's copy of each hook wherever it started
  (`tests/test_hooks.py::test_every_hook_runs_the_main_checkouts_copy_wherever_the_session_started`),
  so a branch checked out there changes the hooks of every session. In bypass mode the protected
  hook asks nothing (`docs/decisions/0019-under-bypass-permissions-the-protected-hook-tells-and-asks-nothing.md`),
  so nothing stops a stray edit there.
- **Title a pull request `area: plain verb phrase (#issue)`,** in at most 72 characters, one change
  per title, and "part N of M" for a part of a split change. The squash commit takes the title, so
  main's log reads the same way.
- **Use `.github/pull_request_template.md` as the outline of the body,** and leave the template
  itself as it is: why, what changed, what to look at, the record and any protected edit, then the
  checks and reviews folded away. A reviewer then finds each thing in the same place.
- **Write a new decision record under a placeholder number, and open its pull request as a draft.**
  The placeholder has four digits that no record holds. Then push one commit that renames the
  record, its title and each mention of its number to the pull request's number, and mark the pull
  request ready. If it is closed and a new one opened from the same branch, rename the record again
  to the new number. In the body, say "the record this pull request adds", never a number.
- **Measure a diff from the diff GitHub serves for the pull request, not from a local one, and leave
  a margin.** The facts port counts it as a Task carries it, each line numbered and the whole escaped
  as JSON, and the Kernel holds that count to the bound (`adapters/pull.py`,
  `docs/decisions/0137-the-review-is-given-each-head-lines-number-and-the-bound-counts-the-diff-numbered.md`).
  The count is longer than the raw text, and much longer for a diff full of quotes and backslashes.
- **Resolve a merge conflict as a three-way merge** of the branch's change with the main you merged,
  never by taking one side whole, and check afterwards that the pull request's diff did not grow by
  deleting lines of main. Taking one side whole can drop another change's tests.
- **In a runner of your own that tries mutants on a copy, leave the copy's `__pycache__` out and run
  it with `PYTHONDONTWRITEBYTECODE=1` set,** so every Python it starts writes none. A stale compiled
  module can report a false survivor or a false kill.
  `tools/mutants.py` guards against this itself (`docs/decisions/0027-a-mutant-is-killed-by-a-test-that-fails-on-it-twice-and-passes-without-it.md`).

## Writing a decision record

A record is a short why-log that points to the code. It is not a spec. From record 1166 on, its
word budget is held by a check, in the table above; the rest of this section is advice. The shape a
check holds is in `docs/AGENTS.md`: the sections, the number,
and that a record is never edited, with the form of a Status that replaces one in `tools/check_decisions.py`.
A title is at most 72 characters and names the file
(`docs/decisions/0245-a-new-records-title-is-short-and-names-its-file.md`).

- **Title.** The rule as one plain sentence.
- **Status.** One line: the date, who ruled, the issue, and the record it replaces or extends.
  Leave out how the ruling reached you.
- **Decision.** Plain sentences, or at most eight short rows. Name the file that holds the exact
  form, and do not copy it. End with "Limits:" and what the check misses.
- **Why.** Two to four sentences: the problem, the evidence, and what was rejected.
- **Boundaries.** Two columns, Boundary and Check. The Boundary is a short phrase for one
  behaviour. The Check names the file, the test as `path::name`, and one mutant that test kills,
  as `mutant: "<its description>"`. One mutant is enough; do not list them all.

Aim for sentences of about 15 words, well inside the budget. The code and its tests
carry the exact rule. A record that copies them goes stale when they change, and then a reader
cannot tell which one is right.
