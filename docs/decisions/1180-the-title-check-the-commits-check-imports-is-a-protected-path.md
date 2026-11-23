# 1180. The title check the commits check imports is a protected path

Status: accepted. 2026-11-23, the Factory Builder, by decision 0240's principle; issue 1090. Extends `docs/decisions/0244-a-pull-requests-title-names-its-area-a-plain-change-and-its-issue.md`.

## Decision

`tools/pr_title.py` joins the protected list in `config/hooks.json`. So does a package at its name, which Python would import in its place. The module is listed at any suffix, as decision 0240 lists its seven checks.

So `apply` refuses a Role's push that changes one, a session is asked before an edit, and every model Lens reads a change to it.

Limits: the title check imports only `adapters/github.py` beyond the standard library, and that stays unprotected, as decision 0240's transport row says.

## Why

`tools/commits_are_the_maintainers.py` imports the title check and folds its answer into the verdict, and it runs from the base. One quiet edit to the title check could so blind a protected check without touching it. Decision 0240 protects any file whose only job is to decide a protected check's verdict; the title check was added after it, so nothing held it.

## Boundaries

| Boundary | Check |
|---|---|
| The title check, at any suffix, is on the protected list, and a Role's push of it is refused | `tests/test_apply.py::test_the_checks_that_hold_a_trust_boundary_are_on_the_repos_own_list`, `config/hooks.json`, mutant: "the title check the commits' check imports is pushed by a Role" |
| A package at the title check's name is on the list too, and a push into it is refused | `tests/test_apply.py::test_the_checks_that_hold_a_trust_boundary_are_on_the_repos_own_list`, `config/hooks.json`, mutant: "a package that shadows tools/pr_title.py is pushed by a Role" |
