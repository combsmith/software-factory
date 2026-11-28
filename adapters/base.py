"""Where the commit an opening admission carries stands on the default branch at the push (decision 0242, issue 838).

`on_default(transport, repo, admitted)` reads the default branch's head as the issues port does (`issues.default_head`:
the repo names the branch, and its ref, never a name a tag could share, gives a commit's whole name). It then tells
three cases apart, `(case, head)`:

- `HEAD`: the admitted sha is that head. Nothing more is asked.
- `ANCESTOR`: GitHub's comparison of the admitted sha with that head says the head is ahead of it, and their merge
  base is the admitted sha itself.
- `NEITHER`: the comparison says the head is behind it, their merge base the head, or apart from it, their merge
  base a third commit: the admitted sha was rewritten away.

`(None, head)` where the comparison cannot be read, or says what no history holds, such as a head ahead of another
merge base, and `(None, None)` where the head cannot, or where the repo or the sha is told wrongly: then nothing is
compared, or nothing at all is asked. Neither is one of the three: an unread fact is never a case.

The port decides nothing. `harness/push.py`, not yet built, asks it before the write and once after it. It goes on
only where the case is in `GOES_ON`, and refuses in the third case and where nothing was told, whatever head is given
beside it; and it makes the work branch only while the head is the one its checks read. A later record names the
refusal's code and its fault.

Limit: GitHub answers a comparison with no common history, or a sha it does not hold, with a refusal, not a status;
that is read as untold, not as `NEITHER`. Both push nothing.
"""
from __future__ import annotations

import re

from adapters import issues
from adapters.github import Unanswered, request

HEAD = "head"                   # the admitted sha is the default branch's head
ANCESTOR = "ancestor"           # it is an ancestor of that head
NEITHER = "neither"             # it is no commit of that head's history
GOES_ON = (HEAD, ANCESTOR)      # the two cases a push goes on in; nothing else is one
SHA = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
AHEAD, BEHIND, APART = "ahead", "behind", "diverged"    # GitHub's words for a head after, before or beside the base


def _sha(said) -> bool:
    return type(said) is str and SHA.fullmatch(said) is not None


def _repo(said) -> bool:
    return type(said) is str and REPO.fullmatch(said) is not None and said.split("/")[1] not in (".", "..")


def on_default(transport, repo, admitted) -> tuple:
    """`(case, head)`: `HEAD`, `ANCESTOR` or `NEITHER` for where `admitted` stands on `repo`'s default branch, read
    now, with that head; `(None, head)` where the comparison cannot be read, `(None, None)` where the head cannot, or
    where `repo` or `admitted` is told wrongly, with nothing asked."""
    if not (_repo(repo) and _sha(admitted)):
        return None, None
    head = issues.default_head(transport, repo)
    if not _sha(head):
        return None, None
    if head == admitted:
        return HEAD, head
    try:
        answer = transport.send(request("GET", "/repos/%s/compare/%s...%s?per_page=1" % (repo, admitted, head)))
    except Unanswered:
        return None, head
    body = answer.get("body") if isinstance(answer, dict) and answer.get("status") == 200 else None
    body = body if isinstance(body, dict) else {}
    base = body.get("merge_base_commit") if isinstance(body.get("merge_base_commit"), dict) else {}
    if body.get("status") == AHEAD and base.get("sha") == admitted:
        return ANCESTOR, head
    if body.get("status") == BEHIND and base.get("sha") == head \
            or body.get("status") == APART and _sha(base.get("sha")) and base.get("sha") not in (admitted, head):
        return NEITHER, head
    return None, head
