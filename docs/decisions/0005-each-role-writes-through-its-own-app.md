# 0005. Each Role writes through its own App; the machine user only approves

Status: accepted. Source: decision 5 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

Every agent writes through a GitHub App of its own Role, with a token minted per Run for one repo
and narrowed to the Effects that Run requests. Reading is shared through one reader App that can
write nothing. Approving reviews are submitted by the machine user, which does nothing else. The
owner account is the Maintainer's alone. The code owners are the org's: the team org-leads, which
holds the Maintainer and the machine user (Maintainer, 2026-10-14). Code ownership therefore does
not stop the Factory approving a change to its own rules. Two things do: `apply` refuses a Role's
change to them unless a person approved it (0004), and until the Factory has an author of its own,
every change is the Maintainer's, read and merged by the Maintainer.

## Why

A Role's permissions should be a ceiling GitHub enforces, not a promise in the Factory's own code.
GitHub does not count an approval from an author or a last pusher, so the approver never pushes.

## Boundaries

| Boundary | Check |
|---|---|
| No approval is attempted where the approver is the author or the last pusher | `tests/test_decide.py::test_approver_is_never_the_author_or_last_pusher` |
| A last pusher that cannot be read, null, empty or not there, makes no approval, admits nothing and takes a queued item out, for the Maintainer; it never excuses a dependency update from the model review. A person's login and an App's bot login are read alike, as names (`trials/P-28.json`, `trials/P-28.app.json`; "Design: where the last pusher and the base are read from (P-28, P-29)", issue 163) | `tests/test_decide.py::test_an_unreadable_last_pusher_lets_nothing_through`, `examples/invalid/facts.an-empty-last-pusher.json` |
| In the simulator, on one seed in nine and under faults, the push that left the head is now and then missing from the branch's activity and the last pusher reads null: that pass approves, enqueues and admits nothing, and a dequeue on it is refused by `apply` once the entry is there | `tests/test_simulator.py::test_the_seeds_read_a_push_missing_from_the_activity` |
| Every actor in the facts has a kind: a person (`human`), a Lens's App (`lens`), any other App (`app`), or the machine user (`machine_user`). One whose kind cannot be read defers for the Maintainer, and takes a queued item out | `tests/test_decide.py::test_an_actor_whose_kind_cannot_be_read_defers`, `examples/invalid/facts.an-actor-without-its-kind.json`, `examples/invalid/facts.an-actor-of-a-kind-the-kernel-does-not-know.json` |
| The machine user is the approver the configuration names, and nobody else is; an agent's or a dependency update's author is an App. Facts that say otherwise cannot be read | `tests/test_decide.py::test_the_approver_or_an_author_bot_read_as_another_kind_cannot_be_read` |
| The port tells a person, a Lens's App, any other App and the machine user apart from GitHub's account type and the configuration, never from a name's spelling | `tests/test_adapters.py::test_the_class_is_the_account_named_or_outside` for the author; a reviewer's, a thread's and a label event's accounts are waiting on `adapters/timeline.py` |
| A person whose login ends in `[bot]` cannot be read: a name's spelling only ever refuses an actor | `tests/test_decide.py::test_a_person_whose_login_is_a_bots_is_unreadable` |
| Only the machine user's approval stands, and only while it has write access | `tests/test_decide.py::test_only_the_approvers_approval_stands` |
| No Role owns or shadows a category of Finding about its own work | `tools/check_authority.py` |
| No workflow names the owner account's token | `tools/check_workflows.py` |
| No commit in this repo is authored or pushed by the machine user | waiting on `controller/reconcile.py` |
| Every permission of an App serves a need that the table of needs maps to it, no write need is held by two Apps, and the reader App holds no write | `tools/check_apps.py` |
| Until a Consumer repo is served (slice 3), each App is installed on named repos only; from then, as decided at that cutover, against UJ-6 | `tools/check_apps.py` |
| Every permitted Effect of every Intent is within the ceiling of that Role's App | waiting on `roles/` |
| The Controller's `checks: write` cannot pass a Lens: a required Lens is read only from its own App, and the status on the item has one name that is no Lens's or its check's | `tests/test_decide.py::test_a_check_from_another_app_is_unreadable_for_its_lens`, `tests/test_tools.py::test_the_status_on_the_item_never_carries_a_required_lens_name` |
| A Lens pinned to GitHub Actions is bound to any Actions job of its check's name, one a pull request adds among them: every check from the Lens's App is read and all must pass, so an extra passing one is harmless, and replacing the real job is a change to `.github/`, which only the Maintainer authors (0004). An upload to code scanning with CodeQL's tool and category, by anyone with `security_events: write`, might replace the CodeQL verdict; a follow-up story pins each Lens to its workflow file | `tests/test_decide.py::test_every_check_a_lens_reports_from_its_own_app_is_read`, `tests/test_decide.py::test_a_check_from_another_workflow_is_unreadable_for_its_lens`; the upload unverified, `sim/grounding.py` |
| Every write by a Factory identity matches a recorded Effect; one that does not raises an alert | waiting on `controller/reconcile.py` |
| No Factory secret is readable by a workflow that runs on a Work item's branch | waiting on `harness/` |
| The code owners file is the org's, word for word | `tests/test_tools.py::test_code_owners_are_the_orgs_word_for_word` |
| A Role's change to the Lifecycle, the authority table, the gate, the brakes or `.github/` is refused unless a person approved it | waiting on `harness/` |
