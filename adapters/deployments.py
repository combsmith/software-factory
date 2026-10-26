"""A move of `next`, recorded as GitHub keeps a deployment, through the one transport (decision 0044; #197's ruling
4′): one Deployment of the commit to the environment `factory-next`, described by the Release's name, and its status
`success` once the Channel was read back on it. It decides nothing, and is asked only after the move was read back.
It hands back the Deployment's id, or None when either write was not answered as GitHub answers it."""
from __future__ import annotations

from adapters.github import Unanswered, request

ENVIRONMENT = "factory-next"


def record(transport, repo: str, commit: str, release: str):
    """The id of the Deployment of `commit` as `release` to `factory-next`, its status `success`; None otherwise."""
    made = {"ref": commit, "task": "deploy", "auto_merge": False, "required_contexts": [], "environment": ENVIRONMENT,
            "description": release, "transient_environment": False, "production_environment": False}
    try:
        answer = transport.send(request("POST", "/repos/%s/deployments" % repo, body=made))
        body = answer["body"]
        ident = body.get("id") if answer["status"] == 201 and isinstance(body, dict) else None
        if type(ident) is not int or ident < 1 or body.get("sha") != commit or body.get("environment") != ENVIRONMENT:
            return None
        answer = transport.send(request("POST", "/repos/%s/deployments/%d/statuses" % (repo, ident),
                                        body={"state": "success", "environment": ENVIRONMENT}))
    except Unanswered:
        return None
    body = answer["body"]
    if answer["status"] != 201 or not isinstance(body, dict) or body.get("state") != "success":
        return None
    return ident
