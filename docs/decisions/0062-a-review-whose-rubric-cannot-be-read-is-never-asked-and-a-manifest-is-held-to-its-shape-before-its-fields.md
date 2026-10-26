# 0062. A review whose rubric cannot be read is never asked, and a manifest is held to its shape before its fields

Status: accepted. Taken as working rulings on 2026-10-25, which the Maintainer may overturn in review, for "Harness and the team checks: a review Run whose rubric cannot be read is refused before the CLI, and a manifest of the wrong shape is a problem, not a traceback" (issue 330). It extends `docs/decisions/0059-a-roles-manifest-is-held-to-the-authority-table-and-its-apps-ceiling.md`, whose run job tells the CLI the rubric and whose team checks read the manifests.

## Decision

| What | Decided | Because |
|---|---|---|
| A review's rubric | For an Intent whose Result covers a rubric, `review-change` today (`harness/run.py`'s `REVIEWING`), the run job reads the Role's rubric and refuses it unless it names this Role and this Intent and can be read as a rubric. A rubric that is missing, of another Role or Intent, of no criteria, or not JSON makes the job write a `failed` Result, reason `rubric_unreadable`, before the CLI is started. An Intent that covers no rubric is told none | A Result covers its rubric (decision 0049). A review asked without one is a model call spent on a Result `apply` must refuse. The fault is the Factory's, an `environment` one, and is read before the call |
| A manifest's shape | `tools/check_authority.py`'s `team()` holds each manifest to `role/1` before reading anything from it. One of another shape is a problem naming its file, and nothing else is read from it | A field of the wrong type ended the check in a traceback, which reports no problem at all |

## Why

Both faults already failed closed: `apply` refuses an uncovered Result, and `tools/check_examples.py` holds every
manifest to `role/1` in the same verify run. Each is now caught where it starts, and reported as a code or a problem
rather than a model call or a traceback.

## Boundaries

| Boundary | Check |
|---|---|
| A reviewing Run whose rubric is missing, of another Role or Intent, of no criteria, or not JSON is never asked, and the run job writes a `failed` Result, `rubric_unreadable` | `tests/test_harness.py::test_a_review_whose_rubric_cannot_be_read_is_never_asked` |
| An Intent that covers no rubric is told none | `tests/test_harness.py::test_the_cli_is_told_the_roles_instructions_and_rubric_from_the_release_before_the_task` |
| A manifest of another shape is a problem, never a traceback | `tests/test_tools.py::test_a_manifest_is_named_as_its_file_and_held_to_role_1` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
