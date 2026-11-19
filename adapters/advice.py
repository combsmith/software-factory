"""An advisory Lens's Result, built from what its reader answered (decision 0224). It is pure: it reads no file, no clock
and no network, and is handed the schemas it holds an answer and its own Result to. `read` takes the answer the second
transport returned, `{status, headers, body}`, and `unasked` takes the reason no answer is in hand. Each returns an
`advice/1`: `completed` only when the call completed, the answer was not cut short, it names the pinned model and it is
one object held to `advice-answer/1`; otherwise `incomplete` or `failed`, with one code and no Finding.

What the reader says is the author's diff at one remove, so nothing of it is trusted. Its severity is kept as its
opinion, its category and criterion as hints beside its text, and its title and message under `body` alone. A Finding
is `uncategorised` with no criterion, on an annotation whose key is its id, and its id is its Lens's name and half a
sha256 of its source, the content id, its path, its line, its severity and its place among the Findings that share all
five: never of its text, and short enough to be the key `result/1` adopts from. A reader's file is compared, whole and
as it is written, with the change's paths, and is never opened, joined or made tidy: a Finding whose path the change
does not hold, or that is no one word, is counted and left out.

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
# A path advice/1 holds: one word, with no control and nothing that turns the line it is shown on.
PLACE = re.compile(r"[^\s\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]{1,1024}")
DIGITS = 64             # a whole number of this many digits no count or line needs: Python reads one of any length
COUNTED = 1000000000    # the most tokens advice/1 holds a count of; one Azure gives above it is not known
MOST = 100              # the findings one answer may hold, as its schema says: more are not handed to the validator
MILLION = 1000000
# The name of the check run that shows an advisory Lens's Result. It is always neutral, and no ruleset may name it
# (tools/check_rulesets.py), since a ruleset counts a neutral check as met.
CHECK = "advisory-%s"
# What `apply` shows of a Result (decision 0224, "What is shown"). An annotation's level is never `failure`, whatever
# its Finding's severity: a reader is wrong too often for a red mark, so the two graver severities are a `warning` and
# the two lighter a `notice`.
SEVERITIES = ("blocking", "major", "minor", "info")
LEVEL = {"blocking": "warning", "major": "warning", "minor": "notice", "info": "notice"}
ANNOTATIONS = 50        # GitHub takes at most fifty annotations in one request, and one request is all that is sent
HEADLINE = 255          # the characters of an annotation's title, GitHub's own bound
MESSAGE = 8000          # the characters of an annotation's message: under GitHub's 64 KiB whatever the characters are
LARGEST = 4 * 1024 * 1024       # the bytes of a Result's file `apply` reads: one over it is not read as one
# What `apply` says it did with one Lens's Result, the codes applied/1 holds (its schema lists the same): shown, or why
# not. A token GitHub did not confirm revoked is `token_not_revoked`, whatever was shown through it.
CODES = ("shown", "advice_missing", "advice_digest_differs", "advice_invalid", "advice_disagrees", "advice_not_the_runs",
         "advice_not_the_lens", "advice_not_the_content", "advice_finding_not_its_own", "advice_text_not_its_findings",
         "item_not_read", "superseded", "run_not_whole", "out_of_time", "token_not_minted", "not_written",
         "not_read_back", "write_raised", "token_not_revoked")
LENS = re.compile(r"[a-z]{1,31}")
RUN = re.compile(r"r_[0-9A-Z]{6,26}")
# What no annotation's words hold: a control but a message's newline and tab, what turns the line they are shown on,
# a line or paragraph separator, and half a surrogate pair.
UNSHOWN = ("\x00-\x08\x0b-\x1f\x7f-\x9f\xad\u061c\u180e\u200b-\u200f\u2028-\u202e\u2060-\u206f\ud800-\udfff"
           "\ufeff\ufff9-\ufffb\U000e0000-\U000e007f")
PARTED = "[\x0b\x0c\x85\u2028\u2029]"       # what parts two words as a line's end does: shown as a space, so they do not join
SURROGATE = re.compile("[\ud800-\udfff]")
CODED = re.compile(r"(completed|incomplete \((%s)\)|failed \((%s)\)): [0-9]{1,3} blocking, [0-9]{1,3} major, [0-9]{1,3} "
                   r"minor, [0-9]{1,3} info; [0-9]{1,3} off the change" % ("|".join(INCOMPLETE), "|".join(FAILED)))
SUMMARY = "An advisory read: it gates nothing. %d finding(s): %d annotated, %d with no line, %d left out past %d annotations."
SUMMED = re.compile(re.escape(SUMMARY).replace("%d", "([0-9]{1,3})"))
# The reasons a chat completion's one choice may say it ended for: any other has not ended.
ENDINGS = ("stop", "length", "content_filter", "tool_calls", "function_call")


def _count(value):
    return value if type(value) is int and 0 <= value <= COUNTED else None


def _counts(usage: dict, names: tuple, silent: bool) -> tuple:
    """`(asked, answered)`, the tokens of a read that ended, each a whole count or None. A count that contradicts
    itself is not known, neither of its two, so that the cost is not and is never lower than what was billed: a prompt
    of no tokens, an answer of no tokens from any read but one a content filter ended with no words, a total above the
    two, or reasoning above the output it is part of. A total below the two is priced at their sum, the higher figure,
    which errs toward the ceiling."""
    asked, answered = _count(usage.get(names[0])), _count(usage.get(names[1]))
    total, details = usage.get("total_tokens"), usage.get(names[1] + "_details")
    thought = details.get("reasoning_tokens") if isinstance(details, dict) else None
    if asked is not None and answered is not None and (
            asked == 0 or (answered == 0 and not silent) or (type(total) is int and total > asked + answered)
            or (type(thought) is int and thought > answered)):
        return None, None
    return asked, answered


def _usage(told: dict, model, tokens: tuple, asks: int, seconds) -> dict:
    asked, answered = tokens
    cost = None
    # Only the pinned model's answer is priced: another's is not the model's, and its prices are not the pinned one's.
    # A cost is counted in millionths of a dollar and rounded up to a whole one, never down to nought, once the float's
    # own noise below it is gone.
    if asked is not None and answered is not None and model == told["model"]:
        price = told["usd_per_million"]
        millionths = round(asked * price["input"] + answered * price["output"], 6)
        cost = -(-millionths // 1) / MILLION
    return {"api": told["api"], "deployment": told["deployment"], "model": told["model"],
            "answering_model": model if type(model) is str and MODEL.fullmatch(model) else None,
            "effort": told["effort"], "asks": asks, "input_tokens": asked, "output_tokens": answered,
            "cost_usd": cost, "seconds": seconds}


def _result(told: dict, reason, findings: list, texts: list, off: int, usage: dict, schemas: dict) -> dict:
    status = "completed" if reason is None else "failed" if reason in FAILED else "incomplete"
    result = {"schema": "advice/1", "run": told["run"], "release": told["release"], "lens": told["lens"],
              "status": status, "reason": reason, "findings": findings, "texts": texts, "off_change": off, "usage": usage}
    if validate(result, schemas["advice"], schemas=schemas):
        raise ValueError("what the step was told builds no advice/1")
    return result


def unasked(told: dict, reason: str, asks: int, seconds, schemas: dict) -> dict:
    """The Result of a read that has no answer: over the day's ceiling, too large to ask, no key, out of time, or Azure
    not reached."""
    if reason not in UNASKED:
        raise ValueError("no answer in hand is one of %s" % ", ".join(UNASKED))
    return _result(told, reason, [], [], 0, _usage(told, None, (None, None), asks, seconds), schemas)


def _fault(body) -> str:
    """The code of what Azure's own error says, where it says one this file knows: else None."""
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return {"content_filter": "refused", "context_length_exceeded": "too_large",
            "rate_limit_exceeded": "rate_limited"}.get(code if isinstance(code, str) else None)


def _responses(body: dict) -> tuple:
    """`(reason, text)` of a response of the Responses API."""
    state, details = body.get("status"), body.get("incomplete_details")
    if state in ("queued", "in_progress"):
        return "timed_out", None
    if state == "incomplete" or details is not None:
        filtered = isinstance(details, dict) and details.get("reason") == "content_filter"
        return ("refused" if filtered else "cut_short"), None
    if state != "completed" or body.get("error") is not None:
        return _fault(body) or "transport", None
    output = body.get("output")
    messages = [item for item in (output if isinstance(output, list) else [])
                if isinstance(item, dict) and item.get("type") == "message" and isinstance(item.get("content"), list)]
    if any(item.get("status") == "incomplete" for item in messages):
        return "cut_short", None
    parts = [part for item in messages for part in item["content"]]
    if any(isinstance(part, dict) and part.get("type") == "refusal" for part in parts):
        return "refused", None
    said = [part.get("text") for part in parts if isinstance(part, dict) and part.get("type") == "output_text"]
    return (None, said[0]) if len(said) == 1 and type(said[0]) is str else ("unparsed", None)


def _chat(body: dict) -> tuple:
    """`(reason, text)` of a chat completion."""
    if body.get("error") is not None:
        return _fault(body) or "transport", None
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


def _finished(body: dict) -> bool:
    """Whether a chat completion holds its one choice, ended for a reason the API names: one that does not has not
    answered."""
    choices = body.get("choices")
    return isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict) \
        and type(choices[0].get("finish_reason")) is str and choices[0]["finish_reason"] in ENDINGS


def _silent(body: dict, api: str) -> bool:
    """Whether a read that ended was ended by a content filter and holds no words anywhere: the one read that may have
    answered no tokens. An empty text is no words."""
    if api == "responses":
        details, output = body.get("incomplete_details"), body.get("output")
        filtered = body.get("status") == "incomplete" and isinstance(details, dict) \
            and details.get("reason") == "content_filter"
        parts = [part for item in (output if isinstance(output, list) else [])
                 if isinstance(item, dict) and isinstance(item.get("content"), list) for part in item["content"]]
        return filtered and not any(isinstance(part, dict) and (part.get("text") or part.get("refusal")) for part in parts)
    choice = body["choices"][0]
    message = choice.get("message")
    return choice.get("finish_reason") == "content_filter" \
        and not (isinstance(message, dict) and (message.get("content") or message.get("refusal")))


def _whole(digits: str) -> int:
    if len(digits) >= DIGITS:
        raise ValueError("a whole number of more digits than a count or a line has")
    return int(digits)


def _once(pairs: list) -> dict:
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("a key is given twice")
    return dict(pairs)


def _answered(text: str, schemas: dict):
    """The object a reader's text is, held to advice-answer/1, or None. A key given twice is no answer: JSON would keep
    the last, and a second `findings` that is empty would make a read with findings a clean one."""
    text = text.strip()
    fenced = FENCED.fullmatch(text)
    try:
        answer = json.loads(fenced.group(1) if fenced else text, object_pairs_hook=_once, parse_int=_whole)
    except (ValueError, RecursionError):
        return None
    if not isinstance(answer, dict) or (isinstance(answer.get("findings"), list) and len(answer["findings"]) > MOST):
        return None             # before the validator, which would write an error for each of a million
    return answer if isinstance(answer, dict) and not validate(answer, schemas["advice-answer"], schemas=schemas) else None


def _findings(told: dict, answer: dict) -> tuple:
    actor = "%s@%s" % (told["deployment"], told["model"])
    changed, shared, findings, texts, off = set(told["changed_paths"]), {}, [], [], 0
    for said in answer["findings"]:
        path = said["file"]
        line = said["line"] if path is not None else None       # a line of no file names no place
        if path is not None and (path not in changed or not PLACE.fullmatch(path)):
            off += 1
            continue
        key = json.dumps([told["lens"], "advisory", actor, told["content_id"], path, line, said["severity"]])
        shared[key] = shared.get(key, -1) + 1
        ident = "%s:%s" % (told["lens"], hashlib.sha256(("%s#%d" % (key, shared[key])).encode()).hexdigest()[:32])
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
    # What a response says of its tokens while it is still running, or once it is cancelled, is not what it cost:
    # only one that has ended, a response as completed or incomplete and a chat completion with its one choice's
    # reason, is priced, and any other read's cost is not known.
    ended = known and body.get("error") is None \
        and (body.get("status") in ("completed", "incomplete") if told["api"] == "responses" else _finished(body))
    usage = body.get("usage") if ended and isinstance(body.get("usage"), dict) else {}
    names = ("input_tokens", "output_tokens") if told["api"] == "responses" else ("prompt_tokens", "completion_tokens")
    model = body.get("model") if ended else None      # one that has not answered names no model that did
    reason, text = (None, None) if not known else _responses(body) if told["api"] == "responses" else _chat(body)
    spent = _usage(told, model, _counts(usage, names, ended and _silent(body, told["api"])), asks, seconds)
    if not known:
        reason = "rate_limited" if status == 429 else "no_key" if status in (401, 403) else _fault(body) or "transport"
        return _result(told, reason, [], [], 0, spent, schemas)
    if reason is None and model != told["model"]:
        reason = "not_the_model"
    found = _answered(text, schemas) if reason is None else None
    if found is None:
        return _result(told, reason or "unparsed", [], [], 0, spent, schemas)
    findings, texts, off = _findings(told, found)
    return _result(told, None, findings, texts, off, spent, schemas)


def held(data, digest, lens: str, advisory, admit: dict, schemas: dict) -> tuple:
    """`(result, None)` for the bytes of an advisory Lens's Result that `apply` may show, or `(None, code)`. The bytes
    are taken by the digest written beside them, as the advise step wrote it, and held to `advice/1` and to the Run
    before anything of them is shown: the Run's own `run` and `release`, the Lens the file is named for, which the
    configuration names advisory, each Finding on the admitted content, its id its surface's key and its source the
    Lens, and one text for each Finding, by its id and in its order."""
    if not isinstance(data, bytes) or not isinstance(digest, bytes) or len(data) > LARGEST:
        return None, "advice_missing"
    if not isinstance(advisory, (list, tuple)) or not all(isinstance(name, str) for name in advisory):
        return None, "advice_not_the_lens"
    if digest != ("sha256:%s\n" % hashlib.sha256(data).hexdigest()).encode():
        return None, "advice_digest_differs"
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_once, parse_int=_whole, parse_constant=_whole)
    except (ValueError, RecursionError):
        return None, "advice_invalid"       # a key given twice, a number no count has, or no number, among them
    if not isinstance(result, dict) or any(isinstance(result.get(part), list) and len(result[part]) > MOST
                                           for part in ("findings", "texts")):
        return None, "advice_invalid"       # before the validator, which would write an error for each of a million
    if validate(result, schemas["advice"], schemas=schemas):
        return None, "advice_invalid"
    if any(SURROGATE.search(found.get("location", {}).get("path", "")) for found in result["findings"]):
        return None, "advice_invalid"       # half a surrogate pair is no part of a path, and the schema cannot say so
    # What the schema cannot say and the parser holds: a status and its reason agree, and only a read holds Findings.
    reason = result["reason"]
    if result["status"] != ("completed" if reason is None else "incomplete" if reason in INCOMPLETE else "failed") \
            or (reason is not None and (result["findings"] or result["texts"] or result["off_change"])):
        return None, "advice_disagrees"
    if (result["run"], result["release"]) != (admit["run"], admit["release"]):
        return None, "advice_not_the_runs"
    if lens not in advisory or result["lens"] != lens:
        return None, "advice_not_the_lens"
    if any(found["content_id"] != admit["content_id"] for found in result["findings"]):
        return None, "advice_not_the_content"
    if any(found["id"] != found["surface"]["key"] or found["source"]["lens"] != lens
           or not found["id"].startswith(lens + ":") for found in result["findings"]):
        return None, "advice_finding_not_its_own"
    ids = [found["id"] for found in result["findings"]]
    if len(set(ids)) != len(ids) or [text["id"] for text in result["texts"]] != ids:
        return None, "advice_text_not_its_findings"
    return result, None


def shown(result: dict) -> tuple:
    """`(output, ids)`: a check run's output for a Result `held` let through, and the ids of the Findings annotated.
    The title is codes and counts alone: the status, its reason if it has one, the Findings by severity and those off
    the change. The summary is counts too. A reader's words are an annotation's title and message and nothing else: the
    first line of its text and the rest. A Finding with no line is counted and not annotated, and so is each past the
    fiftieth, the graver first."""
    findings = result["findings"]
    status = result["status"] if result["reason"] is None else "%s (%s)" % (result["status"], result["reason"])
    counts = ", ".join("%d %s" % (sum(f["severity"] == s for f in findings), s) for s in SEVERITIES)
    bodies = {text["id"]: text["body"] for text in result["texts"]}
    placed = sorted((f for f in findings if "start_line" in f.get("location", {})),
                    key=lambda f: SEVERITIES.index(f["severity"]))
    kept, notes = placed[:ANNOTATIONS], []
    for f in kept:
        first, _, rest = bodies[f["id"]].partition("\n")
        first, rest = re.sub(PARTED + "|\t", " ", first), re.sub(PARTED, " ", rest)
        first, rest = re.sub("[%s]" % UNSHOWN, "", first).strip(), re.sub("[%s]" % UNSHOWN, "", rest).strip()
        line = f["location"]["start_line"]
        note = {"path": f["location"]["path"], "start_line": line, "end_line": line,
                "annotation_level": LEVEL[f["severity"]], "message": (rest or first or "(no text)")[:MESSAGE]}
        if first and rest:
            note["title"] = first[:HEADLINE]
        notes.append(note)
    summary = SUMMARY % (len(findings), len(kept), len(findings) - len(placed), len(placed) - len(kept), ANNOTATIONS)
    return ({"title": "%s: %s; %d off the change" % (status, counts, result["off_change"]), "summary": summary,
             "annotations": notes}, [f["id"] for f in kept])


def _lined(value) -> bool:
    return type(value) is int and 1 <= value <= 999999999


def showable(output) -> bool:
    """Whether a check run's output is one `shown` builds, and nothing beside it: a title of codes and counts, the
    summary's one sentence of counts, and at most fifty annotations, each a path, its line, a level that is no failure
    and a reader's words within their bounds. What a check run's output may hold beyond these, it may not."""
    if not isinstance(output, dict) or set(output) != {"title", "summary", "annotations"}:
        return False
    notes = output["annotations"]
    if not isinstance(output["title"], str) or not CODED.fullmatch(output["title"]) or not isinstance(notes, list) \
            or not isinstance(output["summary"], str) or not SUMMED.fullmatch(output["summary"]) or len(notes) > ANNOTATIONS:
        return False
    if int(SUMMED.fullmatch(output["summary"]).group(2)) != len(notes):
        return False            # the summary's count of the annotated is of the annotations sent
    for note in notes:
        if not isinstance(note, dict) or set(note) - {"title"} != {"path", "start_line", "end_line", "annotation_level",
                                                                  "message"}:
            return False
        words = [note["message"]] + ([note["title"]] if "title" in note else [])
        level = note["annotation_level"]
        if not isinstance(note["path"], str) or not PLACE.fullmatch(note["path"]) or SURROGATE.search(note["path"]) \
                or not _lined(note["start_line"]) or not _lined(note["end_line"]) or note["end_line"] != note["start_line"] \
                or not isinstance(level, str) or level not in set(LEVEL.values()) \
                or not all(isinstance(said, str) and said.strip() and not re.search("[%s]" % UNSHOWN, said) for said in words) \
                or len(note["message"]) > MESSAGE or len(note.get("title", "")) > HEADLINE or "\n" in note.get("title", ""):
            return False
    return True
