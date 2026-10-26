# 0068. A thread's resolver is told by its account, never by resolvedBy's type

Status: accepted. The Factory Builder's rulings of 2026-10-26 on
"Threads port: a thread's resolver is read from its timeline event, by id and type (P-49)" (issue 331), from trial P-49
("Platform trial: what GitHub gives the threads port", issue 282) and trial P-53. It extends decision 0005, that each
actor is told by its account id and type, and leaves it as it is: 0005's row on a thread's shape stays not held while
a thread whose first comment was deleted is read as before.

## Decision

| What | Decided | Because |
|---|---|---|
| A thread's resolver | `resolvedBy`'s account id is matched to the thread's comment author, whose type GraphQL gives; failing that, to the repo's permission read of `resolvedBy`'s login, which answers the account's id and type, held to the id. `resolvedBy`'s type is never read | GraphQL types `resolvedBy` a User whoever resolved the thread, an App among them (`trials/P-49.json`). No timeline item names a thread's resolution (`trials/P-53.json`). The permission read answers the account by id and type, a `Bot` for an App's bot, a `User` for a person (`trials/P-53.json`) |
| One that cannot be told | An id neither answers, a read that fails, an account of no type GitHub gives, or one whose access cannot be read leaves the resolver unread, and the rest of the threads read stands: the Kernel defers on the thread, never taking it for a User | Fail closed: a resolver taken for a person would close a Lens's thread |
| Another App | An App that is neither the thread's Lens nor a person is read as an App: the thread stays open under `kernel/gate.py`'s `closed`, and is not unreadable | Only a Lens's own App or a person closes a Lens's thread (L-17) |
| The cost | One permission read a login a pass, shared with the read of a person's write access, a read that failed or never answered among them | The pass reads one `Accounts` for all its pull requests |
| Reconciliation | What was seen tells a thread's resolver by its account id alone, among the Factory's identities, and a Role's resolution is matched to a `resolve_thread` Effect by the thread's id, recorded by a Run of that same Role, as the run records say (decision 0061) | An App's resolution, typed a User, was told by no identity, and an unrecorded one went unseen. A thread's id outlives its reopening, so one Role's recorded resolution must not cover another's |
| A deleted first comment | Not held here: GitHub keeps no link from the reply to the deleted comment or its review (`trials/P-53.json`). Every Finding comment a Lens's `applied/1` records must still be in the threads read, or the read is unreadable: issue 338 ("Threads port: a Lens's recorded Finding comment missing from the threads read leaves it unreadable"), blocked by the collector | A comparison with what an earlier pass kept would keep state between passes, and miss a deletion made before any pass saw the comment |

## Why

P-49 found that a Lens resolving its own thread, through `apply`, made the threads port refuse the whole read: it read
the resolver as a User, and a User's login has no `[bot]`. A person resolving a Lens's thread, which is how a person
closes one, matches no comment author when the person wrote none of the thread, so a type read from comment authors
alone would hold such a pull request for good; the permission read, which the port already makes for a person's write
access, answers the account by id and type, and costs no read more for a person.

## Boundaries

| Boundary | Check |
|---|---|
| An App's resolution is read as that App's, from P-49's records | `tests/test_adapters.py::test_an_apps_resolution_is_read_as_the_apps_by_its_comment_author` |
| A resolver is typed by its account, never by `resolvedBy`'s type: a person's resolution, the Lens's own, another App's, and one that cannot be told | `tests/test_adapters.py::test_a_resolver_is_typed_by_its_account_never_by_resolved_bys_type` |
| A resolver is read once a login, whatever it resolved | `tests/test_adapters.py::test_a_resolver_is_read_once_a_login_whatever_it_resolved` |
| An account is typed by the permission read only for the id asked | `tests/test_adapters.py::test_an_account_is_typed_by_the_permission_read_held_to_its_id` |
| A resolution is matched only to an Effect its own Role's Run recorded | `tests/test_reconcile.py::test_a_resolution_is_matched_to_the_role_whose_run_recorded_it` |
| Reconciliation tells a resolver by its account id, and matches a Role's resolution | `tests/test_reconcile.py::test_each_identitys_writes_are_read_by_its_account_never_its_login`, `tests/test_reconcile.py::test_each_write_is_matched_to_the_effect_that_recorded_it` |
| A Lens's recorded Finding comment missing from the threads read leaves it unreadable | not held yet: `tests/test_adapters.py::test_a_thread_a_trial_recorded_is_read_as_the_port_reads_it` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
