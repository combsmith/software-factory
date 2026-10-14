# 0014. Where this repo departs from the org's standards

Status: proposed. The Maintainer accepts it by merging it, or strikes a row.

## Decision

This repo follows the org's standards, kept in combsmith/.github and read here at commit
9e2daad, except in the rows below. Every page under `docs/standards/` names the org standard each
of its rules rests on. Where a rule here is stricter than the org's, the stricter one holds and
needs no exception. Org headings are quoted as written, without their code marks.

| The org's rule | Here | Because |
|---|---|---|
| The stages of ci.yml: lint, format, type check and coverage; pytest, never unittest. ci-standards.md, "1. CI Pipeline (ci.yml)"; the org's AGENTS.md, "Pre-Commit Quality Checks" and "Code Quality"; the Python instructions, "Testing (pytest)" | One required check, `factory / verify`: `make verify` and the mutation check, on unittest. No formatter, linter or type checker | Each of those tools is an install, and the required check runs only what is in the commit (0001, 0008). The mutation check stands where a coverage threshold would |
| SonarCloud by the org's workflow. ci-standards.md, "3. SonarCloud Analysis (sonarcloud.yml)" | The org's workflow, written to this repo's workflow rules. It informs; it is not a required check or a required Lens. Coverage is not measured: `sonar-project.properties` excludes every file from it | A Finding from a Lens outside the required set gates only when a required Lens adopts it (0012). Measuring coverage needs an install, and the mutation check stands where a coverage threshold would |
| The agent workflows every repo carries: dev-lead, pr-review-mention, pr-auto-review, persona-mention, initiative-driver, feature-ideation, dependabot-automerge, dependabot-rebase, auto-rebase, add-to-project. ci-standards.md, "Required Workflows" | None of them. No workflow of the proof of concept serves this repo, for any Intent family | The design keeps the proof of concept's author out of this repo, to start it clean; this record extends that to the rest of its fleet. Each of these is woken by an event that carries work (0003), or needs a personal token or every secret or runs on pull_request_target (0004, 0005), or updates or merges a branch past the gate (0007) |
| The code-quality ruleset and its four required checks. github-settings.md, "code-quality — Required Checks Ruleset (All Repositories)" | Not applied until each of the four checks exists here | Applied first, it blocks every pull request |
| A concurrency group on CI. ci-standards.md, "1. CI Pipeline (ci.yml)" | None on the required check | A group evicts a waiting run, which is how work was lost (`docs/lessons.md`, "A request existed only as a queued run") |
| A copilot-instructions file and a setup-steps workflow. copilot-instructions-standard.md, "Creating a Repo-Level copilot-instructions.md" | Neither | A second file that is always loaded is a second copy of the rules (0009, 0013), and there is nothing to set up |
| BMAD installed, with planning documents in its output folder. The org's AGENTS.md, "BMAD Method — Spec-Driven Development" | The design is under `docs/prd/` and `docs/architecture/` | It is installed by a download |
| Agents resolve every review thread, a person's included. The org's AGENTS.md, "Thread Resolution Policy" | A person's thread is closed by that person | An agent resolved the threads that were holding it (`docs/lessons.md`, "The agent resolved the threads that were holding it") |

The org's secret scan is not departed from. It is a security policy, so the rule here gives way:
the scan runs as the org wrote it, in a workflow of its own, the one workflow allowed to download a
program. It is exempt from that rule alone and held to its text by a hash (ruled by the Maintainer).
One line differs: the download is held to HTTPS on redirects too, which the org's own scanner asks for.

CodeQL's default setup runs here as the org asks, and its result is a required Lens. The code
owners file is the org's, copied word for word: the team org-leads owns every path (Maintainer,
2026-10-14). What keeps the Factory from approving a change to its own rules is recorded in 0005.

Taken up later, each with the part that needs it, and not a departure: a Dependabot entry for
workflow actions; the agent-shield and dependency-audit callers, which hold no secret and would
inform and not gate; the pr-quality ruleset; the org's repo settings and labels; and its rule that
no two schedules share a time.

## Why

A departure nobody wrote down is drift, and the org's audit will report it as such. The org's
AGENTS.md says a repo's own rule takes precedence over it. For the files under its standards
folder it asks more: that a departure be recorded there too, by an issue, and not made silently.
That issue has not been filed.

## Boundaries

| Boundary | Check |
|---|---|
| Every rule in a standard names the org standard it rests on, or says it has none | `tests/test_tools.py::test_a_standard_that_cites_no_org_standard_is_caught` |
| The org's secrets baseline opens `.gitignore`, word for word | `tests/test_tools.py::test_an_edited_secrets_baseline_is_caught` |
| A first-party reusable workflow is pinned to its channel tag, as the org requires; anything else to a commit, with its version beside it | `examples/workflows/invalid/pin.a-first-party-branch.yml`, `examples/workflows/invalid/pin.no-version-beside-the-hash.yml` |
| The org's secret scan runs as written, exempt from one rule by name and held word for word | `tests/test_tools.py::test_an_exempt_workflow_is_held_word_for_word` |
| Nothing is installed, which is what rules out the org's linters and test runner | `tests/test_tools.py::test_third_party_code_is_caught` |
| The code owners file is the org's, word for word | `tests/test_tools.py::test_code_owners_are_the_orgs_word_for_word` |
