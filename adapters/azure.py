"""The second transport: what an advisory Lens's reader is asked through, and nothing else (decision 0224). With
`adapters/github.py` it is one of the two files in this repo that may reach the network, and it may not name GitHub's host
(tools/check_repo.py). A request is one of four acts, built by `create`, `read`, `cancel` or `chat`, and names no method
and no path: this file alone writes those, by `wire`, so a caller cannot ask for another, and no request of this file's is
one `adapters/github.py` would send. They are the requests of two APIs alone: Responses, to create a response, read it
and cancel it, and Chat Completions, to create one.

What sends them is the next part to come, and until it does this file imports nothing that reaches the network.
"""
from __future__ import annotations

import re

RESPONSES = "/openai/v1/responses"
CHAT = "/openai/v1/chat/completions"
# A response's id as a path's one segment: no slash, dot, percent or query, so it names no other path.
IDENT = re.compile(r"[A-Za-z0-9_-]{1,200}")


class Unanswered(Exception):
    """A request the transport will not send, or one Azure did not answer whole."""


def request(act: str, ident, body) -> dict:
    """One of the four requests, or a refusal: `create` or `chat` with a JSON object that is not empty and no id, or
    `read` or `cancel` with a response's id and no body."""
    made = act in ("create", "chat") and ident is None and isinstance(body, dict) and bool(body)
    named = act in ("read", "cancel") and type(ident) is str and IDENT.fullmatch(ident) is not None and body is None
    if type(act) is not str or not (made or named):
        raise Unanswered("the transport sends a response's create, read and cancel and a chat completion's create alone")
    return {"act": act, "id": ident, "body": body}


def create(body: dict) -> dict:
    """The request that creates a response (the Responses API)."""
    return request("create", None, body)


def read(ident: str) -> dict:
    """The request that reads a response created before, by its id."""
    return request("read", ident, None)


def cancel(ident: str) -> dict:
    """The request that cancels a response still running, so that it is not left to run on and be billed."""
    return request("cancel", ident, None)


def chat(body: dict) -> dict:
    """The request that creates a chat completion (the Chat Completions API)."""
    return request("chat", None, body)


def wire(req) -> tuple:
    """`(verb, path, body)` as a request is sent: the only verbs and paths this transport writes. A request not built
    as `request` builds one is refused, whoever made it."""
    if not isinstance(req, dict) or set(req) != {"act", "id", "body"}:
        raise Unanswered("a request is its act, its id and its body, as this file builds one")
    req = request(req["act"], req["id"], req["body"])
    if req["act"] == "create":
        return "POST", RESPONSES, req["body"]
    if req["act"] == "chat":
        return "POST", CHAT, req["body"]
    if req["act"] == "read":
        return "GET", "%s/%s" % (RESPONSES, req["id"]), None
    return "POST", "%s/%s/cancel" % (RESPONSES, req["id"]), {}
