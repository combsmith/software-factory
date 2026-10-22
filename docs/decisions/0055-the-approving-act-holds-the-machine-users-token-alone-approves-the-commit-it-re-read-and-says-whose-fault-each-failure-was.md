# 0055. The approving act holds the machine user's token alone, approves the commit it re-read, and says whose fault each failure was

Status: accepted. The working rulings on "The approving act: the machine user approves from a Run with no Engine, bound
to the admitted commit" (issue 195), 2026-10-21, with the Maintainer's answers of 2026-10-21 relayed by the
orchestration session.

## Decision

| What | Decided | Because |
|---|---|---|
| The token | A fine-grained token of the machine user, for this repo alone, stored as `APPROVER_TOKEN` in an environment of its own, `factory-approve`, that holds nothing else: no App key, no model credential. No other environment holds it. Its deployment branch policy allows `main` alone, admin bypass is off, and it has no required reviewer. It is the one credential the act's job holds, so every read the act makes goes through it too | The classic token the Maintainer keeps for other uses can approve and merge across the org, and its every other write in a served repo would be a reconciliation alert (I-33). The Factory runs unattended, and P-3 showed a branch policy holds without a reviewer. The Maintainer chose this token (answer 2) |
| What the act does | `harness/approve.py` decides nothing. In order, each step that fails writing nothing: it reads its Decision from the pass record by its own Run id; it holds the token to the configuration's `approver`, a User; it reads the item again, with the head commit its first read gave; while what it read carries the content the Decision approved, it recovers the approver's approval of that commit if it is the approver's latest review of it, writing nothing; it asks the Kernel again with its own Run left out, and goes ahead only if `kernel.decide.still_wanted` says the approval is still issued for this content; it posts one review, `event` `APPROVE` with `commit_id` the head it read and nothing else, and reads it back by its id | §3.5: a Run started any other way finds no Decision and does nothing. I-38: an act that writes asks the Kernel again first. §3.6: a review is recovered as one by this actor on this commit. L-41: a claim is only what was read back |
| The one write | The act's transport is `effects.Approving`, narrowed for each step: who the token is; reads of the item's repo, the org's Pause and the facts port's own GraphQL reads of this pull request; and, for the approval step alone, one write, the approval of the commit the act just read. Any other request is refused before it leaves, so no push, comment, dismissal, resolution, merge or mutation can leave the job | Decision 0005: the machine user only approves |
| The binding | The commit approved is the one the act just read, whose content the Kernel just admitted again; never the head the pass saw, and never the pull request by number alone. A head that moved while it was read is `superseded`, `head_moved`, through the facts port's `Moved`. A push between the read and the post leaves `commit_id` bound to the commit read: GitHub attaches the approval there or refuses it, and the next pass decides afresh | Decision 0007: an approval is bound to content. What GitHub does with a `commit_id` behind the head is untried; P-7 posted with none, and a later trial on the canary asks it |
| What it records | `applied/1` with one Effect, `approve`, its state and its key, the review's node id as read back; `approve` is in `applied/1`'s types alone, never `effect/1`'s, so no Result can ask for an approval. `outcome/1` is null on success, else `item`, `environment` or `superseded` with a code, never `capacity`: the act runs no model, and a `capacity` outcome would defer every model Run | §4.9's threat "Craft a Result that has `apply` approve something else" |
| Whose fault | Only a status and what is read again decide the class, never GitHub's words. No Decision for this Run, the Kernel no longer wanting it, a head moved or a pull request closed: `superseded`. A read that failed, a Pause that cannot be read, 5xx, 429 or no answer, a token that is not the approver's, or 401, 403 or 404: `environment`; so is an approval GitHub took whose answer or read-back cannot be read, since it may stand. Any other refusal of the approval while the pull request is open at the commit, or a read-back that is not the approver's approval of that commit: `item`, an attempt. A read-back that cannot be read: `environment` | The Kernel has already asked whether the approver is the author or the last pusher (I-26), so a refusal that survives that is the pull request's, and after `max_attempts` a person looks (I-28). Every failure counts toward the Run ceiling (L-03) |
| A change to a model Lens's own inputs | The act approves only what the Kernel, asked again on fresh facts, still issues, so the wait for a different person's approval binds as the act starts: an approval decided before that person's approval was dismissed approves nothing. The machine user's own approval never judges such a change | The ruling on "A model Lens's inputs: its manifest and its prompt" (issue 140), its ruling 3, and the Maintainer's answer 1, held by decision 0052 |
| Its workflow | The approve workflow, on `workflow_dispatch`, is a frozen shim that calls the approve job's workflow at the Release's channel, with the item's concurrency group and the Pause; that workflow holds the one job, `approve`, on `factory-approve`, with `contents: read`, one secret, no `ref:` checkout, no cache and one `run:` line, which runs the act | The ruling on "Workflows: the frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape" (issue 196), its ruling 3: every workflow on `workflow_dispatch` is a shim. The live files land with that story's Run workflow, held from their first commit by the `approve` rule of `tools/check_workflows.py`, the second pull request of this story |

## Why

The approval is the one place the machine user's long-lived token is used, and the Factory's only path to a merge.
So the act holds it alone, writes one thing with it, and writes that only when the Kernel, asked again on what was
just read, still wants it. Section 3.10 and section 4.9 put the token in `apply`; the issue puts it in an environment
of its own, and this takes the issue's: `apply` holds the Role Apps' keys for a Run's Effects, and a Role's Result
can never reach the approver's token.

The token's age and its alert (L-37) are deferred to "Credentials: each stored credential's age read, and one alert
near its limit" (issue 305), and the reconciliation of every write by a Factory identity to a recorded Effect (I-33)
to "Controller: reconciliation, every write by a Factory identity matched to a recorded Effect (I-33)" (issue 306), by the Maintainer's answers 3 and 4.

## Boundaries

| Boundary | Check |
|---|---|
| The act sends one write, the approval of the commit it read, and its transport refuses any other | `tests/test_approve.py::test_the_act_sends_one_write_and_it_is_the_approval` |
| The commit approved is the one read, with nothing else in the review, and only the approver's approval of it read back by its id is claimed | `tests/test_approve.py::test_the_act_approves_the_commit_it_read_and_claims_only_what_it_reads_back` |
| A Run no Decision issued an approval for finds none and writes nothing | `tests/test_approve.py::test_a_run_no_decision_issued_an_approval_for_finds_none_and_writes_nothing` |
| Only the approver's own token, a User's, approves | `tests/test_approve.py::test_only_the_approvers_own_token_approves` |
| An approval that landed is recovered and nothing is written; a list that cannot be read recovers nothing | `tests/test_approve.py::test_an_approval_that_landed_is_recovered_and_nothing_is_written` |
| The act approves only what the Kernel, asked again with this Run left out, still wants | `tests/test_approve.py::test_the_act_approves_only_what_the_kernel_asked_again_still_wants`, `tests/test_decide.py::test_a_run_or_an_approval_is_still_wanted_only_for_the_same_content` |
| The act approves no change to a model Lens's own inputs that no different person approved | `tests/test_approve.py::test_the_act_approves_no_change_to_a_model_lenss_inputs_that_no_judge_approved` |
| Each fault is classed as the table says, by its status and what is read again, and never as `capacity` | `tests/test_approve.py::test_each_fault_of_the_act_is_classed_as_the_design_classes_it` |
| `approve` is an Effect `applied/1` records and no Result may ask for | `tests/test_approve.py::test_an_approval_is_an_effect_apply_records_and_no_result_may_ask_for`, `examples/invalid/result.asks-for-an-approval.json` |
| The act's workflow has the shape above, and no other workflow names `APPROVER_TOKEN` | waiting on `.github/workflows/approve-job.yml`, held by the `approve` rule of `tools/check_workflows.py` from its first commit |
| The step runs on `factory-approve` with the approver's token alone, reading the item as the pass does | waiting on `.github/workflows/approve.yml` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
