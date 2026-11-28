"""What judges a Role's change, which its push may not touch (record 0025's acceptance contract, lesson L-42; record
0004's Consumer clause, the Solution Architect's rulings of 2026-11-28 on the push's split, relayed by the Factory
Builder).

- `paths(contract, at)`: `(patterns, None)`, what the push of the Role that implements the work may not touch beside
  the base's list: the contract's own file `at`, each of its `protected_paths`, and the file of each criterion of kind
  `test`, its `ref` up to `::`, each once in that order; or `(None, UNREADABLE)` for a contract or a path of no shape
  read here. The patterns are in the syntax of `config/hooks.json`'s paths, as `protected_paths` are: the caller adds
  them to the base's list, so `harness/apply.py`'s `push_refusal` matches them as it matches the list, and refuses a
  list with a pattern it cannot read. The contract is the one a person approved, read from the issue at the commit
  of that approval (decision 0025), never from the head; `at` is where that read found it.
- `consumer(repo, own)`: None where the push is to `own`, the Factory's own repo, or `CONSUMER`: a Consumer's setup
  and test commands are its manifest's, which no port reads yet (`adapters/consumer.py`, not built). So every push to
  a Consumer's repo is refused until one does. The names are compared as given: one in another case is refused.

Its stated limits:
- What judges the Role and the contract does not name is not refused here: a fixture or a threshold a test reads is
  refused only where `protected_paths` names it, or the base's list does, as the Factory's own `config/` does.
- A `ref` with no `::` is taken whole as its file. One that is no path, a command among them, is a pattern the list's
  reader refuses, so every push is refused: it costs a push, never passes one.
- Which contract is the approved one, and that `None` means the issue asks for none, are the caller's: this is given
  a contract that was read.

The caller gives every argument; this reads nothing itself.
"""
from __future__ import annotations

UNREADABLE = "contract_unreadable"          # a contract, or where it was read, of no shape read here
CONSUMER = "consumer_manifest_unread"       # a push to a repo whose manifest no port reads yet

SCHEMA = "acceptance/1"
TEST = "test"
SEPARATOR = "::"


def _text(said) -> bool:
    return type(said) is str and bool(said)


def _check(criterion):
    """A criterion's `check` as `(kind, ref)`, or None where it is in no shape read here."""
    check = criterion.get("check") if type(criterion) is dict else None
    if type(check) is not dict or not _text(check.get("kind")) or not _text(check.get("ref")):
        return None
    return check["kind"], check["ref"]


def paths(contract, at) -> tuple:
    """`(patterns, None)`: the contract's file, its protected paths and each test it names, each once; or
    `(None, UNREADABLE)`."""
    schema = contract.get("schema") if type(contract) is dict else None
    if type(schema) is not str or schema != SCHEMA or not _text(at):
        return None, UNREADABLE
    protected, criteria = contract.get("protected_paths"), contract.get("criteria")
    if type(protected) is not list or not protected or not all(_text(path) for path in protected) \
            or type(criteria) is not list or not criteria:
        return None, UNREADABLE
    checks = [_check(criterion) for criterion in criteria]
    if None in checks:
        return None, UNREADABLE
    tests = [ref.partition(SEPARATOR)[0] for kind, ref in checks if kind == TEST]
    if not all(tests):
        return None, UNREADABLE
    out = []
    for path in [at] + protected + tests:
        if path not in out:
            out.append(path)
    return out, None


def consumer(repo, own):
    """None for a push to the Factory's own repo, `own`; `CONSUMER` for any other, or a name of no exact kind."""
    return None if _text(repo) and _text(own) and repo == own else CONSUMER
