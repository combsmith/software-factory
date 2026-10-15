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
| No Role owns or shadows a category of Finding about its own work | `tools/check_authority.py` |
| No workflow names the owner account's token | `tools/check_workflows.py` |
| No commit in this repo is authored or pushed by the machine user | waiting on `controller/` |
| Every permission of an App serves a need that the table of needs maps to it, no write need is held by two Apps, and the reader App holds no write | `tools/check_apps.py` |
| Until a Consumer repo is served (slice 3), each App is installed on named repos only; from then, as decided at that cutover, against UJ-6 | `tools/check_apps.py` |
| Every permitted Effect of every Intent is within the ceiling of that Role's App | waiting on `roles/` |
| The Controller's `checks: write` cannot pass a Lens: a required Lens is read only from its own App, and the status on the item has one name that is no Lens's or its check's | `tests/test_decide.py::test_a_check_from_another_app_is_unreadable_for_its_lens`, `tests/test_tools.py::test_the_status_on_the_item_never_carries_a_required_lens_name` |
| A Lens pinned to GitHub Actions is bound to any Actions job of its check's name, one a pull request adds among them: every check from the Lens's App is read and all must pass, so an extra passing one is harmless, and replacing the real job is a change to `.github/`, which only the Maintainer authors (0004). An upload to code scanning with CodeQL's tool and category, by anyone with `security_events: write`, might replace the CodeQL verdict; a follow-up story pins each Lens to its workflow file | `tests/test_decide.py::test_every_check_a_lens_reports_from_its_own_app_is_read`; the upload unverified |
| Every write by a Factory identity matches a recorded Effect; one that does not raises an alert | waiting on `controller/` |
| No Factory secret is readable by a workflow that runs on a Work item's branch | waiting on `harness/` |
| The code owners file is the org's, word for word | `tests/test_tools.py::test_code_owners_are_the_orgs_word_for_word` |
| A Role's change to the Lifecycle, the authority table, the gate, the brakes or `.github/` is refused unless a person approved it | waiting on `harness/` |
