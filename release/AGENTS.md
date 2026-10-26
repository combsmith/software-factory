# release/

How the Factory ships itself. `rings.json` names the two Channels, what each serves, and the evidence a Release needs
from `next` before it reaches `stable`. `cut.py` holds the rules that cut a Release and move or roll back a Channel,
pure: it is given the refs and the facts, and returns the writes or one code. `current.py` names a commit's one
Release. `move.py` prints a step's plan from what was read; the workflow that sends it is `.github/workflows/`'s. The
tags themselves are read by `adapters/tags.py`; `fixtures/` keeps what GitHub answered a Release's reads and steps. How to cut, and who may, is the skill `.claude/skills/cut-a-release/SKILL.md`.
Not built yet, by the stories that hold their rules: promote.py, cutover.py.

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
| A fixture holds no credential, and no header a trial's fixture drops | `tests/test_release.py::test_the_refs_github_answered_are_read_as_the_port_reads_them` |
