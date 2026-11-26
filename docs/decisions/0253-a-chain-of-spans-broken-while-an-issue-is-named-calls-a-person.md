# 0253. A chain of spans broken while an issue is named calls a person

Status: replaced by `docs/decisions/1239-an-issues-reads-are-bounded-and-a-read-cut-short-calls-a-person.md`, which holds the rule in force.

## Decision

| What | Decided | Because |
|---|---|---|
| Which first | The issues the newest record that read the issues left out as `issue_budget` are read first, as decision 0251 orders them. A record whose list was read short is passed over (`controller/pass_.py`, B4) | A short list, which an outsider can force, must not empty the queue |
| A chain broken while named | Where the records break the chain while a pull request names the issue, or anything but an issue cross-references it, the facts say `spans_broken` (`adapters/linked.py`). The issues' Kernel defers on it, after a cut read and before a list read short, and calls a person (`kernel/issue.py`). Absent or not exactly true, it is no break (C) | No later pass mends such a chain, so it must not wait in silence |
| Nothing names it | A broken chain with spans but nothing naming the issue defers on its short list and calls no one. No record opens a new span, so the spans leave the two records at hand and the list is whole again (d) | It clears in a pass or two |

Limits: an issue left unread in both records at hand has its chain broken (decision 0251). While anything names it, it calls a person until it is closed or nothing names it. An outsider can bring that by opening some forty issues, or by forcing a short list.

## Why

Decisions 0251 and 0252 leave issues out by a budget and by a short list. The keyword spans' chain and the queue must read past such passes without breaking in silence. Calling a person for every broken chain with spans was rejected (d): that state mends itself.

## Boundaries

| Boundary | Check |
|---|---|
| A budget in a fraction is no configuration; the debts read first are the newest record's | `examples/invalid/controller.a-budget-in-a-fraction.json`, `tests/test_controller.py::test_the_issue_reads_stop_at_the_passs_budget_and_those_left_out_by_it_are_read_first_by_the_next`, `controller/pass_.py`, mutant: "the issues are read first by the oldest record's debts" |
| A record whose list was read short is passed over by the queue | `tests/test_controller.py::test_the_issue_reads_stop_at_the_passs_budget_and_those_left_out_by_it_are_read_first_by_the_next`, `controller/pass_.py`, mutant: "a list read short keeps the queue" |
| An issue left unread by the budget raises its own alert; a pull request's entry with the list's code is facts that are not facts | `tests/test_controller.py::test_an_issue_left_unread_by_the_budget_raises_its_own_alert_and_no_other`, `controller/reads.py`, mutant: "an issue list read short is a pull request's code too" |
| A chain broken while named defers `spans_broken` and calls a person | `tests/test_issue.py::test_a_chain_of_spans_the_records_broke_defers_on_its_own_code_and_calls_a_person`, `tests/test_adapters.py::test_a_record_that_left_the_issue_out_by_its_budget_is_passed_over_for_it_alone`, `tests/test_adapters.py::test_a_chain_of_spans_the_records_broke_while_something_names_the_issue_is_said`, `kernel/issue.py`, mutant: "a broken chain calls no one" |
| A broken chain is read after a cut read and before a list read short | `tests/test_issue.py::test_a_chain_of_spans_the_records_broke_defers_on_its_own_code_and_calls_a_person`, `kernel/issue.py`, mutant: "a broken chain is read before a cut read" |
| A broken chain with spans but nothing naming the issue defers on its short list, and is whole once those spans leave the two records at hand | `tests/test_adapters.py::test_a_record_that_left_the_issue_out_by_its_budget_is_passed_over_for_it_alone`, `tests/test_adapters.py::test_a_chain_of_spans_the_records_broke_while_something_names_the_issue_is_said`, `adapters/linked.py`, mutant: "a broken chain is a break whatever names the issue" |
| The simulator breaks the chain beside a linked list read short, so its seeds meet the deferral under faults | `tests/test_issue.py::test_the_issue_world_meets_a_broken_chain_of_spans_under_faults_and_calls_a_person`, `sim/issues.py`, mutant: "the issue world never breaks a chain of spans" |
