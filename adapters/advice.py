"""An advisory Lens's Result, built from what its reader answered (decision 0224). It is pure: it reads no file, no clock
and no network, and is handed the schemas it holds an answer and its own Result to. `read` takes the answer the second
transport returned, `{status, headers, body}`, and `unasked` takes the reason no answer is in hand. Each returns an
`advice/1`: `completed` only when the call completed, the answer was not cut short, it names the pinned model and it is
one object held to `advice-answer/1`; otherwise `incomplete` or `failed`, with one code and no Finding.

What the reader says is the author's diff at one remove, so nothing of it is trusted. Its severity is kept as its
opinion, its category and criterion as hints beside its text, and its title and message under `body` alone. A Finding
is `uncategorised` with no criterion, on an annotation whose key is its id, and its id is its Lens's name and a sha256
of its source, the content id, its path, its line, its severity and its place among the Findings that share all five:
never of its text. A Finding whose path the change does not hold is counted and left out.

The shapes read here are the two APIs' as their own documents give them; no trial has recorded one yet (the record's
"What is owed"), so a state this file does not know is `transport` or `unparsed`, never a read.
"""
from __future__ import annotations

import hashlib
import json
import re

from tools.jsonschema_lite import validate

INCOMPLETE = ("too_large", "cut_short", "rate_limited", "refused", "timed_out", "budget")
FAILED = ("unparsed", "not_the_model", "no_key", "transport")
# What the step may say with no answer in hand: nothing was asked, or nothing came back.
UNASKED = ("too_large", "budget", "no_key", "timed_out", "transport", "rate_limited")
# An answer wrapped in one fence, which a model asked for JSON alone still writes: the object inside is the answer.
FENCED = re.compile(r"```(?:json)?[ \t]*\n(.*)\n[ \t]*```", re.S)
MODEL = re.compile(r"[a-z0-9][a-z0-9.-]{0,127}")
MILLION = 1000000


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _usage(told: dict, model, tokens: tuple, asks: int, seconds) -> dict:
    asked, answered = tokens
    cost = None
    if asked is not None and answered is not None:
        price = told["usd_per_million"]
        cost = round((asked * price["input"] + answered * price["output"]) / MILLION, 6)
    return {"api": told["api"], "deployment": told["deployment"], "model": told["model"],
            "answering_model": model if type(model) is str and MODEL.fullmatch(model) else None,
            "effort": told["effort"], "asks": asks, "input_tokens": asked, "output_tokens": answered,
            "cost_usd": cost, "seconds": seconds}


def _result(told: dict, reason, findings: list, texts: list, off: int, usage: dict, schemas: dict) -> dict:
    status = "completed" if reason is None else "failed" if reason in FAILED else "incomplete"
    result = {"schema": "advice/1", "run": told["run"], "release": told["release"], "lens": told["lens"],
              "status": status, "reason": reason, "findings": findings, "texts": texts, "off_change": off, "usage": usage}
    if validate(result, schemas["advice"], schemas=schemas):
        if reason is None:      # a Finding this file built that advice/1 refuses: no read, never a part of one
            return _result(told, "unparsed", [], [], 0, usage, schemas)
        raise ValueError("what the step was told builds no advice/1")
    return result


def unasked(told: dict, reason: str, asks: int, seconds, schemas: dict) -> dict:
    """The Result of a read that has no answer: over the day's ceiling, too large to ask, no key, out of time, or Azure
    not reached."""
    if reason not in UNASKED:
        raise ValueError("no answer in hand is one of %s" % ", ".join(UNASKED))
    return _result(told, reason, [], [], 0, _usage(told, None, (None, None), asks, seconds), schemas)


def _responses(body: dict) -> tuple:
    """`(reason, text)` of a response of the Responses API."""
    state = body.get("status")
    if state in ("queued", "in_progress"):
        return "timed_out", None
    if state == "incomplete":
        details = body.get("incomplete_details")
        filtered = isinstance(details, dict) and details.get("reason") == "content_filter"
        return ("refused" if filtered else "cut_short"), None
    if state != "completed":
        return "transport", None
    output = body.get("output")
    parts = [part for item in (output if isinstance(output, list) else [])
             if isinstance(item, dict) and item.get("type") == "message" and isinstance(item.get("content"), list)
             for part in item["content"]]
    if any(isinstance(part, dict) and part.get("type") == "refusal" for part in parts):
        return "refused", None
    said = [part.get("text") for part in parts if isinstance(part, dict) and part.get("type") == "output_text"]
    return (None, said[0]) if len(said) == 1 and type(said[0]) is str else ("unparsed", None)


def _chat(body: dict) -> tuple:
    """`(reason, text)` of a chat completion."""
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return "unparsed", None
    ended, message = choices[0].get("finish_reason"), choices[0].get("message")
    if ended == "length":
        return "cut_short", None
    if ended == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
        return "refused", None
    if ended != "stop" or not isinstance(message, dict) or type(message.get("content")) is not str:
        return "unparsed", None
    return None, message["content"]


def _answered(text: str, schemas: dict):
    """The object a reader's text is, held to advice-answer/1, or None."""
    text = text.strip()
    fenced = FENCED.fullmatch(text)
    try:
        answer = json.loads(fenced.group(1) if fenced else text)
    except (ValueError, RecursionError):
        return None
    return answer if isinstance(answer, dict) and not validate(answer, schemas["advice-answer"], schemas=schemas) else None


def _findings(told: dict, answer: dict) -> tuple:
    actor = "%s@%s" % (told["deployment"], told["model"])
    changed, shared, findings, texts, off = set(told["changed_paths"]), {}, [], [], 0
    for said in answer["findings"]:
        path = said["file"]
        line = said["line"] if path is not None else None       # a line of no file names no place
        if path is not None and path not in changed:
            off += 1
            continue
        key = json.dumps([told["lens"], "advisory", actor, told["content_id"], path, line, said["severity"]])
        shared[key] = shared.get(key, -1) + 1
        ident = "%s:%s" % (told["lens"], hashlib.sha256(("%s#%d" % (key, shared[key])).encode()).hexdigest())
        finding = {"schema": "finding/1", "id": ident, "source": {"lens": told["lens"], "kind": "advisory", "actor": actor},
                   "surface": {"type": "annotation", "key": ident}, "category": "uncategorised",
                   "severity": said["severity"], "criterion": None, "content_id": told["content_id"]}
        if path is not None:
            finding["location"] = {"path": path} if line is None else {"path": path, "start_line": line}
        findings.append(finding)
        texts.append({"id": ident, "category": said["category"], "criterion": said["criterion"],
                      "body": ("%s\n\n%s" % (said["title"], said["message"]))[:told["characters"]]})
    return findings, texts, off


def read(told: dict, answer: dict, asks: int, seconds, schemas: dict) -> dict:
    """The Result of what the transport returned for the last ask. `told` is the step's own: the run, the release, the
    Lens, the content id, the change's paths, the API, the deployment, the pinned model, the effort, the cap on a text
    and the prices."""
    status, body = answer.get("status"), answer.get("body")
    known = isinstance(body, dict) and status == 200
    usage = body.get("usage") if known and isinstance(body.get("usage"), dict) else {}
    names = ("input_tokens", "output_tokens") if told["api"] == "responses" else ("prompt_tokens", "completion_tokens")
    model = body.get("model") if known else None
    spent = _usage(told, model, (_count(usage.get(names[0])), _count(usage.get(names[1]))), asks, seconds)
    if not known:
        reason = "rate_limited" if status == 429 else "no_key" if status in (401, 403) else "transport"
        return _result(told, reason, [], [], 0, spent, schemas)
    reason, text = _responses(body) if told["api"] == "responses" else _chat(body)
    if reason is None and model != told["model"]:
        reason = "not_the_model"
    found = _answered(text, schemas) if reason is None else None
    if found is None:
        return _result(told, reason or "unparsed", [], [], 0, spent, schemas)
    findings, texts, off = _findings(told, found)
    return _result(told, None, findings, texts, off, spent, schemas)
