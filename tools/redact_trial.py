"""Take every credential out of a trial's raw capture, before anyone reads it.

    python3 -m tools.redact_trial < RAW > CLEAN 2> REPORT

Run it on the capture where it was written, in a scratch directory outside the repo, and read only
CLEAN. It takes the capture on standard input and writes what is left on standard output, so it
opens no path it is given (SonarCloud's S2083 and S8707). The capture is JSON (a drafted fixture,
or a body), or the text `gh api --include` prints: a status line, headers, a blank line and a body.
It applies the rules of `tools/check_trials.py`, so what it writes passes them. What it takes out
it names on standard error by where it was, never by what it held.

In JSON, a field named for a credential, or whose key or string is shaped like one, is deleted,
and so is such an item of a list. In a fixture, every place a credential was deleted from is added to
`removed`, and a header not on the list a fixture may keep is deleted too. In text, a header line
not on that list and any line shaped like a credential are deleted, and a body that is JSON is
treated as JSON.
"""
from __future__ import annotations

import json
import sys

from tools.check_trials import HEADERS, KEY_SHAPED, refused_key, shaped


def _clean(value, where: str, removed: list):
    """`value` without any field or item that is, or holds, a credential; each place is added to `removed`."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            shown = KEY_SHAPED if shaped(key) else key     # a place is never named by a credential
            here = "%s.%s" % (where, shown) if where else shown
            if refused_key(key) or shaped(key) or (isinstance(item, str) and shaped(item)):
                removed.append(here)
            else:
                out[key] = _clean(item, here, removed)
        return out
    if isinstance(value, list):
        out = []
        for i, item in enumerate(value):
            here = "%s[%d]" % (where, i)
            if isinstance(item, str) and shaped(item):
                removed.append(here)
            else:
                out.append(_clean(item, here, removed))
        return out
    if isinstance(value, str) and shaped(value):
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


def redact_text(raw: str, said: list) -> str:
    head, gap, body = raw.partition("\n\n")
    if not gap:
        head, body = "", raw
    kept = []
    for n, line in enumerate(head.splitlines(), 1):
        name, colon, _ = line.partition(":")
        header = n > 1 and colon and " " not in name.strip()
        if shaped(line) or (header and name.strip().lower() not in HEADERS):
            shown = KEY_SHAPED if shaped(name.strip()) else name.strip()    # a place is never named by a credential
            said.append("removed: line %d%s" % (n, ", the header " + shown if header else ""))
        else:
            kept.append(line)
    try:
        cleaned = json.dumps(redact_json(json.loads(body), said), indent=2) + "\n"
    except ValueError:
        lines, start = [], len(head.splitlines()) + (2 if gap else 0)
        for n, line in enumerate(body.splitlines(), start + 1):
            if shaped(line):
                said.append("removed: line %d" % n)
            else:
                lines.append(line)
        cleaned = "\n".join(lines) + ("\n" if lines else "")
    return ("\n".join(kept) + "\n\n" if gap else "") + cleaned


def main(argv: list, stdin=None, stdout=None, stderr=None) -> int:
    """Read the capture on `stdin`, write it clean to `stdout`, and name each removal on `stderr`. Any argument is
    refused: a path given here is never opened."""
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    if argv:
        print("usage: python3 -m tools.redact_trial < RAW > CLEAN 2> REPORT; it opens no path", file=stderr)
        return 2
    raw, said = (sys.stdin.buffer if stdin is None else stdin).read().decode("utf-8"), []
    try:
        out = json.dumps(redact_json(json.loads(raw), said), indent=2) + "\n"
    except ValueError:
        out = redact_text(raw, said)
    stdout.write(out)
    stdout.flush()
    for line in said:
        print(line, file=stderr)
    print("redacted: %d removed. Read only the clean output" % len(said), file=stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
