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

- A Lens's thread takes its ruling from that Lens's own record too (issue 389): the result, accepted or rejected, of
  its latest Run that ruled on the thread, by when the Run started. None where no Run of the Lens ruled on it, where
  that latest Run ruled on it twice, where a start cannot be read, or where the Lens is not the owner of the thread's
  category, as the category itself says. The queue App's resolution closes the thread on an accepted ruling alone.

A thread no Lens recorded, a person's or an outside reviewer's, is left as `adapters/threads.py` read it.

A later review supersedes a Lens's earlier records for the first rule (issue 347): a Lens Run that reviewed the change,
its Intent `review-change` and its conclusion success, whose `applied/1` was read whole, on the pull request's current
content, supersedes every Run of that Lens that started before it. A Run that failed or was cancelled reviewed
nothing, an adjudication re-reads Findings without reviewing the change, and a review whose record is past retention
cannot be read, so none of them supersedes. Its head is
the current head, at or after any earlier Run's, and no other order of heads can be read, so a Run on any other
content supersedes nothing. A thread every Run that recorded it is superseded need not be in the read: a fresh review
releases a pull request held by a thread that is gone, and raises the problem again on a thread of its own if it
stands. A thread the superseding Run also records is still held to its opener; the join is unchanged.
"""
from __future__ import annotations

import datetime
import re

from adapters import artifacts
from adapters.github import Unanswered

# A Run's start, as the records port reads it.
TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
REVIEW = "review-change"       # the Intent that reviews the change, and so may supersede an earlier review


def _finding(found: dict):
    """`(lens, key, category, severity)` of a Finding posted on a thread, or None for one on any other surface."""
    surface = found["surface"]
    if surface["type"] != "thread":
        return None
    return found["source"]["lens"], surface["key"], found["category"], found["severity"]


def recorded(transport, repo: str, runs, numbers: list, lenses: set, authority: dict) -> dict:
    """`{number: (threads, whole, read)}` for each open pull request numbered: `threads` maps each thread a Lens
    recorded to `{lens, category, severity, runs, ruling}`, the category and severity null unless one Finding of that
    Lens alone names it and the authority table gives the Lens that category, `lens` null when two Lenses recorded it,
    `runs` the Runs that recorded it, and `ruling` the Lens's latest (the module's rules); `read` is each Lens Run
    whose `applied/1` was read whole, `{lens, run, content_id, started_at, reviewed}`, `reviewed` whether it is a
    review that succeeded, which `held` reads for a later review. `runs` is the records port's list, `lenses` the model Lenses' names, `authority`
    `config/authority.json`."""
    whole = isinstance(runs, dict) and runs.get("complete") is True
    ids = runs.get("github_ids") if whole else None
    out = {n: ({}, whole and isinstance(ids, dict), []) for n in numbers}
    if not out or not whole or not isinstance(ids, dict):
        return out
    found = {n: {} for n in numbers}
    ruled = {n: {} for n in numbers}
    read = {n: [] for n in numbers}
    for record in runs["runs"]:
        item = record["item"]
        if record["status"] != "completed" or record["role"] not in lenses or item["type"] != "pull_request" \
                or item["repo"] != repo or item["number"] not in out:
            continue
        number, named = item["number"], ids.get(record["run"])
        if not (isinstance(named, list) and len(named) == 1):
            out[number] = ({}, False, [])
            continue
        try:
            # A Run that succeeded uploaded its record whatever it wrote: one it no longer lists was deleted.
            done, read_whole = artifacts.applied(transport, repo, named[0], record["run"],
                                                 required=record["conclusion"] == "success")
        except Unanswered:
            done, read_whole = None, False
        if not read_whole:
            out[number] = ({}, False, [])
            continue
        for posted in (done or {}).get("findings", ()):
            if posted["source"]["lens"] != record["role"]:
                # A Run that records another Lens's Finding, on any surface, contradicts itself: none of it is read.
                out[number] = ({}, False, [])
                break
            held = _finding(posted)
            if held is not None:
                found[number].setdefault(held[1], []).append(held + (record["run"],))
        for ruling in (done or {}).get("rulings", ()):
            ruled[number].setdefault(ruling["thread"], []).append(
                (record["role"], record["run"], record.get("started_at"), ruling["result"]))
        read[number].append({"lens": record["role"], "run": record["run"], "content_id": record.get("content_id"),
                             "started_at": record.get("started_at"),
                             "reviewed": record.get("intent") == REVIEW and record.get("conclusion") == "success"
                             and done is not None})
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
            threads[key] = {"lens": lens, "category": category, "severity": severity,
                            "runs": sorted({h[4] for h in held}),
                            "ruling": _ruling(ruled[number].get(key, []), lens) if category is not None else None}
        out[number] = (threads, True, read[number])
    return out


def _start(when):
    """A Run's start as the records port reads it, or None where it is no moment."""
    if not isinstance(when, str) or not TIME.fullmatch(when):
        return None
    try:
        datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return when


def _ruling(rulings: list, lens):
    """The result of `lens`'s latest Run that ruled on a thread, of `rulings`, `(lens, run, started_at, result)`; None
    where it made none, where its latest Run ruled twice, or where any of its starts cannot be read."""
    mine = [r for r in rulings if r[0] == lens]
    if not mine or any(_start(r[2]) is None for r in mine):
        return None
    latest = max(r[2] for r in mine)
    last = [r for r in mine if r[2] == latest]
    return last[0][3] if len(last) == 1 else None


def superseded(read: list, content_id) -> set:
    """The Runs a later review of their own Lens supersedes: each that started before a review of that Lens that
    succeeded, read whole, on the pull request's current content `content_id`. A start that cannot be read, or no
    current content, supersedes nothing."""
    def start(r):
        return _start(r.get("started_at"))
    if not isinstance(content_id, str) or not content_id:
        return set()
    fresh = [r for r in read if r.get("reviewed") is True and r.get("content_id") == content_id
             and start(r) is not None]
    return {r["run"] for r in read if start(r) is not None
            and any(f["lens"] == r["lens"] and f["run"] != r["run"] and start(f) > start(r) for f in fresh)}


def held(found: list, whole: bool, recorded_: tuple, content_id=None) -> tuple:
    """`(threads, whole)`: the threads read with each Lens thread's category and severity joined from its Finding, and
    whole only when the read was and every recorded thread is in it, opened by the Lens that recorded it, but for one
    every Run that recorded it is superseded by a later review of its Lens on `content_id`, the current content."""
    threads, recorded_whole = recorded_[0], recorded_[1]
    later = superseded(recorded_[2] if len(recorded_) > 2 else [], content_id)
    whole = whole and recorded_whole
    by_id = {th["id"]: th for th in found}
    for key, finding in threads.items():
        if finding.get("runs") and all(run in later for run in finding["runs"]):
            continue
        th = by_id.get(key)
        if th is None or th["opened_by"] != {"kind": "lens", "name": finding["lens"], "can_write": False}:
            whole = False
    joined = []
    for th in found:
        finding = threads.get(th["id"])
        if th["opened_by"]["kind"] == "lens" and finding is not None and finding["lens"] == th["opened_by"]["name"]:
            th = dict(th, category=finding["category"], severity=finding["severity"], ruling=finding.get("ruling"))
        joined.append(th)
    return joined, whole
