# 0042. The context is tested by a task run outside CI, and the runs are held as a fixture

Status: accepted. Taken as a working ruling on 2026-10-20, which the Maintainer may overturn in review, for
"The context's test: a fresh agent adds a rule to the Kernel without being told how" (issue 8), the last story of slice 0.
It adds to `docs/decisions/0013-context-is-part-of-the-product.md`, whose last row it builds, and to
`docs/decisions/0033-the-factorys-model-credential-is-for-now-the-maintainers-own-subscription-and-a-trial-of-a-vendors-cli-records-no-repo.md`, whose login and pin the runs
use. The Maintainer chose, the same day, that the task takes a rule other than issue 237's, by the criteria below.

## Decision

| What | Decided | Because |
|---|---|---|
| The task | One Kernel rule the repo does not hold and no `@pending` test states, chosen by four criteria: the design states it; it is one reason code in one Kernel module behind one boundary; it needs no new fact and no new limit; it is decided. Its boundary test is the known answer, written in the private held-out home by a private session, and only its sha256 is here. The sentence names the rule and its code and nothing of how, and is never in this repo, a pull request, an issue or a shared transcript until the runs are recorded | A task whose answer is in the repo measures nothing; as first written the test could not fail. A task with a known answer, run more than once, is how context is evaluated |
| Who runs it, and on what | `tools/context_eval.sh` at the Maintainer's terminal, never CI: the CLI at the pin of 0033, on the configuration directory logged in to his own subscription, headless, with the sentence as its whole prompt, on a `git archive` export of one commit of `main` outside every repo, with a scratch HOME and its login alone, its network tools refused, a cap on turns. Its shell is not sandboxed (trial P-26 has no fixture): the record counts each path it named outside the export and each command it could not read | CI runs no model and fetches nothing; the credential lives where 0033 put it; an export has no history, remote or other checkout to read from; what cannot be confined is counted, so a run that looked elsewhere says so |
| How a run is judged | After the agent stops, the runner, not the agent: the held-out test copied in, run on its own and taken out again before anything else; the Makefile and every tool but `tools/mutants.py` put back as made, each one the agent had changed recorded; `make verify`; the whole mutation check, which must kill every mutant, the agent's among them, and no mutant may be dropped from the list. A run passes on all three; the story passes at three of three | The held-out test says whether the rule is the one asked; verify says the change is finished; a killed mutant says the agent followed the three-part rule and not only made a test pass |
| What a run records | A `context-eval/1` run in `evals/context/task.json`: the commit, the date, the CLI's version and the cap; the paths read and the first words of each command, from the transcript's tool uses alone, with a word shaped like a token never recorded; how many paths were named outside the export and how many commands could not be read; what changed, by file, in lines, and what of the judge's was put back; the test, mutant and reason code added; the result's counts, null when the CLI gave none; the three verdicts. Of the model's text only the names it chose, the first words of its commands and the paths it named, each held to a pattern: never a text block, a tool's result, a prompt or an answer | What CI can hold is a fixture of the runs, as a trial's fixture is held, honest about what it holds; a word of the model's would leak the answer, or a hint toward it |
| A failed run | Recorded too; the context changes, never the task, in a pull request of its own that names the failed run; then three fresh runs. The test counts the newest three on the task's hash | The measure is of the context; a task changed after a failure would be the proof of concept's stub again |
| A later change to the context | Re-run at the Maintainer's call, not by CI; the record's commit says what was tested | CI cannot run a model, and cannot tell which change to the context matters |

## Why

Slice 0's exit is that an agent given only the repo and one sentence adds a rule to the Kernel and passes the required
check (design §9.1, §9.14). Nothing in CI can run a model or read the private home, so the test is two things: a
runner that makes and judges the runs where the model and the answer are, and a record in the repo that a test in
`make verify` holds. The record is held the way a trial's fixture is: what it claims is pinned by its content, and the
test that holds it fails until the runs exist. The first pull request lands the runner, the record's form and the test
still `@pending`; the second lands the runs and takes the mark off.

## Boundaries

| Boundary | Check |
|---|---|
| A run's record holds paths, first words, counts and verdicts, and no word of the model's; what cannot be read makes no record | `tests/test_tools.py::test_the_record_holds_paths_counts_and_verdicts_and_no_model_text`, `tests/test_tools.py::test_what_cannot_be_read_makes_no_record` |
| The transcript and the record stay outside the repo, and the front door refuses one inside it | `tests/test_tools.py::test_the_front_door_refuses_a_transcript_inside_the_repo_and_writes_the_record` |
| The runner gives the CLI only the named environment, a scratch HOME and no key of the shell's among it, and judges by the held-out test, `make verify` and the mutation check | `tests/test_tools.py::test_a_run_is_judged_and_recorded_with_no_model_text` |
| A verdict that fails is recorded and fails the run, a mutant that survives the whole check among them; the held-out test is taken out before `make verify`; a judge's file the agent rewrote is put back and recorded; the held-out test's words never reach the record | `tests/test_tools.py::test_a_verdict_that_fails_is_recorded_and_fails_the_run` |
| The runner refuses before it asks: OUT taken or inside a repo, CONFIG_DIR the default, REPO no checkout, COMMIT unknown, a sentence that is not one or names no code, a held-out test inside the repo | `tests/test_tools.py::test_each_refusal_stops_before_anything_is_asked` |
| The record is `context-eval/1`, in `LIVE`, with a task of one sentence and a hash of 64 hex; a counter-example of each is rejected | `tools/check_examples.py` |
| The context's test passes three of three on its task | `tests/test_evals.py::test_a_fresh_agent_given_the_repo_adds_a_rule_and_passes_the_check`, not held yet |
