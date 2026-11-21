# Development practices

How a change to this repo is made, from a branch to a merge. The table lists the practices a check
holds. The list after it is advice that no check holds. A practice that gains a check moves up into
the table in the same pull request as the check.

How code, tests and workflows are written is in `docs/standards/`, and the Kernel's own steps are in
`AGENTS.md`. This page does not repeat them.

## Held by a check

| Practice | Held by |
|---|---|
| A change merges only once the required check, `factory / verify`, passes: `make verify` on the pull request and the merge group, and every mutant shard on the merge group. At the desk, run `make checks` and the mutants of the files the change touches | `tools/verify.py`, `tools/needs_passed.py` |
| Every commit a pull request carries names the Maintainer, and an account `config/hooks.json` lists opened it from this repo | `tests/test_tools.py::test_every_commit_a_pull_request_carries_is_the_maintainers`, `tests/test_tools.py::test_the_job_refuses_for_the_commits_or_the_opener_and_says_what_it_holds` |
| A diff over `max_diff_lines` (4000) or `max_diff_characters` (60000) in `config/defaults.json`, or one GitHub cuts short, is held, `too_large`, and never reviewed in part. Split such a change into parts | `tests/test_decide.py::test_truncated_or_oversized_diff_is_held_without_a_run`, `tests/test_decide.py::test_a_diff_no_task_can_carry_whole_is_held_and_one_at_the_bound_is_reviewed` |
| A change to a model Lens's own inputs, the paths under `lens_inputs` in `config/hooks.json`, waits after the model review for the approval of a different person with write access (`docs/decisions/0052-a-change-to-a-model-lenss-own-inputs-needs-a-different-persons-approval.md`) | `tests/test_decide.py::test_a_change_to_a_model_lenss_own_input_waits_for_a_person` |
| A person's review thread is closed by that person; an agent leaves it open (`docs/decisions/0014-where-this-repo-departs-from-the-orgs-standards.md`) | `tests/test_decide.py::test_a_persons_thread_resolved_by_anyone_but_that_person_stays_open` |
| A session asks before it edits a protected path, one under `protected` in `config/hooks.json`, unless it runs in bypass mode | `tests/test_hooks.py::test_from_the_front_door_an_edit_to_a_protected_path_asks_and_a_clean_one_is_silent` |
| A new decision record takes the next number after main's last when its pull request is queued, not when it is written: the merge group checks main with the change, and a gap or a repeat fails there | `tests/test_tools.py::test_a_decision_with_no_boundary_is_caught` |
| A decision record and a lesson take the shape `docs/AGENTS.md` gives them | `tests/test_tools.py::test_a_decision_with_no_boundary_is_caught`, `tests/test_tools.py::test_a_lesson_with_no_check_is_caught` |
| A trial's fixture is made as `.claude/skills/run-a-platform-trial/SKILL.md` says, by the rules of `trials/AGENTS.md` | `tools/check_trials.py` |
| A description edited after the first approval since a person looked holds the item until a person approves | `tests/test_decide.py::test_a_description_edited_after_the_approval_holds_until_a_person_approves` |

So once a pull request has been approved, even if that approval was later dismissed, leave its body
alone, and its title with it: close it and open a new one from the same branch. The hold follows from
`docs/decisions/0135-a-description-edited-after-the-first-approval-since-a-person-looked-holds-the-item.md`
and `docs/decisions/0158-a-machine-users-approval-is-measured-from-the-act-that-read-the-description-and-one-nothing-anchors-holds-an-edit.md`,
and only a person can release it.

## Advice no check holds

No check holds these, so they are advice for whoever makes a change, and nothing in this repo
depends on them.

- **Keep the main checkout on `main`, and work in a separate git worktree.** A session runs the main
  checkout's copy of each hook wherever it started
  (`tests/test_hooks.py::test_every_hook_runs_the_main_checkouts_copy_wherever_the_session_started`),
  so a branch checked out there changes the hooks of every session. In bypass mode the protected
  hook asks nothing (`docs/decisions/0019-under-bypass-permissions-the-protected-hook-tells-and-asks-nothing.md`),
  so nothing stops a stray edit there.
- **Title a pull request `area: plain verb phrase (#issue)`,** in at most 72 characters, with one
  change to a title and "part N of M" for a part of a split change. The squash commit takes the
  title, so main's log reads the same way.
- **Write the body to `.github/pull_request_template.md`:** why, what changed, what to look at, the
  record and any protected edit, then the checks and reviews folded away. A reviewer then finds each
  thing in the same place.
- **Take the size of a diff from the numbered diff GitHub serves for the pull request,** not from a
  local diff. The Kernel counts the diff numbered and escaped as JSON, which is longer than the raw
  text, so leave a margin under the budget.
- **Resolve a merge conflict as a three-way merge** of the branch's change with the main you merged,
  never by taking one side whole, and check afterwards that the pull request's diff did not grow by
  deleting lines of main. Taking one side whole can drop another change's tests.
- **Run a mutant runner that works on a copy with `python3 -B`.** A stale compiled module in the copy
  can report a false survivor or a false kill.
