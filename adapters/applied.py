"""What each Lens recorded on a pull request: the Findings in every completed Run's `applied/1` of a model Lens, read
by the Run's GitHub id, and held against the threads read (design section 3.3, decisions 0038 and 0069, issue 338).

`recorded` reads them. A Run counts when the records port names it, by its run-name, completed, a model Lens's, on an
open pull request of the home repo; its `applied/1` is read through `adapters/artifacts.py`, whatever its conclusion,
since a write may have landed before a later one failed. A Finding it posted on a thread is kept by that thread's id,
its surface key. The list of a pull request's Findings is whole only when the run list was read whole, each counted
Run is named by one GitHub run, and each `applied/1` was read whole and holds no Finding of another Lens than its
Run's. An `applied/1` past the artifact retention is read as none, whole, as an expired outcome is (decision 0049):
the accepted miss decision 0069 names. A Run that succeeded uploaded one whatever it wrote, so one it lists none of was
deleted, and is not whole; a Run that did not succeed may have uploaded none. What else cannot be read is not whole,
never none.

`held` holds the threads read to them, by two rules.

- Every thread a Lens recorded must be in the read, and still opened by that Lens, told by its account
  (`adapters/timeline.Accounts`, decision 0067). GitHub keeps a thread's id when its first comment is deleted, and
  reads its reply as its first comment (trials/P-49.json), so a deletion shows as an opener that is now someone
  else, and a thread that is gone as a missing one. Either leaves the threads read not whole, and the Kernel defers.
  The Lens's own reply read as the opener is still the Lens's: the thread gates, though its Finding's text is lost.
- A Lens's thread takes its category and severity from that Lens's one Finding on it, never from its text. One that
  matches none, matches two, or names a category the authority table does not give that Lens has neither, and the
  Kernel defers on a required Lens's open thread as it does today (`kernel/derive.py`'s `unreadable_thread`).

A thread no Lens recorded, a person's or an outside reviewer's, is left as `adapters/threads.py` read it.
"""
from __future__ import annotations

from adapters import artifacts
from adapters.github import Unanswered


def _finding(found: dict):
    """`(lens, key, category, severity)` of a Finding posted on a thread, or None for one on any other surface."""
    surface = found["surface"]
    if surface["type"] != "thread":
        return None
    return found["source"]["lens"], surface["key"], found["category"], found["severity"]


def recorded(transport, repo: str, runs, numbers: list, lenses: set, authority: dict) -> dict:
    """`{number: (threads, whole)}` for each open pull request numbered: `threads` maps each thread a Lens recorded to
    `{lens, category, severity}`, the category and severity null unless one Finding of that Lens alone names it and
    the authority table gives the Lens that category; `lens` null when two Lenses recorded it. `runs` is the records
    port's list, `lenses` the model Lenses' names, `authority` `config/authority.json`."""
    whole = isinstance(runs, dict) and runs.get("complete") is True
    ids = runs.get("github_ids") if whole else None
    out = {n: ({}, whole and isinstance(ids, dict)) for n in numbers}
    if not out or not whole or not isinstance(ids, dict):
        return out
    found = {n: {} for n in numbers}
    for record in runs["runs"]:
        item = record["item"]
        if record["status"] != "completed" or record["role"] not in lenses or item["type"] != "pull_request" \
                or item["repo"] != repo or item["number"] not in out:
            continue
        number, named = item["number"], ids.get(record["run"])
        if not (isinstance(named, list) and len(named) == 1):
            out[number] = ({}, False)
            continue
        try:
            # A Run that succeeded uploaded its record whatever it wrote: one it no longer lists was deleted.
            done, read_whole = artifacts.applied(transport, repo, named[0], record["run"],
                                                 required=record["conclusion"] == "success")
        except Unanswered:
            done, read_whole = None, False
        if not read_whole:
            out[number] = ({}, False)
            continue
        for posted in (done or {}).get("findings", ()):
            if posted["source"]["lens"] != record["role"]:
                # A Run that records another Lens's Finding, on any surface, contradicts itself: none of it is read.
                out[number] = ({}, False)
                break
            held = _finding(posted)
            if held is not None:
                found[number].setdefault(held[1], []).append(held)
    owners = authority.get("categories", {}) if isinstance(authority, dict) else {}
    for number, by_key in found.items():
        if not out[number][1]:
            continue
        threads = {}
        for key, held in by_key.items():
            named = {h[0] for h in held}
            lens = named.pop() if len(named) == 1 else None
            category, severity = (held[0][2], held[0][3]) if len(held) == 1 else (None, None)
            if category is not None and (owners.get(category) or {}).get("owner") != lens:
                category, severity = None, None
            threads[key] = {"lens": lens, "category": category, "severity": severity}
        out[number] = (threads, True)
    return out


def held(found: list, whole: bool, recorded_: tuple) -> tuple:
    """`(threads, whole)`: the threads read with each Lens thread's category and severity joined from its Finding, and
    whole only when the read was and every recorded thread is in it, opened by the Lens that recorded it."""
    threads, recorded_whole = recorded_
    whole = whole and recorded_whole
    by_id = {th["id"]: th for th in found}
    for key, finding in threads.items():
        th = by_id.get(key)
        if th is None or th["opened_by"] != {"kind": "lens", "name": finding["lens"], "can_write": False}:
            whole = False
    joined = []
    for th in found:
        finding = threads.get(th["id"])
        if th["opened_by"]["kind"] == "lens" and finding is not None and finding["lens"] == th["opened_by"]["name"]:
            th = dict(th, category=finding["category"], severity=finding["severity"])
        joined.append(th)
    return joined, whole
