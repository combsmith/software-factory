"""What the draft pull request an opening Run opens may say in its title and body (issue 838; the Factory Builder's
ruling 4 on S6).

The title and the body come from the Result, written by a model. `apply` writes them with what it adds itself: the
issue's `(#N)` after the title, and a line that closes the Run's issue and no other. So those are the only links in
the draft, and the Result's text links nothing, mentions no one and closes nothing.

- `refusal(title, body)`: None where the draft may say them, or the one reason, a code, why it may not. The first
  of these that holds is the one given:
  - `UNREADABLE`: a title or a body that is no text of its exact kind; one that holds a lone surrogate, U+D800 to
    U+DFFF, which is no character, so no UTF-8 can carry it to GitHub; a title that is empty or blank, or holds a
    line break, a tab or another control character; a body that is empty or blank, or holds a control character
    but a line break or a tab; a title or a body of characters that show nothing alone: Unicode's default-ignorable
    ones, as `guards/patch.py`'s `IGNORABLE` lists them, U+180F, and the Braille blank U+2800; a bidi control, U+200E,
    U+200F, U+061C, U+202A to U+202E or U+2066 to U+2069, or a format control of their kind, U+206A to U+206F or
    U+FFF9 to U+FFFB, anywhere, which shows text in an order or a shape other than its own, or hides it; a tag
    character, U+E0000 to U+E007F, anywhere, an ASCII character that shows nothing, so text of them is hidden; or text
    that reads as other text once GitHub renders it: a character reference (`&` before a letter or `#`), a
    percent-escape (`%` before a hex digit) or raw HTML (`<` before a letter, `/`, `!` or `?`).
  - `LINKS`: a reference GitHub could read as a link to an issue, a pull request or a discussion: `#` before a digit,
    so also `owner/repo#12`; `GH-` before a digit; a path whose part `issue`, `issues`, `pull`, `pulls` or
    `discussions` is followed by a digit, whatever its host or scheme; a dot segment, `.` or `..` after a slash and
    before a space, a slash or a query, which a browser takes out of a path, so `issues/x/../12` leads to issue 12; a
    Markdown link or image, inline (`](`) or by a reference or a footnote (`]:`), whose target may be relative: on a
    pull request's page, `[see](12)` is a link to pull request 12; or a TeX command `\\href` or `\\url`, which GitHub's
    math may render as a link whose target the text names.
  - `MENTIONS`: `@` before a character a GitHub login may begin with, a letter or a digit.
  - `CLOSES`: a closing keyword as a word of its own: close, closes, closed, fix, fixes, fixed, resolve, resolves or
    resolved, in any case.

Each is read in any case, of the text as it is and of the same text with every backslash taken out, since Markdown
drops the backslash of an escape (`GH\\-12` renders as `GH-12`); a path's part is read with every slash taken out,
so `issues//12` is read as `issues/12`, and a dot segment with each backslash read as a slash, as a browser reads it.
A keyword is read in any run of characters, each case-folded, and only an ASCII letter as written, right before or after
the run, joins it to a longer word: a character that folds to letters (the Kelvin sign, `ß`, `ſ`, a ligature) joins
none, and a keyword written with one is read.

What is refused more widely than GitHub links or closes, on purpose: refusing a harmless title costs a Run, and a link
let through binds or notifies what no one admitted.
- A mark is refused wherever it stands, inside a word, in code and in a URL: GitHub links `#12` only after a space or
  a mark, never in code, and `@name` only where no letter comes before it; the bounds of a word differ between its
  readers and this one. So an e-mail address is refused as a mention, `x#1` as a link, and `fix` before no reference.
- A word is bounded by anything but an ASCII letter: `fix_up`, `fix2` and `pre-fix` each hold `fix`, and so do `fix`
  written with the ligature U+FB01 and `fix` after the Kelvin sign. `fixture` and `prefix` are words of their own.
- A path is read with every slash taken out, so a file's path `pu/ll2` is read as `pull2`, and refused.
- Every character reference, percent-escape and tag, raw HTML's comment among them, is refused: each makes the text
  GitHub reads, or a reader follows, other than the text this reads. `&#35;12` renders as `#12`, `#<!-- -->12` may,
  `issues/%31%32` leads to issue 12, and a link GitHub makes of a tag shows none of its target.

Its stated limits:
- GitHub also links a commit's SHA (`owner/repo@sha` is refused as a mention, since a login may begin with a letter
  or a digit) and a URL to a user, a repository, a file or a commit: none binds an issue or a pull request, notifies
  anyone or closes anything, so each is let through.
- A repository's own autolink prefixes are let through, and no prefix is refused: an admin sets each one's target,
  not the model, and this reads no settings. Even one whose target is an issue's page is, as far as is known, a plain
  link: no mention, no close and no cross-reference on the target. That is from memory, not a trial.
- An invisible character between a mark and a digit, `#` U+200B `12`, is let through: GitHub links no reference so
  split, and the text shows one only to the eye.
- A mark is read only as ASCII writes it: GitHub reads no other `#`, `@`, digit or hyphen in a reference or a
  mention, so a full-width number sign before a digit is let through.
- `\\href` and `\\url` are refused in any case and wherever they stand, in math or not, as a precaution: it is not
  known, and no trial asked, whether GitHub's math renders either as a link.
- That `apply`'s own line reads as written is `apply`'s, and not this guard's: written after the Result's text, an
  unclosed code fence there would make it code; written before, nothing that follows changes how it reads.
- Blank is read of characters, not of what Markdown renders: a body of its marks alone, `#`, `**` or `-`, with or
  without what shows nothing between them, is let through. It links, mentions and closes nothing.
- A variation selector inside text is let through, as an emoji needs one, and so is a run of them, which may carry
  bytes no one sees: what shows is all a reader of the page is given, and a model that reads the body is the
  reader's to bound.
- How long a title and a body may be is `effect/1`'s schema's to bound: a guard writes no number. The issue's
  `(#N)` after the title is `apply`'s too, and so is refusing a title too long to carry it.

`apply` gives both arguments; this reads nothing itself.
"""
from __future__ import annotations

from guards import patch

UNREADABLE = "opening_unreadable"   # no text, or text that reads as other text once GitHub renders it
LINKS = "opening_links"             # a reference to an issue or a pull request, or a link whose target may be one
MENTIONS = "opening_mentions"       # an @-mention, or what may be one
CLOSES = "opening_closes"           # a closing keyword in the Result's own text

# What a body may not hold: every control character but a line break and a tab, the line separators among them.
CONTROL = ("\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\r\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b"
           "\x1c\x1d\x1e\x1f\x7f\x80\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8d\x8e\x8f\x90\x91\x92\x93\x94"
           "\x95\x96\x97\x98\x99\x9a\x9b\x9c\x9d\x9e\x9f\u2028\u2029"
           # and the bidi controls, which show text in an order other than its own.
           "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
           # and the format controls of the same kind: how brackets mirror and digits are shaped, and the marks of an
           # annotation a renderer may hide.
           "\u206a\u206b\u206c\u206d\u206e\u206f\ufff9\ufffa\ufffb")
# What shows nothing alone, beside white space and `guards/patch.py`'s `IGNORABLE` (Unicode 13.0's): Unicode 14.0's
# fourth Mongolian variation selector, and the Braille blank. A title or a body of these is blank.
INVISIBLE = "\u180f\u2800"
# Unicode's tag characters, first and last: each is an ASCII character that shows nothing, so text of them is hidden.
TAG_FIRST = "\U000e0000"
TAG_LAST = "\U000e007f"
# The first and the last surrogate: a str may hold one alone, as JSON's escape gives it, but it is no character, and
# no UTF-8 encodes it. Compared as characters, since a guard writes no number but 0 and 1.
SURROGATE_FIRST = "\ud800"
SURROGATE_LAST = "\udfff"
# And what a title may not hold beside it: a title is one line.
BREAKS = "\t\n"
DIGITS = "0123456789"
HEX = "0123456789abcdef"
LETTERS = "abcdefghijklmnopqrstuvwxyz"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# What a GitHub login may begin with, case-folded.
LOGIN_FIRST = "abcdefghijklmnopqrstuvwxyz0123456789"
# What a character reference holds after its `&`, and what raw HTML holds after its `<`.
REFERENCE = "abcdefghijklmnopqrstuvwxyz#"
TAG = "abcdefghijklmnopqrstuvwxyz/!?"
# The parts of a path to an issue, a pull request or a discussion that a number follows.
SEGMENTS = ("issue", "issues", "pull", "pulls", "discussions")
# The TeX commands that make a link of their argument, as math may render them.
COMMANDS = ("\\href", "\\url")
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
    if type(said) is not str or any(c in banned or SURROGATE_FIRST <= c <= SURROGATE_LAST or TAG_FIRST <= c <= TAG_LAST
                                    for c in said):
        return False
    return not any(_follows(text, "&", REFERENCE) or _follows(text, "%", HEX) or _follows(text, "<", TAG)
                   for text in _readings(said))


def _links(text: str) -> bool:
    bare = "".join(text.split("/"))
    path = "/".join(text.split("\\"))
    return (_follows(text, "#", DIGITS) or _follows(text, "gh-", DIGITS) or "](" in text or "]:" in text
            or any(command in text for command in COMMANDS)
            or any(_follows(bare, segment, DIGITS) for segment in SEGMENTS)
            or any(part.split("?")[0].split()[:1] in ([".."], ["."]) for part in path.split("/")[1:]))


def _seen(said: str) -> list:
    """What of `said` shows: its words once each character that shows nothing alone is taken out."""
    return "".join(c for c in said if c not in INVISIBLE and not any(first <= c <= last for first, last in patch.IGNORABLE)
                   ).split()


def _closes(said: str) -> bool:
    """Whether a run of `said`'s characters folds to a keyword with no ASCII letter of `said`'s own right before or
    after it, as it is and with every backslash taken out. A character that folds to letters bounds a word, so it
    joins no keyword to a longer one, and a keyword written with one is read."""
    longest = max(len(key) for key in KEYWORDS)
    for text in (said, "".join(said.split("\\"))):
        for start in range(len(text)):
            if start and text[start - 1] in LETTERS + UPPER:
                continue
            folded = ""
            for end in range(start, len(text)):
                folded += text[end].casefold()
                if len(folded) > longest:
                    break
                if folded in KEYWORDS and not (end + 1 < len(text) and text[end + 1] in LETTERS + UPPER):
                    return True
    return False


def refusal(title, body):
    """None where a draft may be opened with `title` and `body`, the Result's own, or the one reason why not."""
    if not (_text(title, CONTROL + BREAKS) and _seen(title) and _text(body, CONTROL) and _seen(body)):
        return UNREADABLE
    texts = _readings(title) + _readings(body)
    if any(_links(text) for text in texts):
        return LINKS
    if any(_follows(text, "@", LOGIN_FIRST) for text in texts):
        return MENTIONS
    if _closes(title) or _closes(body):
        return CLOSES
    return None
