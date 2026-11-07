# harness/eval/

The eval job's steps, a module each, in the order `__init__.py` gives. Their rules are `evals/AGENTS.md`'s, beside the sets they run, but for what issue 612, "The eval job reads a named set, and a gate set's report is aggregates only", adds, which are here.
A dispatch names its set. A set whose manifest says it is a gate set is reported by counts alone, `eval-aggregate/1`, and each case's outcome with its Result goes to a ledger, `eval-ledger/1`, kept in the scratch.
`seal.py` encrypts the ledger with `openssl cms` to each of the Maintainer's certificates that its pins, in a protected path under `.github/`, name by sha256 (`seal.RECIPIENTS`). The ciphertext alone is uploaded, as `eval-ledger`.
No key that opens a ledger is in the job or the repo. Until the Maintainer commits his certificates, a gate set's run fails at the seal, `no_recipient`. Where a ciphertext is kept past its artifact's 90 days is not built yet.

| Rule | Held by |
|---|---|
| A dispatch names its set by one part, the review Intent's where it names none, and each step reads the set the plan named | `tests/test_evals.py::test_a_named_set_is_read_and_a_name_of_more_than_one_part_is_not` |
| A gate set's report holds counts alone, no case's id, verdict or code; its ledger, in the scratch alone, every case with its Result | `tests/test_evals.py::test_a_gate_sets_report_holds_counts_alone_and_its_ledger_every_case` |
| The seal encrypts the ledger by RSA-OAEP and AES-256 to each pinned certificate as checked, binds the ciphertext in the report, and removes the plaintext | `tests/test_evals.py::test_the_seal_encrypts_the_ledger_to_each_pinned_certificate_alone` |
| A certificate not pinned, a pin not whole, a ledger not the report's or not sealed whole: nothing is sealed | `tests/test_evals.py::test_the_seal_refuses_a_certificate_not_pinned_and_a_ledger_not_sealed_whole` |
| The gate passes a gate set's report only if it is sealed, its counts add up to its set and its own words, and each kind's bar is cleared | `tests/test_evals.py::test_the_gate_passes_a_good_aggregate_report_and_refuses_a_bad_one` |
| A report of the other kind than its set's is refused; a development set's is `eval-report/1`, as before, and seals nothing | `tests/test_evals.py::test_the_gate_passes_a_good_aggregate_report_and_refuses_a_bad_one` |
| A gate set's judge prints counts and codes, never a case | `tests/test_evals.py::test_a_gate_sets_judge_says_counts_and_codes_and_never_a_case` |
| The seal and the ledger's upload come after the run and before the report's, the seal given nothing | `tests/test_evals.py::test_the_eval_workflow_names_each_credential_in_one_step_alone` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
