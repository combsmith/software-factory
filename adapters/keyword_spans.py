"""A closing keyword's link, timed by the passes that saw it: each linked pull request's `keyword_spans`, read from the
pass records before this pass (design sections 3.10 and 4.1; decision 0186).

GitHub gives a keyword's link no time (`trials/P-48.json`), so its only one is the Factory's own record of seeing it.
Each pass record holds each issue's facts, and so each pull request that pass listed, with its keyword as that pass read
it and its spans as the records before that pass gave them. The base is the newest record at hand that holds the
issue's facts with `complete.linked` true: it carries the whole history, one step short, the spans it holds and what its
own pass saw. What it saw is added here: a keyword it read, with no span open, opens one at the `read_at` of the issue's
facts in that record; a keyword it read gone, with a span open, ends that span at that `read_at`, and one put back later
opens a new span, which reaches back to nothing. Each record newer than the base that holds the issue, not whole, adds
openings alone: a keyword it read with no span open opens one at its `read_at`, and nothing is ended, since a list read
short may have missed a keyword.

The chain is broken, and the spans are not the whole history, where a record newer than the base, or any where there is
none, leaves the issue out (its `left_out` names the item, or an item it cannot name) or served no issue because their
Apps could not be told (its alert `issue_apps_unreadable`); or where records hold the issue but none of them whole. A
pass whose list of issues could not be read stops and writes no record (decision 0218). No record at hand that holds or
leaves out the issue, and none that raised that alert, is first sight: no pass saw a keyword, and the first that sees one
opens its span. So a record that holds no issue and leaves none out, with no `served_from` or none open, is first sight
too; and `served_from` set back to null and on again later loses the history between (decision 0186).

Only records the Factory itself wrote are read: the caller hands those `adapters/passes.py` read from the poller's own
runs and `controller/reads.py` held to `pass/1`, or None where they could not be read. Records that could not be read
give no time and are not whole: a pull request whose keyword a pass saw could go unlisted, so the issue defers. No
network read is made here.
"""
from __future__ import annotations

from controller.pass_ import ISSUE_APPS


def after(pull: dict, at: str, whole: bool) -> list:
    """A listed pull request's spans once the pass that listed it is counted: `pull` as that pass's record holds it, `at`
    the `read_at` of the issue's facts there, `whole` whether that pass read the linked pull requests whole."""
    spans = [dict(span) for span in pull["keyword_spans"]]
    standing = bool(spans) and spans[-1]["gone_at"] is None
    if pull["keyword"] and not standing:
        spans.append({"seen_at": at, "gone_at": None})
    elif not pull["keyword"] and standing and whole:
        spans[-1]["gone_at"] = at
    return spans


def held(record: dict, item: dict):
    """The issue's facts in `record`, or None where it holds none."""
    for entry in record["issues"]:
        if entry["facts"]["item"] == item:
            return entry["facts"]
    return None


def read(earlier, item: dict) -> tuple:
    """`(spans, whole)` for the issue `item`: each pull request a pass saw with its keyword, by number, with its spans,
    from the pass records `earlier`, oldest first; and whether they were read whole: True, False where they could not be
    read, None where the chain they give is broken. One with no span is left out: no pass saw its keyword."""
    if not isinstance(earlier, list):
        return {}, False
    try:
        facts = [held(record, item) for record in earlier]
        bases = [at for at, found in enumerate(facts) if found is not None and found["complete"]["linked"] is True]
        base = bases[-1] if bases else -1
        spans = {pull["number"]: after(pull, facts[base]["read_at"], True) for pull in facts[base]["linked"]} if bases else {}
        chained = bool(bases) or facts.count(None) == len(facts)
        for record, found in zip(earlier[base + 1:], facts[base + 1:]):
            left = [entry["item"] for entry in record["left_out"]]
            chained = chained and ISSUE_APPS not in record["alerts"] and item not in left and None not in left
            for pull in found["linked"] if found is not None else ():
                spans[pull["number"]] = after(dict(pull, keyword_spans=spans.get(pull["number"], [])),
                                              found["read_at"], False)
    except (KeyError, TypeError):
        return {}, False
    return {number: found for number, found in spans.items() if found}, True if chained else None
