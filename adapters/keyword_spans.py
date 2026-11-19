"""A closing keyword's link, timed by the passes that saw it: each linked pull request's `keyword_spans`, read from the
pass records before this pass (design sections 3.10 and 4.1; decision 0186).

GitHub gives a keyword's link no time (`trials/P-48.json`), so its only one is the Factory's own record of seeing it.
Each pass record holds each issue's facts, and so each pull request that pass listed, with its keyword as that pass read
it and its spans as the records before that pass gave them. The newest record that holds the issue's facts therefore
carries the whole history, one step short: the spans it holds, and what its own pass saw. What it saw is added here: a
keyword it read, with no span open, opens one at the `read_at` of the issue's facts in that record, the first record
that listed the pull request with this keyword; a keyword it read gone, with a span open, ends that span at that
`read_at`, and one put back later opens a new span, which reaches back to nothing. A keyword is read gone only by a
record that read the linked pull requests whole: one read short may have missed it, and the span stays open.

Only records the Factory itself wrote are read: the caller hands those `adapters/passes.py` read from the poller's own
runs and `controller/reads.py` held to `pass/1`, or None where they could not be read. No record at hand, or none that
holds the issue, gives no time, never an earlier one. Records that could not be read give no time and are not whole: a
pull request whose keyword a pass saw could go unlisted, so the issue defers. No network read is made here.
"""
from __future__ import annotations


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


def read(earlier, item: dict) -> tuple:
    """`(spans, whole)` for the issue `item`: each pull request a pass saw with its keyword, by number, with its spans,
    from the newest of the pass records `earlier`, oldest first, that holds the issue's facts; and whether the records
    could be read. One with no span is left out: no pass saw its keyword."""
    if not isinstance(earlier, list):
        return {}, False
    try:
        for record in reversed(earlier):
            for entry in record["issues"]:
                facts = entry["facts"]
                if facts["item"] == item:
                    found = {pull["number"]: after(pull, facts["read_at"], facts["complete"]["linked"] is True)
                             for pull in facts["linked"]}
                    return {number: spans for number, spans in found.items() if spans}, True
    except (KeyError, TypeError):
        return {}, False
    return {}, True
