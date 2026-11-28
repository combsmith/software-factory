"""The opening port: the draft pull request an opening Run's `apply` opens for its issue, in the issue's own repo, from
the work branch the Decision admitted to the repo's default branch, and reads back (issue 838; decision 0238). It
decides nothing: the title and the body are `harness/draft.py`'s, the branches `apply`'s, and a Role's token sends
only what `allowed` lets through.

- `refusal(title, body)`: None, or the code why GitHub would not take them: `TITLE_BYTES` for a title whose UTF-8 is
  over 256 bytes, `BODY_BYTES` for a body whose UTF-8 is over 65,536. GitHub's bound is 256 characters and 65,536;
  no trial grounds the unit it counts in (decision 0238), and bytes are never fewer than characters, so a draft this
  lets through is within the bound whatever the unit. `apply` asks this before any token is minted. A title or a body
  that is no text is `UNREADABLE`, as is a lone surrogate, which no UTF-8 can carry.
- `allowed(repo, branch, base, title, body)`: `(permits, patterns)` for `adapters/effects.py`'s `Allowed`: the list
  of the pull requests from `branch`, the one opening, a draft of exactly that title, body, head and base, and the read
  of one by its number; nothing for any of them told wrongly. The base is the default branch's name as GitHub gave it.
- `write(sender, repo, branch, base, commit, title, body, login)`: what the opening did, read back, as
  `harness/apply.py`'s `opened` reads it, `{state, number, head, reason}`. One `login` already opened from `branch`
  is recovered, `already_applied`, and nothing is sent: an opening `apply` that ended after its write opens no second
  (section 4.1); one a person closed is `opened_closed`, and none is opened beside it. Else the draft is opened once,
  and `applied` only when read back by its number: open, opened by `login`, from `branch` of `repo` itself at
  `commit`, the one the push landed, to `base`, a draft. A 401 or a 403 is `refused`, `token_refused`; a list not
  read whole, `pulls_unreadable`: it is whole only with no next page and each entry saying who opened it, a person
  or an App, from where; two by `login` from the branch, `opened_twice`; a write GitHub did not answer or did not
  take, `write_unanswered` or `write_refused`; a write taken whose read-back fails, a 401 or a 403 on it among them,
  is `sent`, and nothing is claimed for it. One told wrongly sends nothing, `TOLD_WRONGLY`; a pull request is the
  App's only as a `Bot`.

Limits: the read-back holds the head, not the text, which `allowed` held as it was sent; a login or a repo is
compared in the case given, so one GitHub reads back in another case claims nothing; a rate limit's 403 is
`token_refused`, as `adapters/effects.py`'s Role writes read it.

P-41 grounds the write: an App's installation token opens a pull request in its repo, answered 201 with its number,
head and author, and GitHub asks `pull_requests=write` of it.
"""
from __future__ import annotations

import re

from adapters.github import Unanswered, request
from adapters.push import REPO, WORK

TITLE_MOST = 256        # GitHub's bound on a pull request's title, here in bytes of UTF-8
BODY_MOST = 65536       # and on its body
TITLE_BYTES = "opening_title_bytes"
BODY_BYTES = "opening_body_bytes"
UNREADABLE = "opening_unreadable"
TOLD_WRONGLY = "opening_told_wrongly"   # a repo, a branch, a base, a commit or a login in no shape this sends
# A branch the draft opens to: a ref's name as git allows it, read plainly.
BASE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,254}")
SHA = re.compile(r"[0-9a-f]{40}")
NUMBER = re.compile(r"[1-9][0-9]{0,18}")
LISTED = 100            # a list of 100 may have more after it, so it is not read whole


def _text(value) -> bool:
    return type(value) is str and not any("\ud800" <= c <= "\udfff" for c in value)


def refusal(title, body):
    """None where GitHub takes `title` and `body` by its bounds, or the one code why it would not."""
    if not (_text(title) and _text(body)):
        return UNREADABLE
    if len(title.encode("utf-8")) > TITLE_MOST:
        return TITLE_BYTES
    if len(body.encode("utf-8")) > BODY_MOST:
        return BODY_BYTES
    return None


def _base(base) -> bool:
    return type(base) is str and BASE.fullmatch(base) is not None and ".." not in base and "//" not in base \
        and not base.endswith(("/", ".", ".lock"))


def _told(repo, branch, base) -> bool:
    return type(repo) is str and REPO.fullmatch(repo) is not None and repo.split("/")[1] not in (".", "..") \
        and type(branch) is str and WORK.fullmatch(branch) is not None and _base(base)


def _pulls(repo: str) -> str:
    return "/repos/%s/pulls" % repo


def _listing(repo: str, branch: str) -> str:
    return _pulls(repo) + "?head=%s:%s&state=all&per_page=%d" % (repo.split("/")[0], branch, LISTED)


def allowed(repo, branch, base, title, body) -> tuple:
    """`(permits, patterns)` for `Allowed`: what a Role's token may send to open one draft from `branch` of `repo` to
    `base`, of exactly `title` and `body`; nothing at all for any of them told wrongly."""
    if not _told(repo, branch, base) or refusal(title, body) is not None:
        return {}, []
    text = (title, body)

    def nothing(body) -> bool:
        return body is None

    def draft(sent) -> bool:
        return type(sent) is dict and set(sent) == {"title", "body", "head", "base", "draft"} \
            and (sent["title"], sent["body"]) == text and sent["head"] == branch and sent["base"] == base \
            and sent["draft"] is True

    permits = {("GET", _listing(repo, branch)): nothing, ("POST", _pulls(repo)): draft}
    patterns = [("GET", re.compile(re.escape(_pulls(repo) + "/") + NUMBER.pattern), nothing)]
    return permits, patterns


class _Refused(Exception):
    """GitHub would not take the token."""


def _sent(sender, req: dict):
    """GitHub's answer, or None where it gave none; a 401 or a 403 ends the opening refused."""
    try:
        answer = sender.send(req)
    except (Unanswered, OSError, TypeError, ValueError, KeyError, AttributeError):
        return None
    if isinstance(answer, dict) and answer.get("status") in (401, 403):
        raise _Refused()
    return answer if isinstance(answer, dict) else None


def _body(answer, status: int):
    return answer.get("body") if isinstance(answer, dict) and answer.get("status") == status else None


def _back(state: str, number=None, head=None, reason=None) -> dict:
    return {"state": state, "number": number, "head": head, "reason": reason}


def _readable(pull) -> bool:
    """Whether a listed pull request says who opened it, a person or an App, and from which branch of which repo:
    one that does not may be the App's own, so the list is not read whole."""
    user, head = (pull.get("user"), pull.get("head")) if isinstance(pull, dict) else (None, None)
    return isinstance(user, dict) and type(user.get("login")) is str and user.get("type") in ("User", "Bot") \
        and isinstance(head, dict) \
        and type(head.get("ref")) is str and isinstance(head.get("repo"), dict) \
        and type(head["repo"].get("full_name")) is str


def _ours(pull, repo: str, branch: str, login: str) -> bool:
    """Whether `pull` is one `login` opened from `branch` of `repo` itself."""
    user, head = (pull.get("user"), pull.get("head")) if isinstance(pull, dict) else (None, None)
    return isinstance(user, dict) and user.get("login") == login and user.get("type") == "Bot" \
        and isinstance(head, dict) and head.get("ref") == branch \
        and isinstance(head.get("repo"), dict) and head["repo"].get("full_name") == repo


def _more(answer) -> bool:
    """Whether GitHub's answer says another page follows."""
    headers = answer.get("headers") if isinstance(answer, dict) else None
    link = next((v for k, v in headers.items() if str(k).lower() == "link"), "") if isinstance(headers, dict) else ""
    return 'rel="next"' in str(link)


def write(sender, repo, branch, base, commit, title, body, login) -> dict:
    """What opening the draft did, read back: `{state, number, head, reason}`. `commit` is the one the push landed on
    `branch`: a draft read back at another head is not the one `apply` opened."""
    if not _told(repo, branch, base) or refusal(title, body) is not None or type(login) is not str or not login \
            or type(commit) is not str or SHA.fullmatch(commit) is None:
        return _back("refused", reason=TOLD_WRONGLY)
    posted = []
    try:
        return _open(sender, repo, branch, base, commit, title, body, login, posted)
    except _Refused:
        # A draft GitHub took is no refusal: it stands, and nothing is claimed for it.
        return _back("sent") if posted else _back("refused", reason="token_refused")


def _open(sender, repo, branch, base, commit, title, body, login, posted) -> dict:
    answer = _sent(sender, request("GET", _listing(repo, branch)))
    listed = _body(answer, 200)
    if not isinstance(listed, list) or len(listed) >= LISTED or _more(answer) \
            or not all(_readable(p) for p in listed):
        return _back("failed", reason="pulls_unreadable")
    mine = [p for p in listed if _ours(p, repo, branch, login)]
    if len(mine) > 1:
        return _back("failed", reason="opened_twice")
    # One a person closed is no draft to recover, and no second is opened beside it.
    if mine and mine[0].get("state") != "open":
        return _back("failed", reason="opened_closed")
    state, made = ("already_applied", mine[0]) if mine else ("applied", None)
    if made is None:
        answer = _sent(sender, request("POST", _pulls(repo), body={
            "title": title, "body": body, "head": branch, "base": base, "draft": True}))
        made = _body(answer, 201)
        if answer is not None and answer.get("status") == 201:
            posted.append(True)
            made = made if isinstance(made, dict) else {}
        if not isinstance(made, dict):
            status = answer.get("status") if answer is not None else None
            return _back("failed", reason="write_unanswered" if type(status) is not int or status >= 500
                         else "write_refused")
    number = made.get("number")
    back = _body(_sent(sender, request("GET", "%s/%d" % (_pulls(repo), number))), 200) \
        if type(number) is int and number > 0 else None
    base_read = back.get("base") if isinstance(back, dict) else None
    if not (_ours(back, repo, branch, login) and type(back.get("number")) is int and back["number"] == number
            and back["head"].get("sha") == commit and isinstance(base_read, dict)
            and base_read.get("ref") == base and back.get("state") == "open"
            and (state == "already_applied" or back.get("draft") is True)):
        return _back("sent")
    return _back(state, number, branch)
