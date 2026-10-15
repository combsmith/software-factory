# config/

The Factory's settings, as data: `defaults.json` for the Kernel's limits and required Lenses (a
deterministic Lens, `verify`, `secret-scan` or `code-scanning`, names the exact name of the check run
GitHub reports for it and the id of the one App whose check it is read from; only a dependency update
may be judged without a model Lens) and for the one name of the status on the item,
`authority.json` for who owns each category of Finding, `rubric-pr-review.json` for what a review
must look at, `apps.json` for each GitHub App's permissions and the repos it is installed on, which the
Maintainer registers each App from, `hooks.json` for the Maintainer, whose name every commit and push here carries,
and for what the session hooks ask the person about (the protected paths, merging, the repo's settings) or list at a stop.

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
| The rubric is the review standard. Add a criterion there; no document describes the review | `tests/test_tools.py::test_a_second_copy_of_the_review_standard_is_caught` |
| JSON, with each key written once | `tests/test_tools.py::test_a_key_written_twice_is_refused` |
