"""What the draft pull request an opening Run opens may say in its title and body (issue 838; the Factory Builder's
ruling 4 on S6).

The title and the body come from the Result, written by a model. `apply` writes them with a line of its own, which
closes the Run's issue and no other: so that line is the only link in the draft, and the Result's text links nothing,
mentions no one and closes nothing.

- `refusal(title, body)`: None where the draft may say them, or the one reason, a code, why it may not. The first
  of these that holds is the one given:
  - `UNREADABLE`: a title or a body that is no text of its exact kind; one that holds a lone surrogate, U+D800 to
    U+DFFF, which is no character, so no UTF-8 can carry it to GitHub; a title that is empty or blank, or holds a
    line break, a tab or another control character; a body that is empty or blank, or holds a control character
    but a line break or a tab; or text that reads as other text once GitHub renders it: a character reference (`&` before a letter or
    `#`), a percent-escape (`%` before a hex digit) or raw HTML (`<` before a letter, `/`, `!` or `?`).
  - `LINKS`: a reference GitHub could read as a link to an issue, a pull request or a discussion: `#` before a digit,
    so also `owner/repo#12`; `GH-` before a digit; a path whose part `issue`, `issues`, `pull`, `pulls` or
    `discussions` is followed by a digit, whatever its host or scheme; a Markdown link or image, inline (`](`) or by a
    reference or a footnote (`]:`), whose target may be relative: on a pull request's page, `[see](12)` is a link to
    pull request 12.
  - `MENTIONS`: `@` before a character a GitHub login may begin with, a letter or a digit.
  - `CLOSES`: a closing keyword as a word of its own: close, closes, closed, fix, fixes, fixed, resolve, resolves or
    resolved, in any case.

Each is read in any case, of the text as it is and of the same text with every backslash taken out, since Markdown
drops the backslash of an escape (`GH\\-12` renders as `GH-12`); and a path's part is read with every slash taken out,
so `issues//12` is read as `issues/12`.

What is refused more widely than GitHub links or closes, on purpose: refusing a harmless title costs a Run, and a link
let through binds or notifies what no one admitted.
- A mark is refused wherever it stands, inside a word, in code and in a URL: GitHub links `#12` only after a space or
  a mark, never in code, and `@name` only where no letter comes before it; the bounds of a word differ between its
  readers and this one. So an e-mail address is refused as a mention, `x#1` as a link, and `fix` before no reference.
- A word is a run of ASCII letters once the text is case-folded: `fix_up`, `fix2` and `pre-fix` each hold `fix`, and
  so does `fix` written with the ligature U+FB01, which folds to two letters. `fixture` and `prefix` are words of
  their own.
- Every character reference, percent-escape and tag, raw HTML's comment among them, is refused: each makes the text
  GitHub reads, or a reader follows, other than the text this reads. `&#35;12` renders as `#12`, `#<!-- -->12` may,
  `issues/%31%32` leads to issue 12, and a link GitHub makes of a tag shows none of its target.

Its stated limits:
- GitHub also links a commit's SHA, `owner/repo@sha` (refused as a mention where the SHA begins with a letter), a URL
  to a user, a repository, a file or a commit, and a repository's own autolink prefixes: none is an issue or a pull
  request, none notifies anyone and none closes anything, so each is let through.
- A mark is read only as ASCII writes it: GitHub reads no other `#`, `@`, digit or hyphen in a reference or a
  mention, so a full-width number sign before a digit is let through.
- That `apply`'s own line reads as written is `apply`'s, and not this guard's: written after the Result's text, an
  unclosed code fence there would make it code; written before, nothing that follows changes how it reads.
- How long a title and a body may be is `effect/1`'s schema's to bound: a guard writes no number.

`apply` gives both arguments; this reads nothing itself.
"""
from __future__ import annotations

UNREADABLE = "opening_unreadable"   # no text, or text that reads as other text once GitHub renders it
LINKS = "opening_links"             # a reference to an issue or a pull request, or a link whose target may be one
MENTIONS = "opening_mentions"       # an @-mention, or what may be one
CLOSES = "opening_closes"           # a closing keyword in the Result's own text

# What a body may not hold: every control character but a line break and a tab, the line separators among them.
CONTROL = ("\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\r\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b"
           "\x1c\x1d\x1e\x1f\x7f\x80\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8d\x8e\x8f\x90\x91\x92\x93\x94"
           "\x95\x96\x97\x98\x99\x9a\x9b\x9c\x9d\x9e\x9f\u2028\u2029")
# The first and the last surrogate: a str may hold one alone, as JSON's escape gives it, but it is no character, and
# no UTF-8 encodes it. Compared as characters, since a guard writes no number but 0 and 1.
SURROGATE_FIRST = "\ud800"
SURROGATE_LAST = "\udfff"
# And what a title may not hold beside it: a title is one line.
BREAKS = "\t\n"
DIGITS = "0123456789"
HEX = "0123456789abcdef"
LETTERS = "abcdefghijklmnopqrstuvwxyz"
# What a GitHub login may begin with, case-folded.
LOGIN_FIRST = "abcdefghijklmnopqrstuvwxyz0123456789"
# What a character reference holds after its `&`, and what raw HTML holds after its `<`.
REFERENCE = "abcdefghijklmnopqrstuvwxyz#"
TAG = "abcdefghijklmnopqrstuvwxyz/!?"
# The parts of a path to an issue, a pull request or a discussion that a number follows.
SEGMENTS = ("issue", "issues", "pull", "pulls", "discussions")
KEYWORDS = ("close", "closes", "closed", "fix", "fixes", "fixed", "resolve", "resolves", "resolved")


def _readings(said: str) -> list:
    """`said` case-folded, as it is and with every backslash taken out: the text, and the text Markdown renders."""
    folded = said.casefold()
    return [folded, "".join(folded.split("\\"))]


def _follows(text: str, mark: str, chars: str) -> bool:
    """Whether `mark` stands in `text` with one of `chars` right after it."""
    return any(piece and piece[:1] in chars for piece in text.split(mark)[1:])


def _text(said, banned: str) -> bool:
    """Whether `said` is text of its exact kind that holds none of `banned` and no lone surrogate, and nothing that reads
    as other text."""
    if type(said) is not str or any(c in banned or SURROGATE_FIRST <= c <= SURROGATE_LAST for c in said):
        return False
    return not any(_follows(text, "&", REFERENCE) or _follows(text, "%", HEX) or _follows(text, "<", TAG)
                   for text in _readings(said))


def _links(text: str) -> bool:
    bare = "".join(text.split("/"))
    return (_follows(text, "#", DIGITS) or _follows(text, "gh-", DIGITS) or "](" in text or "]:" in text
            or any(_follows(bare, segment, DIGITS) for segment in SEGMENTS))


def _closes(text: str) -> bool:
    words = "".join(c if c in LETTERS else " " for c in text).split()
    return any(word in KEYWORDS for word in words)


def refusal(title, body):
    """None where a draft may be opened with `title` and `body`, the Result's own, or the one reason why not."""
    if not (_text(title, CONTROL + BREAKS) and title.split() and _text(body, CONTROL) and body.split()):
        return UNREADABLE
    texts = _readings(title) + _readings(body)
    if any(_links(text) for text in texts):
        return LINKS
    if any(_follows(text, "@", LOGIN_FIRST) for text in texts):
        return MENTIONS
    if any(_closes(text) for text in texts):
        return CLOSES
    return None
