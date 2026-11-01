# 0107. The scorer's codes are in the public report and the judge's log

Status: accepted. The Builder's ruling of 2026-11-01, after eval run 41306021919 on the commit a1be0cf read 1 pass, 41 `case_failed` and 2 `diff_not_whole`, and nothing in the report could say why. It rests on the Maintainer's ruling of 2026-10-30 that closed "Evals: the public report's per-case verdicts can publish each case's kind": a case's kind is useless without its content, and the content stays in the private home.

## Decision

| What | Decided | Because |
|---|---|---|
| The report | A case the scorer did not pass carries the scorer's verdict and its own codes: `result_not_completed`, `finding_not_raised`, `category_differs`, `severity_differs`, `location_differs`, `coverage_disagrees`, `finding_raised_wrongly`, `criterion_not_met`, `answer_disagrees_with_verdict`, `location_unreadable`, `criterion_unknown`. `eval-report/1` lists them, and no longer lists `case_failed` for a case | 41 identical codes could not tell a reviewer that missed from a scorer that asked for what no Result can give. 0078 held them back as the answer key, and the ruling above says that overstated it. Its row "What the report says of a case" and its Boundaries row that the report and the log carry no code of the scorer's no longer hold |
| The run's verdict | `verdict` still returns `case_failed` for any case not passed, and the Release's gate reads that as before. The gate is unchanged: it passes every case or nothing | What moved is what a reader can see, never what passes |
| The judge's log | On `engine_fault` or `case_failed`, `judge` prints one line before its code: how many passed, and how many carry each code | The log is what a dispatcher reads first. The line is printed only once `verdict` has held the report to its schema, so what reaches the log is the enum's codes, whatever wrote the report |
| What stays out | No criterion, category, severity, location or diff, and no word of the model's. `severity_differs` says the two differ and not what either is. A report that carries what a case expected is still refused | The codes are enums. A case's content stays in the private home, and its Task never holds its id |
| What was found first | Canary run 41307506047, on the repo's own two example cases, three times each: the expected-`met` case on PR-1 failed all three as `criterion_not_met`, since the model says `not_applicable`, `no_issue_or_contract_provided`, and the expected Finding on PR-3 failed once in three, citing no criterion. A Task holds the diff alone, as `harness/read.py` says, in a live Run as in a case | The scorer reads a real Result correctly. No scorer, prompt or set change is made here: after seeing results that would be tuning to the test without knowing the mix, which these codes will show |

## Why

The eval is the Factory's one measure of its reviewer, and it had come to say only that the reviewer failed. A single code, held back to protect an answer key that a report could not assemble, cost a run of about 42 model calls each time someone wanted to know more.

## Boundaries

| Boundary | Check |
|---|---|
| A case the scorer failed carries the scorer's codes in the report and the judge's log, and the run says `case_failed` | `tests/test_evals.py::test_a_case_not_read_whole_or_failed_fails_the_run_with_its_report_uploaded` |
| A reason outside the enum reaches no log: the report is `report_unreadable`, alone | `tests/test_evals.py::test_a_case_not_read_whole_or_failed_fails_the_run_with_its_report_uploaded` |
| Every code the scorer gives is one the report may carry, and `case_failed` is none of a case's | `tests/test_evals.py::test_every_code_the_scorer_gives_is_one_the_report_may_carry` |
| A report that carries what a case expected is refused | `examples/invalid/eval-report.carries-what-the-case-expected.json` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
