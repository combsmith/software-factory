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
be read (issue 362, "Pause: read the org's FACTORY_PAUSED through the repo's list of org variables, as P-52 found")."""
from __future__ import annotations

import re

from adapters.github import Unanswered, request

NAME = "FACTORY_PAUSED"
PAUSED, NOT_PAUSED = "true", "false"     # the two values a person sets, as `controller/pass_.py` reads them
UNREADABLE = {"unreadable": True}      # no text a variable can hold: `human_pause` reads anything else as unreadable
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


def _org_value(transport, org: str, repo):
    """The org's FACTORY_PAUSED, as `repo`'s list of the org's variables names it, read whole (the module's rule): its
    value, or UNREADABLE, never None."""
    if repo is None or not ORG.fullmatch(org) or not _named(repo) or repo.split("/")[0] != org:
        return UNREADABLE
    entries, total, page = [], None, 1
    while True:
        try:
            answer = transport.send(request("GET", listed(repo, page)))
        except Unanswered:
            return UNREADABLE
        body = answer["body"]
        if answer["status"] != 200 or not isinstance(body, dict) or not isinstance(body.get("variables"), list) \
                or type(body.get("total_count")) is not int or total not in (None, body["total_count"]):
            return UNREADABLE
        total = body["total_count"]
        entries += body["variables"]
        if not NEXT.search(str((answer.get("headers") or {}).get("link", ""))):
            break
        # A next page after one short of a full page, or after every entry the count names, contradicts the count.
        if len(body["variables"]) != PAGE or len(entries) >= total:
            return UNREADABLE
        page += 1
    if any(not isinstance(e, dict) or not isinstance(e.get("name"), str) for e in entries):
        return UNREADABLE
    names = [e["name"].upper() for e in entries]
    if len(entries) != total or len(set(names)) != len(names):
        return UNREADABLE
    pause = [e for e in entries if e["name"].upper() == NAME]
    if not pause:
        return UNREADABLE
    return pause[0]["value"] if isinstance(pause[0].get("value"), str) else UNREADABLE


def _value(transport, scope: str):
    if not _named(scope):
        return UNREADABLE
    try:
        answer = transport.send(request("GET", path(scope)))
    except Unanswered:
        return UNREADABLE
    if answer["status"] == 404:
        return None
    body = answer["body"]
    if answer["status"] != 200 or not isinstance(body, dict) or body.get("name") != NAME \
            or not isinstance(body.get("value"), str):
        return UNREADABLE
    return body["value"]


def read(transport, org: str, repos) -> dict:
    """The Pause on `org`, read from the first of `repos`'s list of the org's variables, and on each of `repos`, each
    read once; with no transport, or no repo to read the org's through, the org's is unreadable."""
    repos = sorted(set(repos))
    if transport is None:
        return {"org": UNREADABLE, "repos": {repo: UNREADABLE for repo in repos}}
    return {"org": _org_value(transport, org, repos[0] if repos else None),
            "repos": {repo: _value(transport, repo) for repo in repos}}
