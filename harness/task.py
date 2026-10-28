"""The Task one Run is given, built from the Decision that admitted it and nothing else (design section 3.5, issue 194).

`build(record, run, facts, texts, role, findings, config, diff)` finds the Decision in the pass record by the Run id the
Controller minted beside it, and builds `task/1` from it, the item's facts, the texts read for it, the Role's manifest
and the configuration, and, for a pull request, the change itself. A Run started any other way finds no Decision and is refused: nothing that can merely start a
workflow can choose what a Run does. Each text is labelled by its trust class from who wrote it, read from the facts'
actor and the configuration, never from the text. A Task carries texts up to the configuration's characters, and says
what it left out, and how much (L-56); the change has a budget of its own. Nothing here reads a clock, a file or the network.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from harness import shared

ADMIT = "admit"
# The order texts are kept in when not all fit: a person with the Maintainer's word first, then the Roles', then
# advisory reviewers', then anyone else's, each kind in the order given, newest first as the reads give them (L-56).
RANK = ("maintainer", "role", "advisory", "outside")
TEXT_ID = re.compile(r"[a-z]+:[A-Za-z0-9_-]+")
# A writer's name as task/1 carries it in `source`.
SOURCE = re.compile(r"[A-Za-z0-9-]+(\[bot\])?")
# Where one file's part of a diff begins, as git writes it: the diff is cut only there, never inside a file.
FILE_START = re.compile(r"(?=^diff --git )", re.M)


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
    if (kind == "machine_user" and name == config["approver"]) or (kind in ("app", "lens") and name in config["roles"]):
        return "role"
    if kind == "lens" and name in config["harness"]["advisory"]:
        return "advisory"
    return "outside"


def readable_text(text) -> bool:
    """A text as the reads give one: an id of its kind, who wrote it as the facts name an actor, and its body. No read
    gives a text of kind `diff`: the change is the Task's own text, built from the bytes the Decision admitted. A text
    left out is held to this as one kept is, so a text no Task could carry is refused, not dropped unseen."""
    return (isinstance(text, dict) and set(text) == {"id", "by", "body"} and isinstance(text["id"], str)
            and TEXT_ID.fullmatch(text["id"]) is not None and not text["id"].startswith("diff:")
            and isinstance(text["body"], str) and shared.errors(text["by"], "actor") == []
            and SOURCE.fullmatch(text["by"]["name"]) is not None)


def carried(body: str) -> int:
    """How long a text is as the Task carries it to the CLI, escaped as JSON, so that the budget bounds the bytes of
    the one argument the CLI is given and not only its characters."""
    return len(json.dumps(body)) - 2


def texts_of(texts: list, config: dict) -> tuple:
    """`(kept, omitted)`: the texts, the Maintainer's first and then each trust class in turn (RANK), each with its
    class, up to the configuration's characters as the Task carries them; and for each kind of text left out, how many
    and how many characters (L-56). A text is kept whole or left out whole, so no text reaches the model cut short."""
    room = config["harness"]["texts"]["characters"]
    kept, omitted = [], {}
    ranked = sorted(((trust(t["by"], config), i, t) for i, t in enumerate(texts)), key=lambda x: (RANK.index(x[0]), x[1]))
    for klass, _, text in ranked:
        body = text["body"]
        if carried(body) <= room:
            kept.append({"id": text["id"], "trust": klass, "source": text["by"]["name"], "body": body})
            room -= carried(body)
            continue
        kind = text["id"].split(":")[0]
        seen = omitted.setdefault(kind, {"kind": kind, "texts": 0, "characters": 0})
        seen["texts"] += 1
        seen["characters"] += len(body)
    return kept, [omitted[k] for k in sorted(omitted)]


def diff_of(diff, facts: dict, admit: dict, config: dict) -> tuple:
    """`(text, omitted)`: the change a pull request's Run judges, as the Task's text `diff:<content hex>`, and what of it
    was left out, or `(None, None)` for an issue, which has none; a pull request with no diff has no Task. The diff is the bytes whose sha256 is the content id
    the Decision admitted, as the facts port takes it (decision 0044), so a Run is given only the content it was admitted
    for. It is `outside` text, whoever pushed it: what a review judges is where an injection arrives. It has its own
    budget, counted as the Task carries it; over it, it is cut at a file's boundary, never inside a file, and what is
    cut is said, as kind `diff`, by files and characters (L-56)."""
    if facts["item"]["type"] != "pull_request":
        if diff:
            raise Refused("an issue's Run is given no diff")
        return None, None
    if not isinstance(diff, bytes) or not diff:
        raise Refused("a pull request's Run is given no diff")
    if "sha256:" + hashlib.sha256(diff).hexdigest() != admit["content_id"]:
        raise Refused("the diff is not the content the Decision admitted")
    try:
        body = diff.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused("the diff is not text") from None
    room = config["max_diff_characters"]
    kept, cut, characters = [], 0, 0
    for part in [p for p in FILE_START.split(body) if p]:
        if not cut and carried(part) <= room:
            kept.append(part)
            room -= carried(part)
        else:
            cut += 1
            characters += len(part)
    text = {"id": "diff:" + admit["content_id"].split(":", 1)[1], "trust": "outside", "source": facts["last_pusher"],
            "body": "".join(kept)}
    return text, ({"kind": "diff", "texts": cut, "characters": characters} if cut else None)


def build(record: dict, run: str, facts: dict, texts: list, role: dict, findings: list, config: dict,
          diff: bytes = None) -> dict:
    """The Task of Run `run`, validated, or Refused. Every input is held to its schema first: what cannot be read is
    no Task, never a crash."""
    if shared.errors(record, "pass"):
        raise Refused("the pass record is no pass/1")
    entry = decision_of(record, run)
    if entry is None:
        raise Refused("no Decision in pass %s admitted Run %s" % (record.get("pass"), run))
    return admitted(entry["decision"]["admit"], entry["decision"]["item"], run, facts, texts, role, findings, config,
                    diff)


def admitted(admit: dict, item: dict, run: str, facts: dict, texts: list, role: dict, findings: list, config: dict,
             diff: bytes = None) -> dict:
    """The Task of Run `run`, admitted for `admit`'s Role, Intent and content on `item`, validated, or Refused. `build`
    reads the admission from the pass record; the eval job gives a held-out case's own, so that a case's Task is built
    by this one function, as a live Run's is (issue 309, ruling 5)."""
    # The facts are the item's as the Run reads them: the item and the content the Decision admitted, or the Run is
    # about something else, and is superseded before anything is asked.
    kind = "facts" if item["type"] == "pull_request" else "issue-facts"
    if shared.errors(facts, kind):
        raise Refused("the facts are no %s" % kind)
    # Facts read short are no reading of the item: a Task built from them could leave out what a person said.
    if not all(v is True for v in facts["complete"].values()):
        raise Refused("the facts of Run %s were read short" % run)
    if shared.errors(role, "role") or not isinstance(texts, list) or not all(readable_text(t) for t in texts):
        raise Refused("the manifest or the texts cannot be read")
    if not isinstance(findings, list):
        raise Refused("the findings cannot be read")
    if facts["item"] != item or facts["content_id"] != admit["content_id"]:
        raise Refused("the facts are not of the item and content Run %s was admitted for" % run)
    if role["name"] != admit["role"]:
        raise Refused("the manifest is %s's, and Run %s is %s's" % (role["name"], run, admit["role"]))
    intents = [i for i in role["intents"] if i["name"] == admit["intent"]]
    if len(intents) != 1:
        raise Refused("%s's manifest declares no Intent %s" % (role["name"], admit["intent"]))
    intent = intents[0]
    kept, omitted = texts_of(texts, config)
    # The change is the first text a pull request's Task carries, apart from the others and their budget.
    change, cut = diff_of(diff, facts, admit, config)
    kept = ([change] if change is not None else []) + kept
    omitted = sorted(omitted + ([cut] if cut is not None else []), key=lambda o: o["kind"])
    task = {"schema": "task/1", "run": run, "release": config["release"], "role": admit["role"],
            "intent": admit["intent"], "item": copy.deepcopy(facts["item"]), "content_id": admit["content_id"],
            "findings": list(findings), "texts": kept,
            "limits": copy.deepcopy(config["harness"]["limits"][intent["tier"]]), "tier": intent["tier"],
            "permitted_effects": list(intent["permitted_effects"]), "result_schema": "result/1",
            "omitted": omitted}
    return shared.checked(task, "task", Refused)
