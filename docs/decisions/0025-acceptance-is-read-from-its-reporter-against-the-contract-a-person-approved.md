# 0025. Acceptance is read from its reporter, against the contract a person approved

Status: accepted.

## Decision

The contract that counts is the one a person approved. The facts carry, in `acceptance`, the
contract a person approved, read at the commit of the newest approving review by a person: its
digest, who approved it, and each criterion by id and kind, never its statement; the contract's
digest at the head; and each result, with the check that reported it. A digest covers the contract
and every path it protects (§3.13), so an edit to a test it names changes it. The criteria come from
the approved contract, never the head. Whether there is a contract at all is the linked issue's:
`acceptance` is null only where the issue the pull request closes asks for none, read in full.

Two Holds come before anything admits a Run, after a foreign check and before a conflict: a contract
no person approved, an approval by the machine user or an App among them, is `contract_not_approved`;
a head whose digest differs from the approved one, a deleted contract among them, is
`contract_changed`. Both are the Maintainer's to see, take a queued item out, and end only when a
person approves the contract at the head. One approving review of the content by a person approves
the contract at that commit.

A result counts only from the reporter its criterion's kind names. The configuration's
`acceptance_reporters` maps each kind a check reports to a required deterministic Lens by name, or
to null: `test` to `verify`, and `scenario`, `mutation`, `static` and `role` to null for now. A result
on this content is read as that Lens's check is, by its name, its App and its workflow file; one from
anywhere else, or for a kind with no reporter, makes the contract unreadable, before any failure,
and the Decision says which: `AC-n:from_app:<id>`, `AC-n:from_workflow:<path>`,
`AC-n:from_another_check` or `AC-n:no_reporter`. Results on earlier content are not judged.

Only a person passes a criterion of kind `human`: a person's approving review of this content that
no person has dismissed confirms every such criterion there. A check's result for one is unreadable,
whatever the configuration names. It never fails; a person objects with a request for changes, which
gates. That review approves no content.

The approval is held to a review GitHub holds: the contract a person approved names the commit it was
approved at, and `reviews` must hold that person's approving review on that commit, which no person has
dismissed; otherwise it is `contract_not_approved`. A digest is `sha256:` and a whole SHA-256. A
contract that cannot be read, an approver `readable_actor` refuses, an unknown kind, a criterion named
twice or a digest cut short among it, defers for the Maintainer, read with the Holds, and admits
nothing; so does a configuration whose `acceptance_reporters` cannot be read, as
`acceptance_reporters_unreadable`. Every field of a review the Kernel reads, its commit, content and
dismissal among them, is read whole, or the review is unreadable.

## Why

The head is the author's. Read from it, a push that deletes the contract, drops a criterion or points
one at a trivial test weakens the check, and a failing criterion could admit a fix Run before anyone
approved what the work is judged against (I-29, I-30). An approval is a person's act at one commit
(decision 0007), so the contract is read there, and a change to anything it protects needs that act
again. A conflict, a failed check and an open Finding each admit a fix Run before acceptance's
evidence is read, so the contract's identity is read before all of them.

Any App with `checks: write` can report a passing result, the implementing Role's own among them, and
GitHub Actions runs any job a pull request adds: no Role judges its own work (I-10, FR-30). A result
already names the check that gave it, so it is read with `reports_for`, the one matcher a Lens's check
is read with (decision 0026), and the same threat has one mechanism. The digest and decision 0020
keep the named tests and `verify`'s inputs from changing unseen.

A dismissal by an App ends nothing a person did (L-17): it ends no request for changes, and it leaves
a person's approval of the contract, and of a `human` criterion, standing. Only a person's own
dismissal withdraws it. The working ruling said "undismissed"; its simulator line has an approval an
App dismissed stand, and the gate already reads a person's request that way, so this reads both alike
and keeps a Lens's App from turning a person's confirmation off. The ruling's new trial is P-38, as
P-37 was taken by decision 0023.

## Boundaries

| Boundary | Check |
|---|---|
| A contract no person approved, or one approved by the machine user, an App, a Lens's App or a stranger, is a Hold for the Maintainer, whatever its evidence, and takes a queued item out | `tests/test_decide.py::test_a_contract_no_person_approved_is_a_hold` |
| A head whose contract's digest differs from the approved one, or that carries none, is a Hold until a person approves again; a contract no person approved is read first | `tests/test_decide.py::test_a_contract_changed_since_its_approval_is_a_hold` |
| No Run is admitted on a contract no person approved, or one changed since: not for a conflict, a failed check, an open Finding, a failing criterion or a model review. A check from another App is read before it | `tests/test_decide.py::test_no_run_is_admitted_on_a_contract_not_approved` |
| A result counts only from the check of the Lens the configuration names for its criterion's kind, by its name, App and workflow file; any other is unreadable, read before any failure, takes a queued item out, and is named once, in the form a foreign check is | `tests/test_decide.py::test_a_result_counts_only_from_the_reporter_its_kind_names` |
| A result for a kind no Lens reports is unreadable, from any check; once the configuration names a Lens, its check's result counts | `tests/test_decide.py::test_a_kind_with_no_reporter_cannot_pass` |
| A `human` criterion is passed only by a person's approving review of this content that no person dismissed; never by the machine user, an App, a stranger, other content or a check, whatever the configuration says, and it never fails | `tests/test_decide.py::test_a_human_criterion_is_passed_only_by_a_persons_approval_of_this_content` |
| An approval or criterion that cannot be read defers for the Maintainer and admits no Run; each Hold is the Maintainer's to see and never stale | `tests/test_decide.py::test_an_unreadable_contract_admits_nothing`, `tests/test_decide.py::test_unreadable_acceptance_never_converges` |
| The approval of the contract is a review GitHub holds: by that person, with write access, approving, on the commit the approval names, and not dismissed by a person; an App's dismissal leaves it standing | `tests/test_decide.py::test_an_approval_of_the_contract_is_a_review_github_holds`, `examples/invalid/facts.an-acceptance-contract-approved-on-no-commit.json` |
| A digest, approved or at the head, is `sha256:` and exactly 64 lower-case hexadecimal digits | `tests/test_decide.py::test_a_digest_is_a_whole_sha256`, `examples/invalid/facts.an-acceptance-digest-cut-short.json` |
| Every field of a review the Kernel reads is there and in its form, a person's comment too, or the review is unreadable | `tests/test_decide.py::test_every_field_of_a_review_the_kernel_reads_is_read_whole` |
| A configuration whose `acceptance_reporters` is missing or of another shape defers an item with a contract for the Maintainer | `tests/test_decide.py::test_a_contract_whose_reporters_cannot_be_read_defers` |
| The facts carry the approved contract, its digest at the head and each result's check, and refuse any of them missing or a kind the Kernel does not know | `examples/invalid/facts.an-acceptance-contract-without-its-head.json`, `examples/invalid/facts.an-acceptance-contract-approved-by-a-name-alone.json`, `examples/invalid/facts.an-acceptance-criterion-of-a-kind-the-kernel-does-not-know.json`, `examples/invalid/facts.an-acceptance-result-without-its-check.json` |
| Under faults, nothing is admitted, converges, queues or merges unless a person approved the contract and the head still carries it, and every criterion passes from its kind's reporter | `tests/test_simulator.py::test_the_seeds_serve_items_with_an_acceptance_contract_and_without`, `tests/test_simulator.py::test_invariants_hold_under_faults` |
| The port reads whether a contract exists from the issue the pull request closes, never the head; the approved contract at the commit of the newest approving review by a person; the digest over the contract and every path it protects; and each result's check | waiting on `adapters/acceptance.py` |
| Whether an approval GitHub dismisses as stale stays on its commit, and who is recorded as dismissing it, is a platform fact, unverified until trial P-38 grounds it | `sim/grounding.py`, `tools/check_trials.py` |
| `apply` refuses the implementing Role's change to a contract or a test it names (I-30) | waiting on `harness/apply.py` |
| A reporter for `role`, `static`, `mutation` and `scenario` | waiting on `roles/` |
