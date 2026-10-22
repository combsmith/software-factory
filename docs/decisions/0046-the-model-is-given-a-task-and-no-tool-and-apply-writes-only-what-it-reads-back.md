# 0046. The model is given a Task and no tool, and apply writes only what it reads back

Status: accepted. Taken as working rulings on 2026-10-21, which the Maintainer may overturn in review, for
"Harness: run and apply for the review Intent, and the model holds no credential that can write" (issue 194). It reopens
`docs/decisions/0033-the-factorys-model-credential-is-for-now-the-maintainers-own-subscription-and-a-trial-of-a-vendors-cli-records-no-repo.md`,
as that decision asked of slice 1's CI credential. Its first pull request holds the `run` job; the second, `apply`, and the
third, the Role, add rows here.

## Decision

| What | Decided | Because |
|---|---|---|
| The Task | `harness/task.py` builds `task/1` from the pass record's Decision, found by the Run id the Controller minted beside it, and the item's facts, the texts read for it, the Role's manifest and the configuration, and nothing else. Every input is held to its schema first. A Run no Decision admitted, or whose facts are of another item or content or were read short, or whose manifest does not declare its Intent, is refused before anything is asked, and nothing read crashes the job | A Run started any other way finds no Decision and does nothing, so nothing that can merely start a workflow can choose what a Run does (design section 3.5) |
| Trust | Each text is labelled from who wrote it, as the facts name the actor and the configuration lists the accounts: `maintainer` for the Maintainer, `role` for a Factory App, Lens or the machine user by the approver's name, `advisory` for a third-party reviewer `config/harness.json` lists, and `outside` for anyone else, a colleague with write access among them | A text's own words never say who wrote it |
| What is left out | A Task carries texts the Maintainer's first, then the Roles', the advisory reviewers' and anyone else's, each in the order given, each whole, up to `config/harness.json`'s characters as the Task carries them, escaped, and says in an optional `omitted` how many texts of each kind it left out and how many characters. The field is optional, so `task/1` keeps its major version | L-56; decision 0038: a field added later is optional. Counted as escaped, the budget bounds the bytes of the one argument the CLI is given, which Linux holds to 128 KiB (the security pass) |
| Limits | The tier and the permitted Effects are the Role's manifest's for the Intent; the limits are `config/harness.json`'s for the tier, since `role/1` has no field for them | One place for each number |
| The Engine | `harness/engine.py` runs the CLI as `tools/trial_p13_cli.sh` does: at the version `config/harness.json` pins, read before and after the call; in an empty directory, with nothing on its input; with no tool at all (`--tools ""`); with the model and the session named before the call; and with `result/1` handed resolved, the Harness's fields removed, `status` narrowed to `completed`, `incomplete` and `refused`, `run` held to the Task's and `effects` narrowed to the Task's `permitted_effects` | L-35; a Task holding outside text has no shell and no network tool (I-35); P-13 at 2.1.306 shows structured output works with no tool |
| The environment | The CLI is given exactly `PATH`, `LANG`, `HOME`, `TMPDIR`, `DISABLE_AUTOUPDATER`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` and the model credential under `CLAUDE_CODE_OAUTH_TOKEN` alone. No other name of the job's environment reaches it; with no credential, nothing is asked | P-26 at 2.1.306 failed: the CLI's sandbox hands a tool the parent's environment, and only the scrub takes a name off it ("Design: the CLI's sandbox limits connections but passes the parent's environment through (P-26 failed); the run job relies on the scrub and --tools \"\"", issue 287) |
| The answer | Of the CLI's answer only `structured_output` and the counts `usage` needs are read, by name; the model's prose is never kept. An answer that does not validate, against the schema the CLI was handed and against `result/1` whole, or that is another Run's, or that gives a reason with `completed` or none with any other status, is no Result: the Harness writes it whole, `failed`, `result_invalid`, with empty lists and `usage`. A CLI that fails, says it erred (`is_error` not false), runs past the Task's seconds, cannot be started or changes version under the Run is a `failed` Result with its own code; a Task too long for one argument is refused before the CLI starts, `task_too_large` | Decision 0038 |
| The `run` job | `harness/run.py` writes result.json and its sha256 into a new directory, and the log carries the digest alone. The Release is the pass record's | Nothing is handed from job to job through the log (section 3.10); one Release, one path (decision 0006) |
| The model credential | The Maintainer's own subscription, by a token from `claude setup-token` under his login, held as the `run` job's environment secret on `factory-run`, under `CLAUDE_CODE_OAUTH_TOKEN`; a metered API key under FR-73's cap is 0033's fallback | The Maintainer, 2026-10-21 |

## Why

The `run` job holds the model credential and `apply` the write credentials; reviewing them apart is reviewing the
boundary FR-10 draws. This first part is everything that happens before `apply`, and it is held with no I/O beyond a
stand-in for the CLI. The cost ceiling is recorded in `usage` and not enforced inside the call: the CLI has no limit
of its own on spend that a trial has asked of it.

## Boundaries

| Boundary | Check |
|---|---|
| A Task is built from the Decision that admitted its Run, and a Run no Decision admitted is refused | `tests/test_harness.py::test_a_task_is_built_from_the_decision_that_admitted_its_run`, `tests/test_harness.py::test_a_run_no_decision_admitted_finds_none_and_does_nothing` |
| A text's trust class is read from who wrote it | `tests/test_harness.py::test_each_text_is_labelled_by_who_wrote_it_never_by_the_text` |
| A Task says what it left out, and how much | `tests/test_harness.py::test_a_task_says_what_it_left_out_and_how_much`, `examples/invalid/task.an-omission-in-words.json` |
| The CLI is given exactly the named environment, the scrub set and the credential under its one name | `tests/test_harness.py::test_the_cli_is_given_exactly_the_named_environment_and_the_one_credential`, `tests/test_harness.py::test_no_credential_asks_nothing`, `tests/test_harness.py::test_the_cli_starts_in_an_empty_directory_with_only_its_environment` |
| The CLI is given no tool | `tests/test_harness.py::test_the_cli_is_given_no_tool` |
| A Task too long for one argument is refused before the CLI starts | `tests/test_harness.py::test_a_task_too_long_for_one_argument_is_refused_before_the_cli_starts` |
| An issue's Run is found among the issues | `tests/test_harness.py::test_an_issues_run_is_found_among_the_issues` |
| The CLI is handed `result/1` resolved and narrowed | `tests/test_harness.py::test_the_cli_is_handed_result_1_resolved_and_narrowed` |
| The version is held to the pin before and after | `tests/test_harness.py::test_the_version_is_held_before_and_after_the_call`, `examples/invalid/harness.an-engine-at-no-version.json` |
| The Harness fills `release` and `usage`, and an answer that does not validate is a `failed` Result | `tests/test_harness.py::test_a_result_the_engine_wrote_is_filled_and_kept`, `tests/test_harness.py::test_an_answer_that_does_not_validate_is_no_result`, `tests/test_harness.py::test_a_cli_that_fails_or_runs_past_its_time_is_a_failed_result` |
| The `run` job writes the Result and its digest, and the log carries the digest alone | `tests/test_harness.py::test_the_job_writes_the_result_and_its_digest_and_nothing_else`, `tests/test_harness.py::test_the_log_carries_the_digest_alone` |
| No job holds both a model credential and one that can write, and the `run` job's workflow sets the scrub and holds no other secret | waiting on `.github/workflows/run.yml` |
| `apply` re-reads the item, refuses what the Task does not permit, and writes only what it reads back | waiting on `harness/apply.py` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
