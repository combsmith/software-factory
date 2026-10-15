# config/

The Factory's settings, as data: `defaults.json` for the Kernel's limits and required Lenses (a
deterministic Lens is named for the check GitHub reports: `verify`, `secret-scan`, `code-scanning`;
only a dependency update may be judged without a model Lens),
`authority.json` for who owns each category of Finding, `rubric-pr-review.json` for what a review
must look at, `apps.json` for each GitHub App's permissions and the repos it is installed on, which the
Maintainer registers each App from.

| Rule | Held by |
|---|---|
| A new file here is added to `LIVE` in `tools/check_examples.py`, with its schema | `tools/check_examples.py` |
| Every limit the Kernel reads is in `defaults.json`; the Kernel writes no number of its own | `tests/test_tools.py::test_a_limit_written_into_the_kernel_is_caught` |
| The author Role owns no category, and security is never accepted as declined or deferred | `tools/check_authority.py` |
| Every need in `apps.json` maps to one permission and level, or says what it waits on. An App holds a permission only for a need mapped to it, never for a waiting one; a write need has one App; the reader writes nothing | `tools/check_apps.py` |
| A value held in two files agrees | `tests/test_tools.py::test_a_value_held_twice_must_agree` |
| The rubric is the review standard. Add a criterion there; no document describes the review | `tests/test_tools.py::test_a_second_copy_of_the_review_standard_is_caught` |
| JSON, with each key written once | `tests/test_tools.py::test_a_key_written_twice_is_refused` |
