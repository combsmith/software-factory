# 0209. The transport refuses a path with a dot segment, and Sonar's traversal rule is set aside for its file

Status: accepted. The Factory Builder's ruling of 2026-11-13 on "SonarCloud: code security review (pythonsecurity)" (issue 725), and the Maintainer's of 2026-11-12 that a confirmed false positive may be set aside in the repo.

## Decision

| What | Decided | Because |
|---|---|---|
| The finding | SonarCloud's one finding, pythonsecurity:S7044, "API Traversal via file content in Live.send()", is of the transport's request line, reached from the eval job through `adapters/heldout.py`. On that flow it is a false positive: `case()` fullmatches the Role and the case's id, and `home()` the owner and the name, before the path is built | Sonar's taint engine reads no fullmatch as a sanitiser |
| What was real | The transport held a path's host and no segment of it, so its request line was safe only caller by caller. Four callers reach it with a part that only its source holds: the event payload's repo in `tools/commits_are_the_maintainers.py`; the home's branch and the home's repo from the Controller's configuration, whose schema admits a segment of two dots; and a pull request's base ref. None is an outsider's text today | Found by the two Claude reads of this change's first form, a NOSONAR on the line, which would have silenced every rule there for every caller |
| The fix | `request` refuses a path any segment of which is one dot or two: plain, percent-encoded in either case, or behind an encoded slash or backslash. The query is not read as path, and a dot within a name is no segment | GitHub resolves a dot segment within a contents path: on a public repo, a path through a missing folder and two dots answered the file beside it. It did not climb out of the endpoint. Refused where every request is built, no port need hold it again |
| What grounds it | Reads of a public repo with no credential on 2026-11-12, by the builder and by a reviewer: no trial, and no fixture. The builder's five answered 404 and were first reported as "GitHub does not resolve them", which was too strong; the reviewer's answered the file | Written down as it was learned. The refusal needs no trial to be safe: no path the Factory builds has such a segment |
| What it does not hold | A part that holds a slash, a question mark or a hash of its own, which names another endpoint or a query with no dot in it: each port holds its own parts, as the held-out port does. Nor a percent-encoding of a percent, which is no dot segment to a server that decodes once | The transport cannot tell a caller's slash from a part's |
| The held-out port | Unchanged. Its test refuses three more inputs, an id with a slash, an id with a percent and a home's name with a percent, and holds `home()`'s own refusal of a name of one dot or two apart from the transport's | Three mutants of its patterns survived; and the transport's refusal would otherwise have hidden the port's own |
| Sonar | `sonar-project.properties` sets pythonsecurity:S7044 aside for `adapters/github.py` alone, in the form the file already holds. Every other rule stays live on it, and no NOSONAR is written there | A line's NOSONAR silences every rule on it. The finding is of the line every request passes, so the rule is set aside for the file whose `request` holds the path |
| Residual | A port still to be written that puts an unheld part into a path is no longer flagged by that rule in this file | The transport's refusal stands in for it for a dot segment, and each port's own tests hold its parts |

## Why

The finding was a false positive on the one flow it named, but marking it so on the line would have hidden the same rule, and every other, for each of the hundred or so requests built there. The reads of that mark showed what the rule was pointing at: nothing at the sink held a path's segments. Holding them there makes the transport safe against a climb whoever calls it, which is what lets the rule be set aside for the file, and only that rule.

## Boundaries

| Boundary | Check |
|---|---|
| A path with a segment of one dot or two, plain, percent-encoded or behind an encoded slash or backslash, is refused before anything is sent; a dot within a name, and a dot in the query, are not | `tests/test_adapters.py::test_a_request_stays_on_githubs_api`, `adapters/github.py`, `tools/mutants.py`, mutant: "a path may hold a dot segment", mutant: "a dot segment is refused only where it is plain", mutant: "a segment of two dots is asked", mutant: "a segment of one dot is asked", mutant: "a dot segment behind an encoded slash is asked", mutant: "a dot segment behind an encoded backslash is asked", mutant: "a dot segment in a query is refused" |
| The held-out port refuses an id or a Role with a slash or a percent, and a home's name with a percent, asking nothing; and a home named with one dot or two by itself | `tests/test_adapters.py::test_a_held_out_case_not_read_whole_says_why`, `adapters/heldout.py`, `tools/mutants.py`, mutant: "a held-out id or Role may hold a slash", mutant: "a held-out id or Role may hold a percent", mutant: "a home's name may hold a percent", mutant: "a home that climbs out is asked" |
| The transport's file holds no NOSONAR, and Sonar's traversal rule is set aside for it by rule and file | `tests/test_adapters.py::test_a_request_stays_on_githubs_api`, `sonar-project.properties`, `tools/mutants.py`, mutant: "Sonar's traversal rule is set aside for every file" |
