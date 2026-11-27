"""The draft an opening Run opens: its title and body as `apply` writes them (issue 838; decisions 0238 and 1321).

`draft(opening, issue)` is what `apply` writes of a Result's `open_pull_request`, `(None, (title, body))`, or why it
writes nothing, `(code, None)`. The title and the body are the model's (decision 0238). What is added is `apply`'s, read
from the issue the Decision admitted, never from the Result:
- The title gains ` (#N)`, the issue's number, which `tools/pr_title.py` asks a pull request's title to end with. The
  model's text is first held to `guards/opening.py`, which refuses `#N` in it. The whole title is then held to
  `pr_title.problems`, the rule CI's `commits` job holds the pull request's title to, by the same code, not a copy of it.
  A title it finds any problem in is refused by that problem's code, never cut or mended.
- The body is led by the one line that closes the issue, `Closes #N`, and a blank line, as `trials/P-46.json` shows
  GitHub reads a closing line at a body's start. Before the model's text, nothing in that text, an unclosed code fence
  among them, can make the line code or hide it. The whole body is then held to `pr_title.body_problems`, the
  template's four headings that CI's `commits` job holds the pull request's body to, and refused by that problem's code.

Each code is the Role's: `apply` gives it as the Result's refusal, before any token is minted, so a refused draft is the
Role's attempt and counts toward its bound. `told(issue)` is what the Run is told of its draft: the title's rule, the
room the suffix leaves and the body's headings.

Its stated limits: a title or a body over GitHub's bound in UTF-8 bytes is the writer port's to refuse, and is not held
here (decision 0238). Nothing here reads a clock, a file or the network.

Still to come, by hand: the push loop, `harness/push.py`, which `adapters/push.py` names, and `apply`'s dispatch of the
push and the draft.
"""
from __future__ import annotations

from guards import opening as text
from tools import pr_title

SUFFIX = " (#%d)"           # after the model's title: the issue it serves, as tools/pr_title.py asks a title to end
CLOSING = "Closes #%d\n\n"  # before the model's body: the draft's one link, a closing line, then a blank line


def room(issue: int) -> int:
    """How long the model's title may be, in characters: the longest title `tools/pr_title.py` keeps, less the suffix."""
    return pr_title.LONGEST - len(SUFFIX % issue)


def told(issue: int) -> str:
    """What a Run that opens a draft is told of its title and body, from `tools/pr_title.py`'s own rule and marks."""
    marks = ", ".join(what for what, _ in pr_title.INTERNAL)
    headings = ", ".join("## " + name for name in pr_title.HEADINGS)
    return ("\n\nYour draft's title is held to the rule for a pull request's title: its area, a lowercase word, a colon "
            "and a space, then a plain verb phrase that starts with a lowercase letter and ends with no stop, holding "
            "none of these: %s. It is at most %d characters, since the Harness adds the issue's number after it. The "
            "Harness writes the line that closes the issue, before your body. Your body has these headings, each "
            "once, in this order, each over some text of your own: %s. Your title and body hold no # before a "
            "digit, no @ before a letter or a digit, no link, no raw HTML, and no word close, fix or resolve in any "
            "form, even one that names no issue. A draft that breaks any of this is refused, as your attempt."
            % (marks, room(issue), headings))


def draft(opening: dict, issue: int) -> tuple:
    """`(None, (title, body))`, the draft `apply` writes of the Result's opening for issue `issue`, or `(code, None)`:
    the guard's code for the model's text, or the first problem `tools/pr_title.py` finds in the whole title, then in
    the whole body."""
    title, body = opening["title"]["body"], opening["body"]
    why = text.refusal(title, body)
    if why:
        return why, None
    whole, written = title + SUFFIX % issue, CLOSING % issue + body
    found = pr_title.problems(whole) or pr_title.body_problems(written)
    if found:
        return found[0].split(":", 1)[0], None
    return None, (whole, written)
