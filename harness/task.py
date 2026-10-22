"""The Task one Run is given, built from the Decision that admitted it and nothing else (design section 3.5, issue 194).

`build(record, run, facts, texts, role, findings, config)` finds the Decision in the pass record by the Run id the
Controller minted beside it, and builds `task/1` from it, the item's facts, the texts read for it, the Role's manifest
and the configuration. A Run started any other way finds no Decision and is refused: nothing that can merely start a
workflow can choose what a Run does. Each text is labelled by its trust class from who wrote it, read from the facts'
actor and the configuration, never from the text. A Task carries texts up to the configuration's characters, and says
what it left out, and how much (L-56). Nothing here reads a clock, a file or the network.
"""
from __future__ import annotations

import copy

from harness import shared

ADMIT = "admit"


class Refused(ValueError):
    """No Task can be built: the Run has no Decision that admitted it, or what was read does not agree with it."""


def decision_of(record: dict, run: str):
    """The entry of the pass record whose Run id is `run` and whose Decision admitted a Run, or None."""
    found = [e for e in record["pull_requests"] + record["issues"] if e["run"] == run]
    if len(found) != 1 or found[0]["decision"]["outcome"] != ADMIT:
        return None
    return found[0]


def trust(actor, config: dict) -> str:
    """A text's trust class, from who wrote it as the facts name them, never from the text (decision 0038). The
    Maintainer is the one person the configuration names; a Factory App or Lens, or the machine user, is a Role; a
    third-party reviewer the configuration lists is advisory; anyone else, a colleague with write access among them, is
    outside."""
    if not isinstance(actor, dict):
        return "outside"
    kind, name = actor.get("kind"), actor.get("name")
    if kind == "human" and name == config["maintainer"]:
        return "maintainer"
    if kind == "machine_user" or (kind in ("app", "lens") and name in config["roles"]):
        return "role"
    if kind == "lens" and name in config["harness"]["advisory"]:
        return "advisory"
    return "outside"


def texts_of(texts: list, config: dict) -> tuple:
    """`(kept, omitted)`: the texts in the order given, each with its trust class, up to the configuration's
    characters in all; and for each kind of text left out, how many and how many characters (L-56). A text is kept
    whole or left out whole, so no text reaches the model cut short."""
    room = config["harness"]["texts"]["characters"]
    kept, omitted = [], {}
    for text in texts:
        body = text["body"]
        if len(body) <= room:
            kept.append({"id": text["id"], "trust": trust(text["by"], config), "source": text["by"]["name"],
                         "body": body})
            room -= len(body)
            continue
        kind = text["id"].split(":")[0]
        seen = omitted.setdefault(kind, {"kind": kind, "texts": 0, "characters": 0})
        seen["texts"] += 1
        seen["characters"] += len(body)
    return kept, [omitted[k] for k in sorted(omitted)]


def build(record: dict, run: str, facts: dict, texts: list, role: dict, findings: list, config: dict) -> dict:
    """The Task of Run `run`, validated, or Refused."""
    entry = decision_of(record, run)
    if entry is None:
        raise Refused("no Decision in pass %s admitted Run %s" % (record.get("pass"), run))
    admit = entry["decision"]["admit"]
    # The facts are the item's as the Run reads them: the item and the content the Decision admitted, or the Run is
    # about something else, and is superseded before anything is asked.
    if facts["item"] != entry["decision"]["item"] or facts["content_id"] != admit["content_id"]:
        raise Refused("the facts are not of the item and content Run %s was admitted for" % run)
    if role["name"] != admit["role"]:
        raise Refused("the manifest is %s's, and Run %s is %s's" % (role["name"], run, admit["role"]))
    intents = [i for i in role["intents"] if i["name"] == admit["intent"]]
    if len(intents) != 1:
        raise Refused("%s's manifest declares no Intent %s" % (role["name"], admit["intent"]))
    intent = intents[0]
    kept, omitted = texts_of(texts, config)
    task = {"schema": "task/1", "run": run, "release": config["release"], "role": admit["role"],
            "intent": admit["intent"], "item": copy.deepcopy(facts["item"]), "content_id": admit["content_id"],
            "findings": list(findings), "texts": kept,
            "limits": copy.deepcopy(config["harness"]["limits"][intent["tier"]]), "tier": intent["tier"],
            "permitted_effects": list(intent["permitted_effects"]), "result_schema": "result/1",
            "omitted": omitted}
    return shared.checked(task, "task", Refused)
