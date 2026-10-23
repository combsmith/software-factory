"""The Pause, read as GitHub holds it: `FACTORY_PAUSED`, a variable on the org and on each repo, read through the one
transport with the Controller's token (#193's rulings for PR 3; L-58). It hands back what `controller/pass_.py`'s
`human_pause` reads: `{"org": value, "repos": {repo: value}}`, each value the variable's text, None where GitHub holds
none, or `UNREADABLE` where the read was not answered as GitHub answers a variable. It decides nothing: the Pause's
meaning is the pass's, and an unreadable scope is a Pause unreadable (I-13)."""
from __future__ import annotations

import re

from adapters.github import Unanswered, request

NAME = "FACTORY_PAUSED"
PAUSED, NOT_PAUSED = "true", "false"     # the two values a person sets, as `controller/pass_.py` reads them
UNREADABLE = {"unreadable": True}      # no text a variable can hold: `human_pause` reads anything else as unreadable
ORG = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")


def path(scope: str) -> str:
    """The variable's path for an org, `owner`, or a repo, `owner/name`."""
    if "/" in scope:
        return "/repos/%s/actions/variables/%s" % (scope, NAME)
    return "/orgs/%s/actions/variables/%s" % (scope, NAME)


def _value(transport, scope: str):
    if not (ORG.fullmatch(scope) or (REPO.fullmatch(scope) and scope.split("/")[1] not in (".", ".."))):
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
    """The Pause on `org` and on each of `repos`, each read once; with no transport, every scope is unreadable."""
    if transport is None:
        return {"org": UNREADABLE, "repos": {repo: UNREADABLE for repo in sorted(set(repos))}}
    return {"org": _value(transport, org), "repos": {repo: _value(transport, repo) for repo in sorted(set(repos))}}
