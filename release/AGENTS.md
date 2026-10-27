# release/

How the Factory ships itself. `rings.json` names the two Channels, what each serves, and the evidence a Release needs
from `next` before it reaches `stable`. `cut.py` holds the rules that cut a Release and move or roll back a Channel,
pure: it is given the refs and the facts, and returns the writes or one code. `current.py` names a commit's one
Release. `move.py` prints a step's plan from what was read, and runs the step: it sends each write, reads it back and records the Deployment. The
tags themselves are read by `adapters/tags.py`; `fixtures/` keeps what GitHub answered a Release's reads and steps. How to cut, and who may, is the skill `.claude/skills/cut-a-release/SKILL.md`.
Not built yet, by the stories that hold their rules: promote.py, cutover.py, fixtures/cut.v0-1-0.json.

| Rule | Held by |
|---|---|
| A Release is cut only from a verified commit of `main`, newer than every Release, of the Channel's major | `tests/test_release.py::test_each_rule_of_a_cut_refuses_with_its_own_code` |
| `next` moves only through the eval gate, judged for that Release and read before anything is written | `tests/test_release.py::test_a_closed_eval_gate_refuses_every_cut_and_move_and_burns_no_version` |
| A step moves only a Channel the ring file declares, to a commit one Release names alone | `tests/test_release.py::test_only_a_channel_the_ring_file_declares_is_moved`, `tests/test_release.py::test_a_channel_moves_only_to_a_commit_one_release_names_alone` |
| No step writes a Release tag | `tests/test_release.py::test_no_step_writes_a_release_tag_and_none_names_anything_but_a_channel` |
| No step moves `stable` until promotion is built | `tests/test_release.py::test_stable_is_never_moved_until_promotion_is_built` |
| A rollback passes no gate and moves only back | `tests/test_release.py::test_a_rollback_passes_no_gate_and_never_moves_forward` |
| By default it moves to the greatest Release below | `tests/test_release.py::test_a_rollback_by_default_takes_the_greatest_release_below_the_one_next_is_on` |
| A commit's Release is its one Release tag; a Channel never is one, and two are none | `tests/test_release.py::test_a_commit_with_no_release_or_two_resolves_to_none` |
| The rules import nothing but each other | `tools/check_release.py` |
| No repo and Intent family is served by two Channels | `examples/invalid/rings.a-repo-on-two-channels.json` |
| A Release reaches `stable` only with Runs behind it, each Effect read back, and an eval for each changed Intent | `examples/invalid/rings.promotion-with-no-runs.json`, `examples/invalid/rings.promotion-without-evals.json` |
| The tags are read whole or not at all, and nothing is read at any tag | `tests/test_release.py::test_tags_are_read_whole_or_not_at_all`, `tests/test_release.py::test_a_move_reads_refs_and_nothing_at_any_tag` |
| Each page GitHub links is read, of this list alone and to a bound | `tests/test_release.py::test_each_page_github_links_is_read_and_only_this_lists` |
| A fixture holds no credential, and no header a trial's fixture drops | `tests/test_release.py::test_the_refs_github_answered_are_read_as_the_port_reads_them` |
| The step sends each write through the token it is given, reads it back, and records each move of `next` | `tests/test_release_step.py::test_a_cut_creates_the_release_moves_next_reads_each_back_and_records_the_deployment` |
| It stops at the first write GitHub refused, or not read back, read twice, on its commit as the one Release planned | `tests/test_release_step.py::test_a_write_not_read_back_stops_the_step_there` |
| The eval gate is closed by anything not read whole, or not the eval job's own pass for the commit and Release | `tests/test_release_step.py::test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed` |
| `verify` counts only as GitHub Actions' one success on the commit | `tests/test_release_step.py::test_verify_counts_only_as_github_actions_one_success_on_the_commit` |
| A commit counts as on `main` only by GitHub's comparison of it with `main`'s head, read by its branch's ref | `tests/test_release_step.py::test_the_facts_of_a_commit_on_main_verified_and_judged` |
| A move forward is gated for the Release it moves to | `tests/test_release_step.py::test_a_move_forward_reads_the_facts_of_the_release_it_moves_to` |
| A rollback reads no fact of the commit it moves to | `tests/test_release_step.py::test_a_rollback_reads_no_fact_and_moves_next_back` |
| A Release is never written twice; a Channel is created once and moved with force after | `tests/test_release_step.py::test_a_release_is_created_and_a_channel_created_once_then_moved_with_force` |
| A Deployment counts only as one of the commit moved to, its status success | `tests/test_release_step.py::test_a_deployment_of_next_is_recorded_with_its_status` |
| Only `.github/workflows/release.yml` runs the step, held to its shape: one job on `factory-release`, its token for this repo alone, no checkout an output names | `tests/test_release_workflow.py::test_each_counter_example_is_refused_for_its_one_fault` |
| No other workflow names the release job's environment, key, token or step | `tests/test_release_workflow.py::test_only_release_yml_names_the_release_jobs_environment_key_token_or_step` |
| A cut asked with no version, as the schedule asks one, is of the next patch of its major | `tests/test_release_workflow.py::test_a_cut_asked_with_no_version_is_of_the_next_patch_or_the_majors_first` |
