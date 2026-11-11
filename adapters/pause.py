"""The Pause, read as GitHub holds it: `FACTORY_PAUSED`, a variable on the org and on each repo, read through the one
transport with the Controller's token (#193's rulings for PR 3; L-58). It hands back what `controller/pass_.py`'s
`human_pause` reads: `{"org": value, "repos": {repo: value}}`, each value the variable's text, None where GitHub holds
none, or `UNREADABLE` where the read was not answered as GitHub answers a variable. It decides nothing: the Pause's
meaning is the pass's, and an unreadable scope is a Pause unreadable (I-13).

The org's own endpoint refuses the Controller's token, which holds the repo's Variables read and nothing of the org's
(trials/P-52.json, a 403); the repo's list of the org's variables names the org's FACTORY_PAUSED with its value. So the
org's Pause is read from that list, for the first repo the read is of, its owner the org, paged by its `link` header
until read whole: as many entries as `total_count` says, each page but the last a full one, each name once whatever its
case. A list read whole that does not name it is unreadable, never unset, since the list holds only the org's variables
shared with that repo (decision 0077); so is a list not read whole, an answer that is not 200, or an entry that cannot
be read (issue 362, "Pause: read the org's FACTORY_PAUSED through the repo's list of org variables, as P-52 found").

`explained` hands back, beside the same read, why each scope it could not read was unreadable, a code of this port's
own and never what GitHub said, for a caller that names its Pause by it: the approving act does (decision 0192). The
read itself is unchanged, and so is what the Controller reads of it."""
from __future__ import annotations

import re

from adapters.github import Unanswered, request

NAME = "FACTORY_PAUSED"
PAUSED, NOT_PAUSED = "true", "false"     # the two values a person sets, as `controller/pass_.py` reads them
UNREADABLE = {"unreadable": True}      # no text a variable can hold: `human_pause` reads anything else as unreadable
# Why a scope is unreadable, the part a caller names it by: GitHub refused the list of the org's variables, or the
# repo's own variable; the list, read whole, does not name it; or anything else, of the org's read or of a repo's.
ORG_REFUSED, ORG_UNNAMED, ORG_UNREAD = "org_refused", "org_unnamed", "org"
REPO_REFUSED, REPO_UNREAD = "repo_refused", "repo"
ORG_REFUSALS = (403, 404)              # how GitHub refuses a token the org's list, or hides the list from it
REPO_REFUSALS = (403,)                 # a 404 on the repo's own variable is a variable GitHub holds none of
ORG = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
PAGE = 100                             # the most entries GitHub gives a page of the org's variables
NEXT = re.compile(r'<[^>]*>;\s*rel="next"')


def path(repo: str) -> str:
    """The variable's path on a repo, `owner/name`."""
    return "/repos/%s/actions/variables/%s" % (repo, NAME)


def listed(repo: str, page: int = 1) -> str:
    """The path of a page of the org's variables, as the repo `owner/name` lists them."""
    first = "/repos/%s/actions/organization-variables?per_page=%d" % (repo, PAGE)
    return first if page == 1 else "%s&page=%d" % (first, page)


def _named(repo: str) -> bool:
    return bool(REPO.fullmatch(repo)) and repo.split("/")[1] not in (".", "..")


def _refused(answer: dict, statuses) -> bool:
    """Whether GitHub refused the token the read: one of `statuses`, and no rate limit's, which GitHub answers 403 too,
    with no request left or a time to wait. A limit is no grant's fault, and is anything else; so is a refusal on the
    last request left, which the port cannot tell from one. A 404 is never a limit's, whatever is left."""
    headers = answer.get("headers") or {}
    limited = answer["status"] == 403 and (str(headers.get("x-ratelimit-remaining")) == "0" or "retry-after" in headers)
    return answer["status"] in statuses and not limited


def _org_value(transport, org: str, repo):
    """The org's FACTORY_PAUSED, as `repo`'s list of the org's variables names it, read whole (the module's rule): its
    value, or UNREADABLE, never None, and beside it the part that says why it is unreadable, or None."""
    if repo is None or not ORG.fullmatch(org) or not _named(repo) or repo.split("/")[0] != org:
        return UNREADABLE, ORG_UNREAD
    entries, total, page = [], None, 1
    while True:
        try:
            answer = transport.send(request("GET", listed(repo, page)))
        except Unanswered:
            return UNREADABLE, ORG_UNREAD
        body = answer["body"]
        if _refused(answer, ORG_REFUSALS):
            return UNREADABLE, ORG_REFUSED
        if answer["status"] != 200 or not isinstance(body, dict) or not isinstance(body.get("variables"), list) \
                or type(body.get("total_count")) is not int or total not in (None, body["total_count"]):
            return UNREADABLE, ORG_UNREAD
        total = body["total_count"]
        entries += body["variables"]
        if not NEXT.search(str((answer.get("headers") or {}).get("link", ""))):
            break
        # A next page after one short of a full page, or after every entry the count names, contradicts the count.
        if len(body["variables"]) != PAGE or len(entries) >= total:
            return UNREADABLE, ORG_UNREAD
        page += 1
    if any(not isinstance(e, dict) or not isinstance(e.get("name"), str) for e in entries):
        return UNREADABLE, ORG_UNREAD
    names = [e["name"].upper() for e in entries]
    if len(entries) != total or len(set(names)) != len(names):
        return UNREADABLE, ORG_UNREAD
    pause = [e for e in entries if e["name"].upper() == NAME]
    if not pause:
        return UNREADABLE, ORG_UNNAMED
    return (pause[0]["value"], None) if isinstance(pause[0].get("value"), str) else (UNREADABLE, ORG_UNREAD)


def _value(transport, scope: str):
    """A repo's own FACTORY_PAUSED: its value, None where GitHub holds none, or UNREADABLE, and beside it the part that
    says why it is unreadable, or None."""
    if not _named(scope):
        return UNREADABLE, REPO_UNREAD
    try:
        answer = transport.send(request("GET", path(scope)))
    except Unanswered:
        return UNREADABLE, REPO_UNREAD
    if answer["status"] == 404:
        return None, None
    if _refused(answer, REPO_REFUSALS):
        return UNREADABLE, REPO_REFUSED
    body = answer["body"]
    if answer["status"] != 200 or not isinstance(body, dict) or body.get("name") != NAME \
            or not isinstance(body.get("value"), str):
        return UNREADABLE, REPO_UNREAD
    return body["value"], None


def explained(transport, org: str, repos) -> tuple:
    """`(read, parts)`: the Pause as `read` hands it back, and the part of each scope that is unreadable, the org's and
    then each repo's as they are read. A scope read, set or not, has none."""
    repos = sorted(set(repos))
    if transport is None:
        return ({"org": UNREADABLE, "repos": {repo: UNREADABLE for repo in repos}},
                [ORG_UNREAD] + [REPO_UNREAD for repo in repos])
    scopes = [_org_value(transport, org, repos[0] if repos else None)] + [_value(transport, repo) for repo in repos]
    return ({"org": scopes[0][0], "repos": {repo: value for repo, (value, _) in zip(repos, scopes[1:])}},
            [part for _, part in scopes if part is not None])


def read(transport, org: str, repos) -> dict:
    """The Pause on `org`, read from the first of `repos`'s list of the org's variables, and on each of `repos`, each
    read once; with no transport, or no repo to read the org's through, the org's is unreadable."""
    return explained(transport, org, repos)[0]
