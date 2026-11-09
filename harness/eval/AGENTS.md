# harness/eval/

The eval job's steps, a module each, in the order `__init__.py` gives. Their rules are `evals/AGENTS.md`'s, beside the sets they run, but for what three issues add, which are here:
issue 612, "The eval job reads a named set, and a gate set's report is aggregates only", issue 613, "The gate pools k dispatches on one commit and reads all of them",
and issue 611, "A case's head is read from the private home, pinned by its hash, and the run is sharded".
A dispatch names its set. A set whose manifest says it is a gate set is reported by counts alone, `eval-aggregate/1`, and each case's outcome with its Result goes to a ledger, `eval-ledger/1`, kept in the scratch.
`seal.py` encrypts the ledger with `openssl cms` to each of the Maintainer's certificates that its pins, in a protected path under `.github/`, name by sha256 (`seal.RECIPIENTS`). The ciphertext alone is uploaded,
as `eval-ledger`, or `eval-ledger-<part>` for a part.
No key that opens a ledger is in the job or the repo, and nothing automated reads one. Until the Maintainer commits his certificates, a gate set's run fails at the seal, `no_recipient`.
The ciphertext lives only as a run artifact under its retention until a storage decision is made; the run's one output, `ledger_sha256`, is its hash, or in a split run the merge's hash of every part's. Where ledgers are kept is not built yet.
A gate set gives its own bars and least of a kind. The Release's gate pools every dispatch on a commit of the gate set `config/harness.json` names, `gate_set`.
Until one is named, the gate reads the review Intent's set by its newest successful dispatch, which a re-dispatch can still make the best of several.
A gate set's dispatch asks its preflight first, a few cases of the review Intent's set scored apart, so that a broken pipeline stops it before any held-out case is asked.
A case's head is read from the home beside the case, its tarball and its tree each by the sha256 the case pins, and held to that tree (issue 611); nothing in the job reads with no credential.
The run is split into the preflight's job, a matrix of shards and a merge job with no credential, which writes the one report from each part's counts; a gate set's shards are drawn by a salt the home keeps.

| Rule | Held by |
|---|---|
| A dispatch names its set by one part, the review Intent's where it names none, and each step reads the set the plan named | `tests/test_evals.py::test_a_named_set_is_read_and_a_name_of_more_than_one_part_is_not` |
| A gate set's report holds counts alone, no case's id, verdict or code; its ledger, in the scratch alone, every case with its Result | `tests/test_evals.py::test_a_gate_sets_report_holds_counts_alone_and_its_ledger_every_case` |
| The seal encrypts the ledger by RSA-OAEP with SHA-256 and AES-256 to each pinned certificate as checked, binds the ciphertext, removes the plaintext | `tests/test_evals.py::test_the_seal_encrypts_the_ledger_to_each_pinned_certificate_alone` |
| A certificate not pinned, a pin not whole, a ledger not the report's or not sealed whole, a file already at the ledger's place: nothing is uploaded | `tests/test_evals.py::test_the_seal_refuses_a_certificate_not_pinned_and_a_ledger_not_sealed_whole` |
| The gate passes a gate set's report only if it is sealed, its counts add up to its set and its own words, and each kind's bar is cleared | `tests/test_evals.py::test_the_gate_passes_a_good_aggregate_report_and_refuses_a_bad_one` |
| A report of the other kind than its set's is refused; a development set's is `eval-report/1`, as before, and seals nothing | `tests/test_evals.py::test_the_gate_passes_a_good_aggregate_report_and_refuses_a_bad_one` |
| No set but a gate set names a gate set's case, by its id or its hash | `tests/test_evals.py::test_no_set_but_a_gate_set_names_a_case_of_one` |
| A gate set marks no group of natural cases, or of others, under ten but none | `tests/test_evals.py::test_a_gate_set_marks_no_group_of_natural_cases_or_others_too_small_to_hide_one` |
| A gate set's judge prints counts and codes, never a case | `tests/test_evals.py::test_a_gate_sets_judge_says_counts_and_codes_and_never_a_case` |
| The seal and the ledger's upload come after the run and before the report's; the seal is given nothing, and the merge step alone sets the run's one output | `tests/test_evals.py::test_the_eval_workflow_names_each_credential_in_one_step_alone` |
| A gate set gives its own bars, least of a kind and the record that states them word for word, and its job and gate hold them; no other set gives any | `tests/test_evals.py::test_a_gate_set_gives_its_own_bars_and_least_and_its_record_states_them` |
| The pool is three runs at least, every one, each kind summed under the set's bars; one faulted closes it | `tests/test_evals.py::test_the_gate_pools_every_dispatch_on_the_commit_and_one_faulted_closes_it` |
| A gate set's preflight is three to five of the review Intent's cases, none a gate set's by its id or its hash | `tests/test_evals.py::test_a_gate_sets_preflight_is_of_the_development_set_and_no_gate_sets_case` |
| The preflight is asked first; a fault in it, or no pass, stops the dispatch before a case of the set is asked, and the gate reads it as faulted | `tests/test_evals.py::test_a_gate_sets_dispatch_asks_its_preflight_first_and_a_broken_one_stops_it` |
| Each case's head is read from the home by its pins, unpacked and held to its tree; one not the one pinned, or not read whole, closes the gate | `tests/test_evals.py::test_each_cases_head_is_read_from_the_home_by_its_pins_and_one_not_read_closes_the_gate` |
| A split run's merge is the report of the whole; a part missing leaves its cases unanswered; no step names a case | `tests/test_evals.py::test_a_development_sets_run_split_into_shards_is_merged_into_the_report_of_the_whole` |
| A gate set's shards are drawn by the home's salt, never by place, and its parts write counts alone | `tests/test_evals.py::test_a_gate_sets_shards_are_drawn_by_the_homes_salt_and_merged_by_their_counts_alone` |
| The Release's gate judges a gate set named in the configuration by every completed dispatch on the commit | `tests/test_release_step.py::test_a_gate_set_is_judged_by_every_dispatch_on_the_commit` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
