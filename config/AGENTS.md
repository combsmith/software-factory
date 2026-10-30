# config/

The Factory's settings, as data: `defaults.json` for the Kernel's limits and required Lenses (a
deterministic Lens, `verify`, `secret-scan` or `code-scanning`, names the exact name of the check run
GitHub reports for it and the id of the one App whose check it is read from; only a dependency update
may be judged without a model Lens), for the Lens whose check alone reports each kind of acceptance criterion,
and for the one name of the status on the item,
`authority.json` for who owns each category of Finding, `rubric-pr-review.json` for what a review
must look at, `apps.json` for each GitHub App's permissions and the repos it is installed on, which the
Maintainer registers each App from, `hooks.json` for the Maintainer, whose name every commit and push here carries,
and for what the session hooks ask the person about (the protected paths, merging, the repo's settings,
a session started with no one asked) or list at a stop, `feed.json` for who acts next and what is asked of a person, read from a Decision's codes,
`controller.json` for what the Controller's pass is told beside it: the accounts that tell what started a pass, the gaps, the automatic pause and the thresholds,
and `rulesets.json` for the repo's rulesets as GitHub answered the Maintainer's read of them, which `tools/rulesets_drift.sh` compares with the live ones by hand.
Its protected paths and each Lens's inputs are also the Kernel's `protected_paths`: a change to one is reviewed by every model Lens.

| Rule | Held by |
|---|---|
| A new file here is added to `LIVE` in `tools/check_examples.py`, with its schema | `tools/check_examples.py` |
| Every limit the Kernel reads is in `defaults.json`, but a Lifecycle's staleness limits, never copied here | `tests/test_tools.py::test_a_limit_written_into_the_kernel_is_caught`, `examples/invalid/config.a-staleness-limit-copied-from-the-lifecycle.json` |
| The author Role owns no category, and security is never accepted as declined or deferred | `tools/check_authority.py` |
| Each deterministic Lens names its check and its App | `examples/invalid/config.a-required-lens-with-no-app.json`, `examples/invalid/config.a-required-lens-with-no-check.json` |
| No Lens or check is named twice | `tests/test_tools.py::test_a_lens_or_a_check_named_twice_is_refused` |
| The status on the item never carries a required Lens's or check's name | `tests/test_tools.py::test_the_status_on_the_item_never_carries_a_required_lens_name` |
| Every need in `apps.json` maps to one permission and level, or says what it waits on. An App holds a permission only for a need mapped to it, never for a waiting one; a write need has one App; the reader writes nothing | `tools/check_apps.py` |
| A value held in two files agrees | `tests/test_tools.py::test_a_value_held_twice_must_agree` |
| `feed.json` has one row for each reason the Kernel gives `needs_you`, and one rule for each attention class | `tests/test_tools.py::test_every_reason_that_needs_a_person_says_what_is_asked` |
| The rubric is the review standard. Add a criterion there; no document describes the review | `tests/test_tools.py::test_a_second_copy_of_the_review_standard_is_caught` |
| The protected paths and each Lens's inputs are one list, in `hooks.json`, the Kernel's too, matched as the hooks match | `tests/test_tools.py::test_the_kernels_matcher_and_the_hooks_agree_on_one_corpus` |
| In `rulesets.json`, CodeQL fails on a security alert of any severity, and a thread left open holds a merge | `examples/invalid/rulesets.a-security-alert-below-high-passes.json`, `examples/invalid/rulesets.a-thread-left-open-merges.json` |
| Nobody bypasses `main`, and only the admin role, whoever holds it, moves a `factory/*` tag | `examples/invalid/rulesets.main-with-a-bypass.json`, `examples/invalid/rulesets.a-release-tag-a-writer-may-move.json` |
| Each check `main` requires is a deterministic Lens's, pinned to that Lens's App; `verify` is among them; each code-scanning tool is a Lens no workflow runs | `tools/check_rulesets.py` |
| An approval `main` counts is exactly one, a code owner's, of the last push, a stale one dismissed, and `.github/CODEOWNERS` names only the machine user's team on every path (decision 0092) | `tools/check_rulesets.py` |
| JSON, with each key written once | `tests/test_tools.py::test_a_key_written_twice_is_refused` |
