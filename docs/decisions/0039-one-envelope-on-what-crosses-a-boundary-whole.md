# 0039. One envelope, on what crosses a boundary whole

Status: accepted. Taken as a working ruling on 2026-10-18, which the Maintainer may overturn in review, for
"Schemas for the Role manifest, the pass record and the feed; and one envelope for all" (issue 28). It reads §3.1 of the
design differently from its words, which said every message carries `schema`, an identifier and the `release` that
produced it, and amends §3.1, §3.4, §3.7, §3.10 and §8.4 in the same change.

## Decision

The envelope is carried by what crosses a boundary whole, once, and everything inside it is versioned by it. Each
schema is in exactly one of four classes, held in `ENVELOPE` in `tools/check_examples.py`. A document crosses a
boundary whole, written by a Release at run time, and requires `schema`, its identity and `release`: `task`, `result`,
`applied` and `outcome`, identity `run`, and `pass`, `view-meta` and `view-items`, identity `pass`, minted by the
Controller as it mints `run`. A record travels inside a document and is also given alone to a reader, and requires
`schema` alone: `facts`, `issue-facts`, `decision`, `issue-decision` and `finding`, which keeps its `id`. A part is only
ever inside another, by reference, and has no `schema` field: `effect`, `disposition`, `coverage`, `run-name`,
`run-record` and `view-item`. A data file a person edits requires `schema`, its path being its identity and the commit
its Release: `config`, `hooks`, `lifecycle`, `authority`, `apps`, `rubric`, `acceptance`, `trial`, `role` and `feed`.
`schema` is a `const` naming the file's own kind and a major version; a document's `release` is the Factory's release
pattern and its identity's pattern is anchored at both ends; a record or a data file has no `release`. `config` and
`hooks` gain `schema` so, and their files with them.

The pass record, `pass/1`, is what replay needs and nothing else: the time the pass gave the Kernel, the whole context
with every key always present, every run record read once for the pass, each read's GitHub `date` and `age`, and, in
one list for pull requests and one for issues, each item's facts, its Decision and the Run id minted for an admission
or an approval, or null. The configuration is not copied: it is the data at `release`, and the example record replays
with the repository's own `config/defaults.json` and Lifecycles. A Decision carries no id and no Release of its own.

The feed's two files, `view-meta/1` and `view-items/1`, carry the pass that wrote them. An item is a part whose
`state` and `attention` are the union of the two Decisions' codes, with `next_actor`, `decision_required`,
`content_id`, `age_hours`, `attempts` as a list of `{intent, count}`, `runs`, `cost_usd`, `sources`, `url` and
`untrusted`. The item's title is the one text on the feed, held under `untrusted`, and never in the facts: `facts/1`
and `issue-facts/1` have no field for it, so neither the Kernel nor a replay sees one. In what one Run carries, and in
what is written from it, a string is a code unless it is a property named `body` or sits under one named `untrusted`;
a body is one string, and only the feed marks text untrusted. A reference into a kind outside that set is held by
that kind's own rules: the facts, the Decisions and `finding/1` are the Factory's own records, with free identifiers
the Kernel only compares, and they are not swept here; a run record is held to codes, since a pass record carries it.
A part carries no `release` either, and a document's identity and release are strings. `config/feed.json` is a
protected path, as every other file in `config/` is, so a change to it is reviewed by every model Lens.

`next_actor` and `decision_required` are read from the Decision's codes through `config/feed.json`, `feed/1`, and
from nothing else: by outcome first, a Decision about to admit or act being the Factory's; then by attention class;
and `review`, `ready` and `stale` by State, with a default. `decision_required` is null unless the attention is
`needs_you`; then the table's row for the reason gives `question` and `choices`, each a code, a choice being something
a person does in GitHub, and `evidence` is the Decision's. The table has one row for each reason the Kernel gives
`needs_you`: its two `NEEDS_YOU_REASONS` sets, and `paused`, `pause_unreadable` and `unmerged_closes`, which the Kernel
gives `needs_you` outside them. `tools/check_examples.py` holds the table to the Kernel, and holds every attention
class to one rule.

`applied/1`, uploaded by `apply`, lists each Effect met, in the order applied, as `{id, type, state, key, reason}`,
and the `finding/1` of each Finding posted, with its surface's key as read back. `outcome/1` is the run record's
outcome code, null for a Run that succeeded, and a reason code. Neither holds text. `role/1` holds a Role manifest as
data, as §3.11 shows it, each Intent with a tier, its permitted Effects, a budget class and an eval set, which is
required. `tools/check_authority.py` holds what a manifest owns, shadows and raises to the Finding's categories.

## Why

Taken literally, §3.1 reached too far. The Kernel can mint neither an id nor a Release for a Decision: it reads no
clock and keeps nothing. `coverage/1` is an array and cannot carry fields. An Effect and a Disposition travel only
inside a Result, which already says which Run and which Release. One fact, one place (decision 0009): a Decision's
Release is its pass's, and a copy in every record is a copy that can disagree. A data file keeps `schema` because an
acceptance contract or a Consumer entry is read by whichever Release serves it, and one rule is easier to hold than
two. The pass record carries the Run id because the Harness finds the Decision that admitted a Run by that id, and the
record is the only place the two meet. Two lists, not one, because without `oneOf` only two lists can say that a pull
request's facts go with a pull request's Decision. The title sits under `untrusted` so that whatever reads the feed
sees it marked, and a reader that feeds a model drops it whole. Who acts next and what is asked are functions of codes
the Decision already holds, so they are a table, not Kernel output: output would be a second copy of the same answer,
and `kernel/` is where every new field costs a boundary test and a mutant; and `controller/`, which will apply the
table, is a reserved path, so the table is data now.

## Boundaries

| Boundary | Check |
|---|---|
| Every schema is in one class, and every class names a schema; a document requires its identity and release, with the release pattern and an anchored identity; a record or a data file requires `schema` and has no release; a part has no `schema`; the const names the kind | `tests/test_tools.py::test_a_schema_without_its_envelope_is_caught` |
| A string under `untrusted` passes, and the same string beside it is caught; the feed's one text is the title | `tests/test_tools.py::test_text_is_let_through_only_untrusted_or_in_a_body` |
| Every Decision in the example pass record is the Kernel's own answer on what the record holds, with the repository's data files; a Run id stands beside an admission and nowhere else | `tests/test_tools.py::test_the_example_pass_record_replays` |
| The pass record's context has exactly the keys every Kernel test is given, all required | `tests/test_tools.py::test_the_pass_record_holds_the_kernels_whole_context` |
| A feed item's State and attention are what the two Decisions can say, and its reason the same code | `tests/test_tools.py::test_the_feed_shows_only_what_a_decision_can_say` |
| The table has one row for each reason the Kernel gives `needs_you`, none for another, one rule for each attention class, and no State or outcome ruled twice; `paused`, `pause_unreadable` and `unmerged_closes` are shown to need a person | `tests/test_tools.py::test_every_reason_that_needs_a_person_says_what_is_asked` |
| A manifest's categories are the Finding's | `tests/test_tools.py::test_a_manifest_with_a_category_nobody_owns_is_caught` |
| Each item of the example feed carries the next actor and the decision required the table gives its Decision's codes, and the table's rules are the design's: a Decision about to admit or act is the Factory's, then by class, then by State | `tests/test_tools.py::test_the_example_feed_follows_the_table` |
| The facts have no field for a title | `examples/invalid/facts.carries-the-title.json`, `examples/invalid/issue-facts.carries-the-title.json`, `examples/invalid/facts.carries-prose.json` |
| A pass record with no release, a Decision without its facts, a context without the Pause, or a Run id in another form is refused | `examples/invalid/pass.no-release.json`, `examples/invalid/pass.a-decision-without-its-facts.json`, `examples/invalid/pass.a-context-without-the-pause.json`, `examples/invalid/pass.a-run-id-in-another-form.json` |
| The feed's files are refused with no pass, a time in another format, a title not marked untrusted, a sentence as a reason, a choice no person can make, a next actor in words, or no release | `examples/invalid/view-meta.no-pass.json`, `examples/invalid/view-meta.time-in-another-format.json`, `examples/invalid/view-items.a-title-not-marked-untrusted.json`, `examples/invalid/view-items.sentence-as-reason.json`, `examples/invalid/view-items.a-choice-no-person-can-make.json`, `examples/invalid/view-items.a-next-actor-in-words.json`, `examples/invalid/view-items.no-release.json` |
| The table refuses a choice no person can make and a question in words | `examples/invalid/feed.a-choice-no-person-can-make.json`, `examples/invalid/feed.a-question-in-words.json` |
| `applied/1` refuses a comment body, an Effect read back in words and a record with no run; `outcome/1` a fault the design does not know, a sentence as a reason and no release | `examples/invalid/applied.carries-the-comment-body.json`, `examples/invalid/applied.an-effect-read-back-in-words.json`, `examples/invalid/applied.no-run.json`, `examples/invalid/outcome.a-fault-the-design-does-not-know.json`, `examples/invalid/outcome.sentence-as-reason.json`, `examples/invalid/outcome.no-release.json` |
| A manifest with a kind the design does not know, a permitted Effect a Result cannot request, an Intent with no eval set or a tier the Engine does not know is refused | `examples/invalid/role.a-kind-the-design-does-not-know.json`, `examples/invalid/role.a-permitted-effect-a-result-cannot-request.json`, `examples/invalid/role.an-intent-with-no-eval-set.json`, `examples/invalid/role.a-tier-the-engine-does-not-know.json` |
| The facts port returns the title beside the facts, never in them, from the same query | `tests/test_adapters.py::test_the_pull_requests_own_facts_and_the_title_beside_them` |
| Every pass uploads a `pass/1` with every key of the context, every run record and every read's `date` and `age`; the Controller mints `pass` and `run`, and writes `run` beside the Decision that admitted it | waiting on `controller/` |
| The feed's two files are written by one pass, carrying its id; `next_actor` and `decision_required` are read from `config/feed.json` and from nothing else | waiting on `controller/` |
| `apply` uploads `applied/1` with every Effect it met and every Finding it posted, and a final step writes `outcome/1` | waiting on `harness/` |
| The records port reads a Run's `outcome/1` only for a Run that did not succeed | waiting on `adapters/artifacts.py` |
| A shadow's Intents permit no Effect and spend from `shadow`; an owner's `owns` agrees with `config/authority.json`; a Role's `name` is its file's; the manifests join `LIVE` | waiting on `roles/` |
