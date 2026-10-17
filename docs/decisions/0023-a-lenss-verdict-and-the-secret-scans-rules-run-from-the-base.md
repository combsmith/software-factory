# 0023. A Lens's verdict and the secret scan's rules run from the base

Status: accepted. Decided by the Maintainer on 2026-10-17, who shrank
"Run each deterministic Lens from the base's inputs" (issue 137) to the secret scan's rules and the
verdict of `verify`, kept every Lens input on the list, and accepted the cost below.

## Decision

Two things a deterministic Lens reads come from the base of the change it judges, never from its
head. The base is the pull request's base commit, `github.event.pull_request.base.sha`, or, in the
merge queue, the commit the entry's group is built on, `github.event.merge_group.base_sha`. The
secret scan, which also runs on a push to `main`, takes the commit pushed, `github.sha`, there. The
base is checked out by the same pinned `actions/checkout`, with `persist-credentials: false`: no new
action, and no git in a `run:` line. A commit that cannot be fetched fails the checkout.

- The secret scan reads its rules, `.gitleaks.toml` and `.gitleaksignore`, from a second checkout,
  of the base into the directory base, through `--config base/.gitleaks.toml` and
  `--gitleaks-ignore-path base/.gitleaksignore`. gitleaks 8.30.1 also reads the `.gitleaksignore`
  at the top of `--source`, whatever the flag names, so the step deletes the head's copy on the line
  before. The history it scans is still the head's, with two things the head writes taken from it:
  `--log-opts` keeps gitleaks' own log options and adds `--text`, so a file the head's
  `.gitattributes` marks `-diff` is read and not passed over as binary; and
  `--ignore-gitleaks-allow` makes an inline `gitleaks:allow` in the content pass over nothing.
- `verify`, the job that judges the jobs it needs, checks out the base and nothing else, and runs
  the base's `tools/needs_passed.py`. A workflow with such a job runs on `pull_request` and
  `merge_group` alone, the only events that give a base. The checks, the tests and the mutants, in
  the jobs `checks` and `mutants`, still run from the head.

`.github/workflows/ci.yml` now differs from the org's text in a second thing besides the download held
to HTTPS: the checkout of the base, the deleted ignore file and the four flags. It is held to its new
text by its hash, and `tools/check_workflows.py` holds it to reading its rules from the base.

No entry comes off `lens_inputs` in `config/hooks.json`. A change to a Lens's inputs still converges
only once every model Lens has reviewed its head (decision 0020).

## Why

What a read from the base buys is a verdict the change cannot forge. Whatever rules the base's
configuration holds, a head can no longer loosen them for itself: an ignore entry, an allowlist
widened, an inline `gitleaks:allow` or a `.gitattributes` that hides a file counts for nothing until
it is merged, and judged as a change of its own. A head that made `tools/needs_passed.py` exit 0
would pass `verify` with every shard failing; the verdict is now the base's.

A judging workflow is held to its two events, rather than given a fallback that fails the job, because
the check reads the triggers from the text and refuses the workflow before it runs; on any other
event `ref:` comes out empty, and `actions/checkout` then checks out the head without a word.

Nothing comes off the list because here nothing would save a review. The list matters only for a
dependency update its bot pushed, the one class that otherwise needs no model review, and in this
repo that bot edits only pins under `.github/`, which is protected whatever the list says. The secret
scan's rules stay on it: a change to them changes the Lens on purpose, and though from the base it
cannot pass itself, once merged it judges every change after it. The inputs of `verify` stay because
its checks and tests stay on the head, where they are this repo's product. The base's tests cannot
test a rule the head adds, and fail a change made on purpose; the base's mutants are text matched
against lines the head changed, and go stale; and a check loosened on purpose would fail its own
change. Running `python3 -m tools.verify` in place of `make verify` would drop the Makefile from the
list, saves no review, and splits the documented command from the check.

The cost, accepted by the Maintainer: a false positive of the secret scan takes two merges, the
allowlist first and then the content; and `.github/workflows/ci.yml` departs further from the org's text. The org's
push-protection standard could take the read from the base, which would end that departure.

In the merge queue the base is `merge_group.base_sha`, which GitHub's webhook schema calls the SHA of
the merge group's parent commit: `main`, or the head of the group ahead of this one. That is what
`main` will be when the entry merges, and each entry ahead was judged as its own. The queue's
branches here agree:
"Session hooks: harden the ask hook against the remaining spellings" (pull request 92), queued behind
"Kernel: what takes a pull request out of the merge queue" (pull request 93), was built on the head
of the group ahead, and its branch was named for that commit. The value the event carries is a
platform fact, unverified until trial P-37 grounds it.

## Boundaries

| Boundary | Check |
|---|---|
| The secret scan's one job runs, in this order and nothing else, the head's checkout, the base's into the directory base, at the base on a pull request, in the merge queue and on a push, the install, which names no base, and the scan, with no environment, directory or container of its own; the scan's whole block, and every gitleaks the workflow runs, in a command string or on one line too, is told the base's `.gitleaks.toml` and `.gitleaksignore`, on the line after the head's `.gitleaksignore` is deleted, reads every file as text with gitleaks' own log options, and ignores an inline `gitleaks:allow` | `tests/test_tools.py::test_the_secret_scan_reads_the_bases_configuration` |
| `.github/workflows/ci.yml` is held to its text by its hash, and exempt from the rule on installs alone | `tests/test_tools.py::test_an_exempt_workflow_is_held_word_for_word` |
| A Lens's job that judges what it needs checks out the base, on a pull request and in the merge queue, with `persist-credentials: false` and nothing else, as its one checkout; its workflow runs on no other event | `tests/test_tools.py::test_a_lens_job_that_judges_its_needs_runs_from_the_base` |
| Every Lens input stays on the list, the secret scan's rules and the inputs of `verify` among them | `tests/test_tools.py::test_each_lens_input_is_a_required_lens_and_verifys_cover_every_check` |
