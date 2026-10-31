"""Take every credential out of a trial's raw capture, before anyone reads it.

    python3 -m tools.redact_trial < RAW > CLEAN 2> REPORT

Run it on the capture where it was written, in a scratch directory outside the repo, and read only
CLEAN. It takes the capture on standard input and writes what is left on standard output, so it
opens no path it is given (SonarCloud's S2083 and S8707). The capture is JSON (a drafted fixture,
or a body), or the text `gh api --include` prints: a status line, headers, a blank line and a body.
It applies the rules of `tools/check_trials.py`, so what it writes passes them. A check run's details on another site
keep their address and lose their query, which may hold what looks like a credential. What it takes out
it names on standard error by where it was, never by what it held.

In JSON, a field named for a credential, or whose key or string is shaped like one, is deleted,
and so is such an item of a list. A string is judged as a line of text is: one that holds a status line, or a field
named for a credential written inside it, is deleted too. NaN and Infinity are not JSON, and are refused. In a fixture, every place a credential was deleted from is added to
`removed`, and a header not on the list a fixture may keep is deleted too. In text, a header line
not on that list and any line shaped like a credential are deleted, and a body that is JSON is
treated as JSON. A capture may hold more than one head, as an interim answer or a proxy's gives one
before the response's; each is read as a head. A body that should be JSON, by its type or its first character,
and cannot be read as JSON is refused: nothing is written and the exit is 1.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse

from tools.check_trials import HEADERS, KEY_SHAPED, refused_key, shaped

STATUS = re.compile(r"HTTP/[0-9.]+ [0-9]{3}\b")
JSON_TYPE = re.compile(r"content-type\s*:.*\bjson\b", re.I)
# A status line in any case or indent, wherever a body is read: a head the reading did not find as one.
ANY_STATUS = re.compile(r"\s*HTTP/[0-9.]+\s+[0-9]{3}\b", re.I)
# A status line and nothing else: the version, the code and a reason phrase of words alone, as HTTP writes one.
STATUS_LINE = re.compile(r"HTTP/[0-9.]+ [0-9]{3}(?: [A-Za-z][A-Za-z '-]*)?\s*")
# A quoted name and a colon, as a field of JSON is written inside text: one named for a credential is never kept.
QUOTED_FIELD = re.compile(r'\\?"([^"\\]{1,64})\\?"\s*:')     # its quotes escaped once, too
# The same in single quotes, each kind read on its own, so the other quote inside a name is part of it.
SINGLE_FIELD = re.compile(r"'([^'\\]{1,64})'\s*:")
# A header line of a head: a name of no space, a colon, a value. A line folded onto the one before begins with a space.
HEADER = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+:")


# The fields a check run links to its details by, as REST and GraphQL spell them.
DETAILS = {"details_url", "detailsUrl"}


def _no_vendor_query(url: str) -> str:
    """`url` without its query where it is on another site than GitHub's. One that cannot be read as a URL is unchanged,
    and is judged as any string is."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
    except ValueError:
        return url
    return url.split("?", 1)[0] if parts.query and host != "github.com" else url


def _named(line: str) -> list:
    """Each name written as a field of JSON, or of a dict in single quotes, inside `line`."""
    return QUOTED_FIELD.findall(line) + SINGLE_FIELD.findall(line)


def _held(text: str) -> bool:
    """Whether a string of JSON holds a credential: by its shape, or as a text line would be refused for one, by a status
    line (a head and its headers written inside it) or a field named for a credential written inside it."""
    return shaped(text) or any(ANY_STATUS.match(line) or any(refused_key(name) for name in _named(line))
                               for line in text.splitlines())


def _clean(value, where: str, removed: list):
    """`value` without any field or item that is, or holds, a credential; each place is added to `removed`."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            shown = KEY_SHAPED if _held(key) else key     # a place is never named by a credential
            here = "%s.%s" % (where, shown) if where else shown
            if key in DETAILS and isinstance(item, str) and _no_vendor_query(item) != item:
                item = _no_vendor_query(item)
                removed.append(here + "?query")
            if refused_key(key) or _held(key) or (isinstance(item, str) and _held(item)):
                removed.append(here)
            else:
                out[key] = _clean(item, here, removed)
        return out
    if isinstance(value, list):
        out = []
        for i, item in enumerate(value):
            here = "%s[%d]" % (where, i)
            if isinstance(item, str) and _held(item):
                removed.append(here)
            else:
                out.append(_clean(item, here, removed))
        return out
    if isinstance(value, str) and _held(value):
        removed.append(where or "$")
        return None
    return value


def _unlisted_headers(data, dropped: list) -> None:
    """Delete each header of a fixture's exchanges that a fixture may not keep."""
    exchanges = data.get("exchanges") if isinstance(data, dict) else None
    for i, exchange in enumerate(exchanges if isinstance(exchanges, list) else []):
        for side in ("request", "response"):
            part = exchange.get(side) if isinstance(exchange, dict) else None
            headers = part.get("headers") if isinstance(part, dict) else None
            for name in list(headers) if isinstance(headers, dict) else []:
                if name.strip().lower() not in HEADERS:
                    del headers[name]
                    dropped.append("exchanges[%d].%s.headers.%s" % (i, side, name))


def redact_json(data, said: list):
    removed, dropped = [], []
    data = _clean(data, "", removed)
    _unlisted_headers(data, dropped)
    if isinstance(data, dict) and "exchanges" in data:
        data["removed"] = list(data.get("removed") or []) + removed
    said += ["removed: %s" % where for where in removed]
    said += ["dropped: %s, which is not a header a fixture may keep" % where for where in dropped]
    return data


class Unreadable(ValueError):
    """A body that should be JSON and cannot be read as JSON: it is refused whole, since its fields cannot be judged."""


def _opens_json(text: str) -> bool:
    """Whether `text` begins, past white space, as JSON does."""
    return text.lstrip()[:1] in ("{", "[")


def _constant(name: str):
    """NaN, Infinity or -Infinity, which Python reads and JSON does not: what holds one is not JSON, and is refused."""
    raise Unreadable("the capture holds %s, which is not JSON" % name)


def _fields(text: str):
    """`text` read as JSON. A JSON string is refused: it holds no field to judge, and a head or a credential may be
    written inside it."""
    data = json.loads(text, parse_constant=_constant)
    if isinstance(data, str):
        raise Unreadable("the capture is a JSON string, which holds no field to judge")
    return data


def _head(block: str, first: int, said: list) -> str:
    """`block`, a status line and its headers starting at line `first`, without a header a fixture may not keep or any
    line shaped like a credential. A line after the status line that is no header, a folded one among them, is refused:
    a head holds nothing else, and what is not a header cannot be judged as one."""
    kept = []
    for n, line in enumerate(block.splitlines(), first):
        if n == first and not STATUS_LINE.fullmatch(line):
            raise Unreadable("a head's status line holds more than a status")
        if n == first and shaped(line):
            # Deleted, it would leave headers with no status line above them: a head that is not one.
            raise Unreadable("a head's status line is shaped like a credential")
        if n > first and not HEADER.match(line):
            raise Unreadable("a head holds a line that is no header")
        if n > first and _opens_json(line.partition(":")[2]):
            raise Unreadable("a head holds a line that is no header")
        name, colon, _ = line.partition(":")
        header = n > first and colon and " " not in name.strip()
        if shaped(line) or (header and name.strip().lower() not in HEADERS):
            shown = KEY_SHAPED if shaped(name.strip()) else name.strip()    # a place is never named by a credential
            said.append("removed: line %d%s" % (n, ", the header " + shown if header else ""))
        else:
            kept.append(line)
    return "\n".join(kept)


def redact_text(raw: str, said: list) -> str:
    heads, body = [], raw
    if STATUS.match(raw):
        # An interim answer (100 Continue) or a proxy's (200 Connection established) comes with a head of its own
        # before the response's: each head that follows is read as one, and only what comes after the last is the body.
        # A later head ends at a blank line as every head does; a status line with none after it is the body, and is read
        # as one, never as a head.
        gap = "\n\n"
        while gap and (not heads or (STATUS.match(body) and "\n\n" in body)):
            head, gap, body = body.partition("\n\n")
            heads.append(head)
    kept, first = [], 1
    for head in heads:
        kept.append(_head(head, first, said))
        first += len(head.splitlines()) + 1
    try:
        cleaned = json.dumps(redact_json(_fields(body), said), indent=2) + "\n"
    except Unreadable:
        raise
    except ValueError:
        # What should be JSON and is not cannot be judged field by field, and a line of it may hold a credential no
        # shape finds under a name that would refuse it: it is refused whole, never kept in part.
        typed = any(JSON_TYPE.match(line) for head in heads for line in head.splitlines())
        if body.strip() and typed:
            raise Unreadable("the body should be JSON and cannot be read as JSON") from None
        lines = []
        for n, line in enumerate(body.splitlines(), first):
            # A line that opens as JSON, or a status line the reading did not take as a head's, is a shape this was
            # never meant to read as text: it is refused whole, never filtered for shapes alone.
            if _opens_json(line):
                raise Unreadable("the body should be JSON and cannot be read as JSON")
            if ANY_STATUS.match(line):
                raise Unreadable("the body holds a head it was not read as")
            if any(refused_key(name) for name in _named(line)):
                raise Unreadable("the body holds a field named for a credential, written as text")
            if shaped(line):
                said.append("removed: line %d" % n)
            else:
                lines.append(line)
        cleaned = "\n".join(lines) + ("\n" if lines else "")
    return "".join(head + "\n\n" for head in kept) + cleaned


def main(argv: list, stdin=None, stdout=None, stderr=None) -> int:
    """Read the capture on `stdin`, write it clean to `stdout`, and name each removal on `stderr`. Any argument is
    refused: a path given here is never opened."""
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    if argv:
        print("usage: python3 -m tools.redact_trial < RAW > CLEAN 2> REPORT; it opens no path", file=stderr)
        return 2
    # `gh api --include` ends its header lines with CR LF. Read as text from a file, they became LF; read as bytes they
    # stay, and a capture with no blank line between its headers and its body would be redacted as one body.
    raw = (sys.stdin.buffer if stdin is None else stdin).read().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    # A byte order mark would hide a status line from the reading of heads and a brace from the reading of JSON. A run's
    # log writes one at the start of its lines, so each is taken out before anything is read, and what it hid is read
    # as what it is.
    raw = raw.replace("\ufeff", "")
    said = []
    try:
        out = json.dumps(redact_json(_fields(raw), said), indent=2) + "\n"
    except Unreadable as refused:
        print("refused: %s, so none of it is kept; nothing is written" % refused, file=stderr)
        return 1
    except ValueError:
        try:
            out = redact_text(raw, said)
        except Unreadable as refused:
            print("refused: %s, so none of it is kept; nothing is written" % refused, file=stderr)
            return 1
    # Written as UTF-8 whatever the locale, as it was to a file.
    target = getattr(stdout, "buffer", None)
    if target is not None:
        target.write(out.encode("utf-8"))
        target.flush()
    else:
        stdout.write(out)
    for line in said:
        print(line, file=stderr)
    print("redacted: %d removed. Read only the clean output" % len(said), file=stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
