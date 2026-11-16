# 0218. An issue's timeline is read by REST, whole by its missing next link, and an App's act with a person's token is the App's

Status: accepted. The Factory Builder's ruling (A) of 2026-11-13 on the readers' major of the issues port's first part: an App acting with a person's token was read as that person. It amends decision 0028's row "A timeline is read whole when its last page's `hasNextPage` is false", and the same row of decisions 0139 and 0141.

## Decision

| What | Decided | Because |
|---|---|---|
| The timeline | `adapters/issues.py` reads it by REST, through `adapters/timeline.py`: whole when its last page names no next link, never by a count or a short page | REST names `performed_via_github_app` on each event, as trial P-34 read again by REST shows; GraphQL names no App an event was made through |
| An App's act | An act an App made with a person's token, the opening among them, is the App's, by `performed_via_github_app`, as on a pull request; one whose App cannot be told refuses the read | A label, a reopening or a comment so made moves nothing a person's would |
| GraphQL | Only for what REST does not give, `lastEditedAt` and the type's changes, with its `updatedAt`, which must be REST's `updated_at` or the issue moved while it was read and the read is refused. A key left out refuses the read; null is read only where the key is there | A field dropped from a query answers with no key, which read as null would be no edit |
| Owed | A trial that records the port's own GraphQL read, `lastEditedAt`, `updatedAt` and the type's changes, and that GraphQL's `updatedAt` agrees with REST's, is "Trial: the issues port's own GraphQL read of an issue, its lastEditedAt, updatedAt and type changes, recorded, and its updatedAt held to REST's" (issue 831), which joins the re-recordings of "Trials: each grounded rule the ports read in another shape than was recorded is recorded again in the port's own query, the checks port's status rollup first" (issue 807) | No trial has asked the type's changes; until one does, the port's query is held by its test alone |

## Why

GraphQL cannot tell an App acting with a person's token from that person, so a label an App so placed could count as a person's. The pull request's port reads REST's attribution; the issue's now does too.

## Boundaries

| Boundary | Check |
|---|---|
| A key GraphQL left out refuses the read; the read asks each field the facts need, written out in its test | `tests/test_adapters.py::test_an_issue_github_did_not_answer_whole_is_refused`, `tests/test_adapters.py::test_the_issues_own_facts_hold_to_the_schema_and_leave_its_linked_pull_requests_unread`, `adapters/issues.py`, mutant: "a key GraphQL left out is read as null", mutant: "the edits leave out lastEditedAt" |
