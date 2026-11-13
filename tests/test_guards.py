"""The guards on a Role's own writes (issue 838): `guards/patch.py`, a patch applied byte for byte or not at all."""
from __future__ import annotations

import os
import pathlib
import random
import subprocess
import tempfile
import unittest

from guards import patch, push

FILE = "100644"
OLD = b"a\nb\nc\nd\ne\nf\ng\nh\n"
CHANGE = (b"diff --git a/docs/a.md b/docs/a.md\nindex 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/a.md\n"
          b"@@ -2,3 +2,3 @@\n b\n-c\n+C\n d\n")
NEW = (b"diff --git a/docs/n.md b/docs/n.md\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n"
       b"+++ b/docs/n.md\n@@ -0,0 +1,2 @@\n+x\n+y\n")
GONE = (b"diff --git a/tests/t.py b/tests/t.py\ndeleted file mode 100644\nindex 1111111..0000000\n"
        b"--- a/tests/t.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
MOVED = (b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 87%\nrename from docs/a.md\nrename to docs/b.md\n"
         b"index 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/b.md\n@@ -1,2 +1,2 @@\n-a\n+A\n b\n")
COPIED = b"diff --git a/docs/a.md b/docs/c.md\nsimilarity index 100%\ncopy from docs/a.md\ncopy to docs/c.md\n"
MODE = b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 100755\n"
TREE = {"docs/a.md": FILE, "run.sh": "100755", "link": "120000", "vendored": "160000", "tests/t.py": FILE}
HELD = {"docs/a.md": OLD, "run.sh": b"#!/bin/sh\n", "link": b"docs/a.md", "tests/t.py": b"x\n"}


def section(name: str, hunks: bytes, old: str = None, extended: bytes = b"index 1111111..2222222 100644\n") -> bytes:
    """One section that changes `name`, or `old` into `name`, as git writes it."""
    was = (old or name).encode()
    return b"diff --git a/%s b/%s\n%s--- a/%s\n+++ b/%s\n%s" % (was, name.encode(), extended, was, name.encode(), hunks)


def new_file(hunks: bytes) -> bytes:
    return b"diff --git a/n b/n\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n+++ b/n\n" + hunks


def gone_file(hunks: bytes) -> bytes:
    return b"diff --git a/f b/f\ndeleted file mode 100644\nindex 1111111..0000000\n--- a/f\n+++ /dev/null\n" + hunks


def landed(data, tree=None, held=None):
    return patch.applied(data, TREE if tree is None else tree, HELD if held is None else held)


class Patch(unittest.TestCase):
    def test_a_patch_is_read_section_by_section_as_git_writes_it(self):
        line = lambda sign, text: {"sign": sign, "text": text, "bare": False}
        hunk = {"old_start": 2, "old_count": 3, "new_start": 2, "new_count": 3,
                "lines": [line(b" ", b"b"), line(b"-", b"c"), line(b"+", b"C"), line(b" ", b"d")]}
        self.assertEqual(patch.read(CHANGE), [{"kind": "change", "old": "docs/a.md", "new": "docs/a.md", "hunks": [hunk],
                                               "index_mode": "100644", "old_mode": None, "new_mode": None}])
        said = [(s["kind"], s["old"], s["new"], s["old_mode"], s["new_mode"], s["index_mode"], len(s["hunks"]))
                for s in patch.read(NEW + GONE + MOVED + COPIED + MODE)]
        self.assertEqual(said, [("new", "docs/n.md", "docs/n.md", None, "100644", None, 1),
                                ("deleted", "tests/t.py", "tests/t.py", "100644", None, None, 1),
                                ("rename", "docs/a.md", "docs/b.md", None, None, "100644", 1),
                                ("copy", "docs/a.md", "docs/c.md", None, None, None, 0),
                                ("change", "docs/a.md", "docs/a.md", "100644", "100755", None, 0)])
        # Each hunk of a section is read, with each side's own place and count.
        two = patch.read(section("docs/a.md", b"@@ -2,2 +2,3 @@\n b\n+C\n d\n@@ -9,3 +10,2 @@\n x\n-y\n z\n"))[0]["hunks"]
        self.assertEqual([(h["old_start"], h["old_count"], h["new_start"], h["new_count"], len(h["lines"])) for h in two],
                         [(2, 2, 2, 3, 3), (9, 3, 10, 2, 3)])
        self.assertEqual(patch.read(section("docs/a.md", b"@@ -999999999 +999999999 @@\n-a\n+A\n"))[0]["hunks"][0]["old_start"],
                         999999999)
        # A count a header leaves out is one line; git's marker says the line before it has no newline at its end,
        # in a hunk or after its last line.
        marker = b"\\ No newline at end of file\n"
        for lines, bare in ((b"-a\n" + marker + b"+A\n", [True, False]), (b"-a\n+A\n" + marker, [False, True]),
                            (b"-a\n" + marker + b"+A\n" + marker, [True, True])):
            hunk = patch.read(section("docs/a.md", b"@@ -1 +1 @@\n" + lines))[0]["hunks"][0]
            self.assertEqual((hunk["old_count"], hunk["new_count"], [said["bare"] for said in hunk["lines"]]), (1, 1, bare))
        ends = patch.read(section("docs/a.md", b"@@ -1,2 +1,2 @@\n-a\n+A\n b\n" + marker))[0]["hunks"][0]
        self.assertEqual([said["bare"] for said in ends["lines"]], [False, False, True])

    def test_sources_names_each_file_a_patch_reads_once_and_no_new_file(self):
        self.assertEqual(patch.sources(CHANGE), ["docs/a.md"])
        self.assertEqual(patch.sources(NEW), [])
        self.assertEqual(patch.sources(MOVED), ["docs/a.md"])
        # A file read with no hunk is read all the same: a copy, a rename and a change of mode, each alone.
        whole = b"diff --git a/run.sh b/bin/run.sh\nsimilarity index 100%\nrename from run.sh\nrename to bin/run.sh\n"
        self.assertEqual([patch.sources(data) for data in (COPIED, whole, MODE)], [["docs/a.md"], ["run.sh"], ["docs/a.md"]])
        self.assertEqual(patch.sources(CHANGE + COPIED + GONE), ["docs/a.md", "tests/t.py"])

    def test_a_patch_lands_the_bytes_it_says_and_no_others(self):
        changes, why = landed(CHANGE)
        self.assertEqual((changes, why), ({"written": {"docs/a.md": (FILE, b"a\nb\nC\nd\ne\nf\ng\nh\n")}, "removed": [],
                                           "read": []}, None))
        self.assertEqual(patch.sources(CHANGE), ["docs/a.md"])
        # Two hunks of one file, each where its header says; a line added at the top, one taken from the end.
        two = section("docs/a.md", b"@@ -1,2 +1,3 @@\n+z\n a\n b\n@@ -7,2 +8 @@\n g\n-h\n")
        self.assertEqual(landed(two)[0]["written"]["docs/a.md"][1], b"z\na\nb\nc\nd\ne\nf\ng\n")
        # A hunk of no context: lines put in after line 3, and lines taken out with nothing put back.
        self.assertEqual(landed(section("docs/a.md", b"@@ -3,0 +4,2 @@\n+x\n+y\n"))[0]["written"]["docs/a.md"][1],
                         b"a\nb\nc\nx\ny\nd\ne\nf\ng\nh\n")
        self.assertEqual(landed(section("docs/a.md", b"@@ -2,2 +1,0 @@\n-b\n-c\n"))[0]["written"]["docs/a.md"][1],
                         b"a\nd\ne\nf\ng\nh\n")
        # A carriage return is a byte of its line, and stays one.
        crlf = landed(section("docs/a.md", b"@@ -1,2 +1,2 @@\n-a\r\n+A\r\n b\r\n"), held={"docs/a.md": b"a\r\nb\r\n"})
        self.assertEqual(crlf[0]["written"]["docs/a.md"][1], b"A\r\nb\r\n")

    def test_a_hunk_stands_where_its_header_says_and_nowhere_else(self):
        # Nothing is searched for: lines that are the file's two lines further down are not this hunk's.
        twice = b"a\nb\nc\nd\nb\nc\nd\n"
        good = section("docs/a.md", b"@@ -5,2 +5,2 @@\n b\n-c\n+C\n")
        self.assertEqual(landed(good, held={"docs/a.md": twice})[0]["written"]["docs/a.md"][1], b"a\nb\nc\nd\nb\nC\nd\n")
        for wrong in (b"@@ -3,2 +3,2 @@\n b\n-c\n+C\n",          # the lines of line 2, said to stand at line 3
                      b"@@ -5,2 +5,2 @@\n b\n-x\n+C\n",          # a line the file does not hold there
                      b"@@ -5,2 +5,2 @@\n b \n-c\n+C\n",         # a line with a space more
                      b"@@ -5,2 +4,2 @@\n b\n-c\n+C\n",          # the new side said to begin a line early
                      b"@@ -7,2 +7,2 @@\n d\n-e\n+E\n",          # a hunk past the file's end
                      b"@@ -5,2 +5,2 @@\n b\n-c\n+C\n@@ -2,1 +2,1 @@\n-b\n+B\n",     # a hunk before the one before it
                      b"@@ -5,2 +5,2 @@\n b\n-c\n+C\n@@ -6,1 +6,1 @@\n-c\n+X\n",     # a hunk over the one before it
                      b"@@ -0,2 +1,2 @@\n a\n-b\n+B\n",          # a hunk of two lines said to stand before the first
                      # a hunk that takes a line the hunk before it took, its new side where that leaves it
                      b"@@ -5,2 +5 @@\n-b\n-c\n+B\n@@ -6 +6 @@\n-c\n+X\n",
                      # two hunks with no line between them, which git writes as one and reads in another order
                      b"@@ -5 +5 @@\n-b\n+B\n@@ -6 +6 @@\n-c\n+C\n", b"@@ -0,0 +1 @@\n+x\n@@ -0,0 +2 @@\n+z\n",
                      b"@@ -5 +5 @@\n-b\n+B\n@@ -5,0 +6 @@\n+x\n"):
            with self.subTest(wrong=wrong):
                self.assertEqual(landed(section("docs/a.md", wrong), held={"docs/a.md": twice}),
                                 (None, patch.NOT_APPLIED))

        # Two hunks with a line between them each stand; the first hunk may stand at the file's first line.
        apart = section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\n@@ -3 +3 @@\n-c\n+C\n@@ -5 +5 @@\n-b\n+B\n")
        self.assertEqual(landed(apart, held={"docs/a.md": twice})[0]["written"]["docs/a.md"][1], b"A\nb\nC\nd\nB\nc\nd\n")

    def test_the_newline_at_a_files_end_is_as_the_patch_says(self):
        marker = b"\\ No newline at end of file\n"
        bare = {"docs/a.md": b"a\nb"}
        cases = (
            # the last line gains its newline; loses it; is changed and keeps none; a line is added after a bare one
            (bare, b"@@ -1,2 +1,2 @@\n a\n-b\n" + marker + b"+b\n", b"a\nb\n"),
            ({"docs/a.md": b"a\nb\n"}, b"@@ -1,2 +1,2 @@\n a\n-b\n+b\n" + marker, b"a\nb"),
            (bare, b"@@ -1,2 +1,2 @@\n a\n-b\n" + marker + b"+B\n" + marker, b"a\nB"),
            (bare, b"@@ -1,2 +1,3 @@\n a\n-b\n" + marker + b"+b\n+c\n", b"a\nb\nc\n"),
            # a bare last line left as context; a bare last line removed, so the line before it ends the file
            (bare, b"@@ -1,2 +1,2 @@\n-a\n+A\n b\n" + marker, b"A\nb"),
            (bare, b"@@ -1,2 +1 @@\n a\n-b\n" + marker, b"a\n"),
            # a hunk that stops short of a bare last line leaves it bare
            ({"docs/a.md": b"a\nb\nc"}, b"@@ -1 +1 @@\n-a\n+A\n", b"A\nb\nc"),
            # an empty file gains lines; a file loses every line and stays
            ({"docs/a.md": b""}, b"@@ -0,0 +1,2 @@\n+a\n+b\n", b"a\nb\n"),
            ({"docs/a.md": b"a\n"}, b"@@ -1 +0,0 @@\n-a\n", b""),
        )
        for held, hunks, after in cases:
            with self.subTest(hunks=hunks):
                self.assertEqual(landed(section("docs/a.md", hunks), held=held)[0]["written"]["docs/a.md"][1], after)
        wrong = (
            (bare, b"@@ -1,2 +1,2 @@\n a\n-b\n+B\n"),                               # the bare line read as whole
            ({"docs/a.md": b"a\nb\n"}, b"@@ -1,2 +1,2 @@\n a\n-b\n" + marker + b"+B\n"),    # a whole line read as bare
            ({"docs/a.md": b"a\nb\n"}, b"@@ -1 +1 @@\n-a\n" + marker + b"+A\n"),        # a line not the last read bare
            (bare, b"@@ -2,0 +3 @@\n+c\n"),                                          # a line added after a bare one
            # A new line with no newline at its end is the file's last: no line of the file follows its hunk, where
            # git would join the two lines into one. (A marker in a hunk that is not the last is no patch at all.)
            ({"docs/a.md": b"a\nb\n"}, b"@@ -1 +1 @@\n-a\n+A\n" + marker),
            ({"docs/a.md": b"a\nb\nc\n"}, b"@@ -1,2 +1,2 @@\n-a\n+A\n b\n" + marker),
        )
        for held, hunks in wrong:
            with self.subTest(hunks=hunks):
                self.assertEqual(landed(section("docs/a.md", hunks), held=held), (None, patch.NOT_APPLIED))

    def test_a_new_a_removed_a_renamed_and_a_copied_file_are_each_what_the_patch_says(self):
        new = (b"diff --git a/docs/n.md b/docs/n.md\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n"
               b"+++ b/docs/n.md\n@@ -0,0 +1,2 @@\n+x\n+y\n")
        self.assertEqual(landed(new)[0], {"written": {"docs/n.md": (FILE, b"x\ny\n")}, "removed": [], "read": []})
        self.assertEqual(patch.sources(new), [])
        empty = b"diff --git a/docs/e b/docs/e\nnew file mode 100755\nindex 0000000..e69de29\n"
        self.assertEqual(landed(empty)[0]["written"], {"docs/e": ("100755", b"")})
        gone = (b"diff --git a/tests/t.py b/tests/t.py\ndeleted file mode 100644\nindex 1111111..0000000\n"
                b"--- a/tests/t.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
        self.assertEqual(landed(gone)[0], {"written": {}, "removed": ["tests/t.py"], "read": []})
        moved = (b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 87%\nrename from docs/a.md\nrename to docs/b.md\n"
                 b"index 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/b.md\n@@ -1,2 +1,2 @@\n-a\n+A\n b\n")
        self.assertEqual(landed(moved)[0], {"written": {"docs/b.md": (FILE, b"A" + OLD[1:])}, "removed": ["docs/a.md"],
                                            "read": ["docs/a.md"]})
        whole = b"diff --git a/run.sh b/bin/run.sh\nsimilarity index 100%\nrename from run.sh\nrename to bin/run.sh\n"
        self.assertEqual(landed(whole)[0], {"written": {"bin/run.sh": ("100755", b"#!/bin/sh\n")}, "removed": ["run.sh"],
                                            "read": ["run.sh"]})
        copied = b"diff --git a/docs/a.md b/docs/c.md\nsimilarity index 100%\ncopy from docs/a.md\ncopy to docs/c.md\n"
        self.assertEqual(landed(copied)[0], {"written": {"docs/c.md": (FILE, OLD)}, "removed": [], "read": ["docs/a.md"]})
        # A copy reads the file as the admitted commit holds it, whatever another section makes of it.
        both = landed(CHANGE + copied)[0]["written"]
        self.assertEqual(patch.sources(CHANGE + copied), ["docs/a.md"])
        self.assertEqual((both["docs/a.md"][1], both["docs/c.md"][1]), (b"a\nb\nC\nd\ne\nf\ng\nh\n", OLD))
        mode = b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 100755\n"
        self.assertEqual(landed(mode)[0]["written"], {"docs/a.md": ("100755", OLD)})

    def test_a_file_is_written_once_and_only_where_the_patch_says_it_stands(self):
        new = (b"diff --git a/%s b/%s\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n+++ b/%s\n"
               b"@@ -0,0 +1 @@\n+x\n")
        gone = (b"diff --git a/tests/t.py b/tests/t.py\ndeleted file mode 100644\nindex 1111111..0000000\n"
                b"--- a/tests/t.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
        moved = b"diff --git a/docs/a.md b/%s\nsimilarity index 100%%\nrename from docs/a.md\nrename to %s\n"
        copied = b"diff --git a/docs/a.md b/%s\nsimilarity index 100%%\ncopy from docs/a.md\ncopy to %s\n"
        mode = b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 100755\n"
        not_applied = (
            new % ((b"docs/a.md",) * 3),                                       # a new file where the tree holds one
            section("docs/none.md", b"@@ -1 +1 @@\n-a\n+b\n"),                 # a change to a file the tree has not
            moved % ((b"run.sh",) * 2),                                        # a rename onto a file
            copied % ((b"run.sh",) * 2),                                       # a copy onto a file
            gone[:gone.index(b"--- ")],                                        # a removal, of no hunk, of a file that holds bytes
            gone.replace(b"deleted file mode 100644", b"deleted file mode 100755"),      # another mode than the tree's
            CHANGE.replace(b"2222222 100644", b"2222222 100755"),
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100755\nnew mode 100644\n",
        )
        for data in not_applied:
            with self.subTest(data=data):
                self.assertEqual(landed(data), (None, patch.NOT_APPLIED))
        # A removal that leaves bytes is no removal: the tree holds more than the patch takes.
        self.assertEqual(landed(gone, held=dict(HELD, **{"tests/t.py": b"x\ny\n"})), (None, patch.NOT_APPLIED))
        # An empty file is removed with no hunk, as git writes it.
        self.assertEqual(landed(gone[:gone.index(b"--- ")], held=dict(HELD, **{"tests/t.py": b""}))[0]["removed"], ["tests/t.py"])
        # A file whose bytes were not read is not guessed at, with hunks or with none, nor read from what is no bytes;
        # and nor is one the tree does not hold, whatever was read.
        self.assertEqual(landed(CHANGE, held={}), (None, patch.NOT_APPLIED))
        for data in (moved % ((b"docs/b.md",) * 2), copied % ((b"docs/c.md",) * 2), mode):
            for held in ({}, {"docs/a.md": OLD.decode()}, {"docs/a.md": None}):
                self.assertEqual(landed(data, held=held), (None, patch.NOT_APPLIED), (data, held))
        self.assertEqual(landed(section("docs/none.md", b"@@ -1 +1 @@\n-a\n+b\n"), held={"docs/none.md": b"a\n"}),
                         (None, patch.NOT_APPLIED))
        away = b"diff --git a/tests/t.py b/x\nsimilarity index 100%\nrename from tests/t.py\nrename to x\n"
        twice = (CHANGE + CHANGE, CHANGE + moved % ((b"docs/b.md",) * 2), moved % ((b"docs/b.md",) * 2) + CHANGE,
                 gone + new % ((b"tests/t.py",) * 3), new % ((b"n",) * 3) + new % ((b"n",) * 3),
                 gone + away, moved % ((b"docs/b.md",) * 2) + moved % ((b"docs/c.md",) * 2),      # a file moved once it is gone
                 copied % ((b"docs/c.md",) * 2) + copied % ((b"docs/c.md",) * 2))
        for data in twice:
            with self.subTest(data=data):
                self.assertEqual(landed(data), (None, patch.UNREADABLE))

    def test_what_is_no_file_is_never_written(self):
        new = (b"diff --git a/%s b/%s\nnew file mode %s\nindex 0000000..2222222\n--- /dev/null\n+++ b/%s\n"
               b"@@ -0,0 +1 @@\n+docs/a.md\n")
        cases = (
            new % (b"l", b"l", b"120000", b"l"),                               # a link
            new % (b"m", b"m", b"160000", b"m"),                               # a submodule
            section("link", b"@@ -1 +1 @@\n-docs/a.md\n\\ No newline at end of file\n+run.sh\n\\ No newline at end of file\n",
                    extended=b"index 1111111..2222222 120000\n"),              # a link pointed elsewhere
            b"diff --git a/link b/link\ndeleted file mode 120000\nindex 1111111..0000000\n--- a/link\n+++ /dev/null\n"
            b"@@ -1 +0,0 @@\n-docs/a.md\n\\ No newline at end of file\n",       # a link removed
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 120000\n",    # a file turned into a link
            b"diff --git a/link b/link\nold mode 120000\nnew mode 100644\n",              # a link turned into a file
            new % (b"link/x", b"link/x", b"100644", b"link/x"),                # a file under a link
            new % (b"run.sh/x", b"run.sh/x", b"100644", b"run.sh/x"),          # a file under a file
            new % (b"docs", b"docs", b"100644", b"docs"),                      # a file where a directory stands
            new % (b"n", b"n", b"100644", b"n") + new % (b"n/x", b"n/x", b"100644", b"n/x"),    # one of its own under another
            b"diff --git a/link b/l2\nsimilarity index 100%\nrename from link\nrename to l2\n",    # a link moved
            # A submodule changed, removed, moved, and written under: no bytes of one are read, and none are needed.
            section("vendored", b"@@ -1 +1 @@\n-a\n+b\n", extended=b"index 1111111..2222222 160000\n"),
            b"diff --git a/vendored b/vendored\ndeleted file mode 160000\nindex 1111111..0000000\n",
            b"diff --git a/vendored b/v2\nsimilarity index 100%\nrename from vendored\nrename to v2\n",
            new % (b"vendored/x", b"vendored/x", b"100644", b"vendored/x"),
            # A rename and a copy are held as a new file is: none lands under a file, or where a directory stands.
            b"diff --git a/docs/a.md b/run.sh/x\nsimilarity index 100%\nrename from docs/a.md\nrename to run.sh/x\n",
            b"diff --git a/docs/a.md b/docs\nsimilarity index 100%\ncopy from docs/a.md\ncopy to docs\n",
            b"diff --git a/run.sh b/tests\nsimilarity index 100%\nrename from run.sh\nrename to tests\n",
            new % (b"n/x", b"n/x", b"100644", b"n/x") + new % (b"n", b"n", b"100644", b"n"),    # the same, the other way about
            # Nor under a file that stands further up than its own directory, in the tree or in the patch.
            new % (b"run.sh/sub/x", b"run.sh/sub/x", b"100644", b"run.sh/sub/x"),
            new % (b"n", b"n", b"100644", b"n") + new % (b"n/sub/x", b"n/sub/x", b"100644", b"n/sub/x"),
            b"diff --git a/docs/a.md b/link/sub/x\nsimilarity index 100%\ncopy from docs/a.md\ncopy to link/sub/x\n",
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(landed(data), (None, patch.NOT_A_FILE))

    def test_a_name_is_read_one_way_or_not_at_all(self):
        good = section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\n")
        self.assertEqual(len(patch.read(good)), 1)
        self.assertEqual(landed(good, held={"docs/a.md": b"a\n"})[1], None)
        names = (b'"docs/a\\303\\251.md"', b"docs/a b.md", b"docs/caf\xc3\xa9.md", b"docs/a\\b.md", b'docs/a"b.md',
                 b"docs/../x", b"./x", b"docs//x", b"/x", b"x/", b".git/config", b"docs/.GIT/x", b"docs/a\tb", b"")
        for name in names:
            with self.subTest(name=name):
                data = good.replace(b"docs/a.md", name)
                self.assertIsNone(patch.read(data))
                self.assertEqual(landed(data), (None, patch.UNREADABLE))
        # git's own directory in each form git knows it by on some file system, at any depth; and names that only
        # look like it, which are read.
        for name in (b"git~1/config", b"GIT~1/config", b"docs/git~2/x", b".git./config", b".GIT.../hooks/x", b".git:x",
                     b".git::$INDEX_ALLOCATION/config", b"docs/.git:x/y", b"docs/.Git..:x", b"git~"):
            with self.subTest(name=name):
                self.assertIsNone(patch.read(good.replace(b"docs/a.md", name)))
        for name in (b".gitignore", b"docs/.gitkeep", b".github/x", b"x.git/y", b"legit~1", b"docs/.git-x", b"git/x"):
            with self.subTest(name=name):
                self.assertEqual(patch.read(good.replace(b"docs/a.md", name))[0]["new"], name.decode())
        # Every line that names a file names what the header names: a side, a rename's line, a copy's.
        moved = b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 100%\nrename from docs/a.md\nrename to docs/b.md\n"
        for data in (good.replace(b"--- a/docs/a.md", b"--- a/run.sh"), good.replace(b"+++ b/docs/a.md", b"+++ b/run.sh"),
                     good.replace(b"+++ b/docs/a.md", b"+++ /dev/null"), good.replace(b"--- a/docs/a.md", b"--- /dev/null"),
                     good.replace(b"+++ b/docs/a.md", b"+++ b/docs/a.md\t"), good.replace(b"b/docs/a.md\n", b"b/run.sh\n", 1),
                     moved.replace(b"rename from docs/a.md", b"rename from run.sh"),
                     moved.replace(b"rename to docs/b.md", b"rename to run.sh"),
                     moved.replace(b"rename to docs/b.md\n", b""), moved.replace(b"similarity index 100%\n", b""),
                     moved.replace(b"rename", b"copy", 1), moved.replace(b"b/docs/b.md", b"b/docs/a.md"),
                     moved.replace(b"docs/b.md", b"docs/a.md"),      # a file renamed to itself
                     # one line of a rename or a copy, on a section that is otherwise a change of mode
                     b"diff --git a/docs/a.md b/docs/a.md\nrename from run.sh\nold mode 100644\nnew mode 100755\n",
                     b"diff --git a/docs/a.md b/docs/a.md\ncopy to run.sh\nold mode 100644\nnew mode 100755\n",
                     moved.replace(b"similarity index 100%", b"similarity index x%"),
                     b"diff --git a/docs/a.md b/run.sh\nold mode 100644\nnew mode 100755\n",     # two names and no rename
                     moved.replace(b"rename from docs/a.md\n", b"rename from docs/a.md\ncopy from docs/a.md\ncopy to docs/b.md\n")):
            with self.subTest(data=data):
                self.assertIsNone(patch.read(data))
                self.assertEqual(landed(data), (None, patch.UNREADABLE))

    def test_what_is_not_a_patch_as_git_writes_it_is_unreadable(self):
        marker = b"\\ No newline at end of file\n"
        cases = (
            b"", "", None, CHANGE.decode(), CHANGE[:-1], b"\n", b"From x\n" + CHANGE, CHANGE + b"\n", CHANGE + b"trailer\n", CHANGE + b" ",
            CHANGE.replace(b"diff --git a/docs/a.md b/docs/a.md\n", b""),
            CHANGE.replace(b"diff --git a/", b"diff --git "), CHANGE.replace(b" b/docs/a.md\nindex", b" docs/a.md\nindex"),
            CHANGE.replace(b"index 1111111..2222222 100644\n", b"something else\n"),
            CHANGE.replace(b"index 1111111..2222222 100644\n", b"index 1111111..2222222 100644\nindex 1111111..2222222 100644\n"),
            CHANGE.replace(b"1111111..2222222", b"1111111.2222222"), CHANGE.replace(b"1111111..2222222", b"111111g..2222222"),
            CHANGE.replace(b"2222222 100644", b"2222222 file"),
            CHANGE.replace(b"+++ b/docs/a.md\n", b""), CHANGE.replace(b"@@ -2,3 +2,3 @@\n b\n-c\n+C\n d\n", b""),
            CHANGE.replace(b" d\n", b""), CHANGE.replace(b" d\n", b" d\n e\n"), CHANGE.replace(b" b\n", b"b\n"),
            CHANGE.replace(b" b\n", b"\n"), CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 @@"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,3"), CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,03 +2,3 @@"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,x @@"), CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,3,1 @@"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,-3 @@"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -1000000000,3 +2,3 @@"),
            section("docs/a.md", b"@@ -1,0 +1,0 @@\n"), section("docs/a.md", b"@@ -1 +1 @@\n" + marker + b"-a\n+A\n"),
            section("docs/a.md", b"@@ -1 +1 @@\n-a\n" + marker + marker + b"+A\n"),
            section("docs/a.md", b"@@ -1 +1 @@\n-a\n\\ No newline\n+A\n"),
            b"diff --git a/x.bin b/x.bin\nindex 1111111..2222222 100644\nGIT binary patch\nliteral 2\nJcmZQ%0000\n\n",
            b"diff --git a/x.bin b/x.bin\nindex 1111111..2222222 100644\nBinary files a/x.bin and b/x.bin differ\n",
            b"diff --git a/docs/a.md b/docs/a.md\nindex 1111111..2222222 100644\n",           # a section that changes nothing
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\n",
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode rwx\n",
            b"diff --git a/n b/n\nnew file mode 100644\ndeleted file mode 100644\n",
            b"diff --git a/n b/n\nnew file mode 100644\nold mode 100644\nnew mode 100755\n",
            b"diff --git a/n b/n\nnew file mode 100644\nindex 0000000..2222222\n--- a/n\n+++ b/n\n@@ -0,0 +1 @@\n+x\n",
            # A hunk that changes nothing; a new file with an old line or two hunks; a removed one with a new line.
            section("docs/a.md", b"@@ -1,2 +1,2 @@\n a\n b\n"),
            new_file(b"@@ -1 +1,2 @@\n a\n+b\n"), new_file(b"@@ -0,0 +1 @@\n+x\n@@ -0,0 +2 @@\n+y\n"),
            gone_file(b"@@ -1,2 +1 @@\n a\n-b\n"), gone_file(b"@@ -1 +0,0 @@\n-a\n@@ -2 +0,0 @@\n-b\n"),
            new_file(b"@@ -0,0 +1 @@\n+x\n@@ -0,0 +1 @@\n+y\n"), gone_file(b"@@ -1 +0,0 @@\n-a\n@@ -1 +0,0 @@\n-b\n"),
            # The one hunk of either stands at line 1 of the side that has lines, and at line 0 of the other.
            new_file(b"@@ -7,0 +1 @@\n+x\n"), new_file(b"@@ -0,0 +2 @@\n+x\n"), new_file(b"@@ -0,1 +1,2 @@\n a\n+b\n"),
            gone_file(b"@@ -1 +7,0 @@\n-a\n"), gone_file(b"@@ -2 +0,0 @@\n-a\n"), gone_file(b"@@ -1,2 +0,1 @@\n-a\n b\n"),
            # A hunk after one that holds git's marker: the file ended there, on one side or on both.
            section("f", b"@@ -1 +1 @@\n-a\n" + marker + b"+A\n" + marker + b"@@ -3 +3 @@\n-b\n+B\n"),
            section("f", b"@@ -1 +1 @@\n-a\n+A\n" + marker + b"@@ -3 +3 @@\n-c\n+C\n"),
            section("f", b"@@ -1 +1 @@\n-a\n" + marker + b"+A\n@@ -3,0 +4 @@\n+c\n"),
            # The sides with no hunk under them; a side as a patch's last line.
            new_file(b""), b"diff --git a/f b/f\nold mode 100644\nnew mode 100755\n--- a/f\n+++ b/f\n",
            b"diff --git a/f b/f\nindex 1111111..2222222 100644\n--- a/f\n",
            # A mode git does not write; a change of mode to the same mode; a second mode on the index line.
            b"diff --git a/f b/f\nold mode 100644\nnew mode 999\n", b"diff --git a/f b/f\nold mode 1\nnew mode 100644\n",
            b"diff --git a/n b/n\nnew file mode 7\n", b"diff --git a/f b/f\ndeleted file mode 0100644\n",
            b"diff --git a/f b/f\nold mode 100644\nnew mode 100644\n",
            b"diff --git a/n b/n\nnew file mode 100644\nindex 0000000..2222222 100755\n",
            b"diff --git a/f b/f\ndeleted file mode 100644\nindex 1111111..0000000 100644\n",
            b"diff --git a/f b/f\nindex 1111111..2222222 120000\nold mode 100644\nnew mode 100755\n",
            # What only a rename or a copy has, on a section that is neither.
            b"diff --git a/a b/b\nnew file mode 100644\nsimilarity index 100%\nrename from a\nrename to b\n",
            b"diff --git a/f b/f\nsimilarity index 100%\nold mode 100644\nnew mode 100755\n",
            # git's marker on a line that is not the last of its side, which git would join to the next.
            section("f", b"@@ -1 +1,2 @@\n-a\n+A\n" + marker + b"+B\n"), section("f", b"@@ -1,2 +1 @@\n-a\n" + marker + b"-b\n+A\n"),
            section("f", b"@@ -1,2 +1,2 @@\n a\n" + marker + b"-b\n+B\n"), section("f", b"@@ -1,2 +1,2 @@\n-a\n+A\n" + marker + b" b\n"),
            section("f", b"@@ -1 +1 @@\n-a\n+A\n" + marker + marker),
            # A NUL in a line is a binary change written as text.
            section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\x00\n"), section("docs/a.md", b"@@ -1 +1 @@\n-a\x00\n+A\n"),
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertIsNone(patch.read(data))
                self.assertIsNone(patch.sources(data))
                self.assertEqual(landed(data), (None, patch.UNREADABLE))
        # A tree or contents in no shape a port gives is the Factory's, under its own code, whatever the patch is: a
        # path is text.
        for tree, held in ((None, HELD), (TREE, None), ([], HELD), (TREE, []), ({**TREE, b"f": FILE}, HELD),
                           ({**TREE, None: FILE}, HELD), ({1: FILE}, HELD), ({**TREE, "unread": None}, HELD),
                           ({**TREE, "docs": "040000"}, HELD), ({**TREE, "n": 100644}, HELD), ({**TREE, "n": b"100644"}, HELD)):
            self.assertEqual(patch.applied(CHANGE, tree, held), (None, patch.TREE_UNREAD))
            self.assertEqual(patch.applied(b"no patch\n", tree, held), (None, patch.TREE_UNREAD))

    def test_a_patch_as_git_writes_it_lands_what_git_would(self):
        # Against git itself, on fixed seeds, under no configuration, attributes or ignore rules but git's own. Files changed, removed, moved, copied,
        # made runnable or plain, and added; lines that are empty, end in a carriage return or begin as a patch's own
        # lines do; last lines with and without a newline; read by `git diff` with and without renames, copies and
        # context. Then each patch is broken at random, and what `applied` still lands of it is what git lands too.
        quiet = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
        quiet.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1")
        alone = ("git", "-c", "core.attributesFile=" + os.devnull, "-c", "core.excludesFile=" + os.devnull)
        marker = b"\\ No newline at end of file"

        def run(tree, *args, data=None, check=True):
            return subprocess.run(alone + args, cwd=tree, check=check, capture_output=True, input=data, env=quiet)

        def below(rng, most):
            return int(rng.random() * most)     # only random() draws alike on every Python

        def lines(rng, count):
            heads = (b"line ", b"line ", b"line ", b"", b"-", b"+", b"\\ ", b"@@ -1 +1 @@ ", b" ", b"diff --git a/x b/x ")
            return [heads[below(rng, len(heads))] + b"%d %s" % (below(rng, 40), b"x" * below(rng, 4))
                    + (b"\r" if rng.random() < 0.1 else b"") if rng.random() < 0.9 else b"" for _ in range(count)]

        def body(rng):
            said = lines(rng, below(rng, 30))
            return b"\n".join(said) + (b"" if said[-1] and rng.random() < 0.25 else b"\n") if said else b""

        def edit(rng, data):
            said = data.split(b"\n")[:-1] if data.endswith(b"\n") else data.split(b"\n") if data else []
            for _ in range(1 + below(rng, 4)):
                kind = below(rng, 3)
                if kind == 0 or not said:
                    said.insert(below(rng, len(said) + 1), lines(rng, 1)[0])
                elif kind == 1:
                    del said[below(rng, len(said))]
                else:
                    said[below(rng, len(said))] = lines(rng, 1)[0]
            return b"\n".join(said) + (b"" if said[-1] and rng.random() < 0.3 else b"\n") if said else b""

        def snapshot(tree, out="."):
            listed = [entry.split(b"\t") for entry in run(tree, "ls-files", "-s", "-z").stdout.split(b"\0") if entry]
            return {name.decode(): (meta.split()[0].decode(), (tree / out / name.decode()).read_bytes()) for meta, name in listed}

        def broken(rng, data):
            said = data.split(b"\n")[:-1]
            for _ in range(1 + below(rng, 2)):
                at, kind = below(rng, len(said)), below(rng, 7)
                if kind == 0:
                    said.insert(at + 1, marker)
                elif kind == 1:
                    said.insert(at, said[at])
                elif kind == 2:
                    del said[at]
                elif kind == 3 and at:
                    said[at - 1], said[at] = said[at], said[at - 1]
                elif kind == 4:
                    said[at] = (b" " if said[at][:1] in (b"-", b"+") else b"+") + said[at][1:]
                else:
                    headers = [i for i, line in enumerate(said) if line.startswith(b"@@ -")]
                    if headers:
                        i = headers[below(rng, len(headers))]
                        if kind == 5:       # the hunk again, where it stands
                            j = min([k for k in headers + [len(said)] if k > i] + [k for k, line in enumerate(said)
                                                                                    if k > i and line.startswith(b"diff ")])
                            said[j:j] = said[i:j]
                        else:               # a number of its header, one more or one fewer
                            digits = [k for k, c in enumerate(said[i]) if c in b"0123456789"]
                            k = digits[below(rng, len(digits))]
                            said[i] = said[i][:k] + b"%d" % ((said[i][k] - 48 + (1 if rng.random() < 0.5 else 9)) % 10) + said[i][k + 1:]
            return b"\n".join(said) + b"\n"

        kinds, copied_with_hunks, lands = set(), 0, 0
        for seed in range(24):
            rng = random.Random(seed)
            with tempfile.TemporaryDirectory() as where:
                tree = pathlib.Path(where) / "tree"
                tree.mkdir()
                run(tree, "init", "-q")
                names = ["a.py", "docs/b.md", "docs/deep/c.txt", "tests/d.py", "e", "run.sh", "one"]
                for name in names:
                    (tree / name).parent.mkdir(parents=True, exist_ok=True)
                    (tree / name).write_bytes(b"\n" if name == "one" else body(rng))
                (tree / "docs" / "long.md").write_bytes(b"".join(b"a long line, number %d\n" % n for n in range(30)))
                os.chmod(tree / "run.sh", 0o755)
                run(tree, "add", "-A")
                first, before = run(tree, "write-tree").stdout.decode().strip(), snapshot(tree)
                for name in names:
                    draw = rng.random()
                    if draw < 0.5:
                        (tree / name).write_bytes(edit(rng, (tree / name).read_bytes()))
                    elif draw < 0.6:
                        (tree / name).unlink()
                    elif draw < 0.7:
                        run(tree, "mv", name, name + ".moved")
                        if rng.random() < 0.5:
                            (tree / (name + ".moved")).write_bytes(edit(rng, (tree / (name + ".moved")).read_bytes()))
                    if 0.4 < draw < 0.5 or 0.65 < draw < 0.75:
                        os.chmod(tree / (name + ".moved" if 0.6 < draw < 0.7 else name), 0o644 if name == "run.sh" else 0o755)
                if rng.random() < 0.6:
                    (tree / "new").mkdir()
                    (tree / "new" / "f.py").write_bytes(body(rng))
                    if rng.random() < 0.5:
                        os.chmod(tree / "new" / "f.py", 0o755)
                if rng.random() < 0.6:
                    (tree / "twin.md").write_bytes(before["docs/long.md"][1] + b"one line more\n")
                run(tree, "add", "-A")
                flags = (("--no-renames",), ("-M",), ("-M", "-C", "--find-copies-harder"), ("-U0", "--no-renames"),
                         ("-U1", "-M"), ("-U0", "-M", "-C", "--find-copies-harder"))[below(rng, 6)]
                data, after = run(tree, "diff", "--cached", *flags, first).stdout, snapshot(tree)
                mode_of = {name: mode for name, (mode, _) in before.items()}
                with self.subTest(seed=seed):
                    sections = patch.read(data)
                    kinds |= {section["kind"] for section in sections}
                    copied_with_hunks += len([s for s in sections if s["kind"] == "copy" and s["hunks"]])
                    need = patch.sources(data)
                    changes, why = patch.applied(data, mode_of, {name: before[name][1] for name in need})
                    self.assertIsNone(why)
                    got = {name: held for name, held in before.items() if name not in changes["removed"]}
                    got.update(changes["written"])
                    self.assertEqual(got, after)
                    self.assertEqual(changes["read"], [s["old"] for s in sections if s["kind"] in ("rename", "copy")])
                # The same patch, broken: most of it is then no patch of this tree. What still lands, git lands alike.
                for turn in range(40):
                    wrong = broken(rng, data)
                    need = patch.sources(wrong)
                    changes, why = patch.applied(wrong, mode_of, {name: before[name][1] for name in need or () if name in before})
                    if why is not None or wrong == data:
                        continue
                    with self.subTest(seed=seed, turn=turn, wrong=wrong):
                        lands += 1
                        run(tree, "read-tree", first)
                        applied = run(tree, "apply", "--cached", "--unidiff-zero", "-", data=wrong, check=False)
                        self.assertEqual(applied.returncode, 0, applied.stderr)
                        run(tree, "checkout-index", "-a", "-f", "--prefix=../out%d/" % turn)
                        got = {name: held for name, held in before.items() if name not in changes["removed"]}
                        got.update(changes["written"])
                        self.assertEqual(got, snapshot(tree, "../out%d" % turn))
        self.assertEqual(kinds, {"change", "new", "deleted", "rename", "copy"})
        self.assertTrue(copied_with_hunks and lands, (copied_with_hunks, lands))


REPO = "combsmith/software-factory"
BRANCH = "factory-work/issue-838-1"
PARENT, ROOT_TREE, MADE, BLOB_A, BLOB_N = "a" * 40, "b" * 40, "c" * 40, "d" * 40, "e" * 40
GIT = "/repos/%s/git/" % REPO
CHANGES = {"written": {"docs/a.md": (FILE, b"A\n"), "run/n.sh": ("100755", b"x\n")}, "removed": ["tests/t.py"],
           "read": ["docs/old.md"]}
PUSH = {"repo": REPO, "branch": BRANCH, "parent": PARENT, "tree": ROOT_TREE, "head": None,
        "message": "The opening Run's commit for issue 838", "changes": CHANGES}
ENTRIES = [{"path": "docs/a.md", "mode": FILE, "type": "blob", "sha": BLOB_A},
           {"path": "run/n.sh", "mode": "100755", "type": "blob", "sha": BLOB_N},
           {"path": "tests/t.py", "mode": FILE, "type": "blob", "sha": None}]
NEW_TREE = {"base_tree": ROOT_TREE, "tree": ENTRIES}
COMMIT = {"message": PUSH["message"], "tree": MADE, "parents": [PARENT]}


def told(**changed) -> dict:
    return dict(PUSH, **changed)


def may(method: str, rest: str, body=None, said=None) -> bool:
    return push.permits(method, GIT + rest, body, PUSH if said is None else said)


class Push(unittest.TestCase):
    def test_the_push_reads_the_admitted_commit_and_its_own_branch_and_nothing_else(self):
        for rest in ("commits/" + PARENT, "blobs/" + BLOB_A, "trees/" + ROOT_TREE + "?recursive=1", "ref/heads/" + BRANCH):
            self.assertTrue(may("GET", rest), rest)
            self.assertFalse(may("GET", rest, {}), rest)
            self.assertFalse(may("DELETE", rest), rest)
        for rest in ("commits/" + PARENT[1:], "commits/" + PARENT.upper(), "commits/" + PARENT + "/comments",
                     "blobs/", "blobs/main", "trees/" + ROOT_TREE, "trees/" + ROOT_TREE + "?recursive=1&x=1",
                     "trees/main?recursive=1", "ref/heads/main", "ref/heads/" + BRANCH + "0", "ref/heads/" + BRANCH + "/x",
                     "ref/tags/factory/v0.1.12", "refs/heads/" + BRANCH, "refs", "matching-refs/heads/", "../pulls",
                     "../contents/config/hooks.json", ""):
            self.assertFalse(may("GET", rest), rest)
        # Nothing outside this repo's git data, whatever it begins with.
        for path in ("/repos/%s/pulls" % REPO, "/repos/%s/contents/x" % REPO, "/repos/%s/git" % REPO,
                     "/repos/combsmith/other/git/commits/" + PARENT, "/repos/combsmith/software-fictory/git/commits/" + PARENT, "/repos/%s-canary/git/commits/%s" % (REPO, PARENT),
                     "https://api.github.com" + GIT + "commits/" + PARENT, GIT[1:] + "commits/" + PARENT):
            self.assertFalse(push.permits("GET", path, None, PUSH), path)
        self.assertFalse(push.permits(None, GIT + "commits/" + PARENT, None, PUSH))
        self.assertFalse(push.permits("GET", None, None, PUSH))
        self.assertFalse(may("get", "commits/" + PARENT))

    def test_a_blob_is_made_of_base64_and_nothing_else_is_said_of_it(self):
        self.assertTrue(may("POST", "blobs", {"content": "QQo=", "encoding": "base64"}))
        for body in (None, {"content": "A\n", "encoding": "utf-8"}, {"content": b"QQo=", "encoding": "base64"},
                     {"content": "QQo="}, {"content": "QQo=", "encoding": "base64", "x": 1}, ["QQo="]):
            self.assertFalse(may("POST", "blobs", body), body)
        self.assertFalse(may("POST", "blobs/" + BLOB_A, {"content": "QQo=", "encoding": "base64"}))

    def test_the_one_tree_is_made_upon_the_admitted_one_and_names_exactly_the_changes(self):
        self.assertTrue(may("POST", "trees", NEW_TREE))
        self.assertTrue(may("POST", "trees", dict(NEW_TREE, tree=ENTRIES[::-1])))
        entry = lambda at, **changed: ENTRIES[:at] + [dict(ENTRIES[at], **changed)] + ENTRIES[at + 1:]
        without = [{k: v for k, v in ENTRIES[0].items() if k != "type"}] + ENTRIES[1:]
        for said, entries in (
                ("a path the changes do not hold", entry(0, path="config/hooks.json")),
                ("a path more", ENTRIES + [dict(ENTRIES[0], path="docs/more.md")]),
                ("a path fewer", ENTRIES[:2]), ("a path twice", [ENTRIES[0], ENTRIES[0], ENTRIES[2]]),
                ("a path twice in place of a removal", [ENTRIES[0], ENTRIES[1], ENTRIES[0]]),
                ("a file in a mode the changes do not give it", entry(0, mode="100755")),
                ("a link", entry(0, mode="120000")), ("a submodule", entry(0, mode="160000", type="commit")),
                ("a tree", entry(0, type="tree", mode="040000")), ("a file named a tree", entry(0, type="tree")), ("a file written as no blob", entry(0, sha=None)),
                ("a blob named by no name", entry(0, sha="main")), ("a removal that names a blob", entry(2, sha=BLOB_A)),
                ("a removal in no file's mode", entry(2, mode="120000")),
                ("an entry that says more", entry(0, content="x")), ("an entry that says less", without),
                ("a path that is no text", entry(0, path=["docs/a.md"])), ("an entry that is none", [None] + ENTRIES[1:]),
                ("no list", {"docs/a.md": ENTRIES[0]})):
            self.assertFalse(may("POST", "trees", dict(NEW_TREE, tree=entries)), said)
        for body in (None, {"tree": ENTRIES}, dict(NEW_TREE, base_tree=MADE), dict(NEW_TREE, base_tree=None),
                     dict(NEW_TREE, x=1)):
            self.assertFalse(may("POST", "trees", body), body)
        self.assertFalse(may("POST", "trees/" + ROOT_TREE, NEW_TREE))

    def test_the_one_commit_stands_on_the_admitted_commit_alone_and_says_what_apply_says(self):
        self.assertTrue(may("POST", "commits", COMMIT))
        for body in (None, dict(COMMIT, parents=[]), dict(COMMIT, parents=[MADE]), dict(COMMIT, parents=[PARENT, MADE]),
                     dict(COMMIT, parents=[PARENT, PARENT]), dict(COMMIT, parents=PARENT), dict(COMMIT, parents=(PARENT,)),
                     dict(COMMIT, message="Fixes #1"), dict(COMMIT, message=None), dict(COMMIT, tree="main"),
                     dict(COMMIT, tree=None), dict(COMMIT, author={"name": "Don Petry", "email": "x@example.com"}),
                     dict(COMMIT, committer={"name": "x", "email": "x@example.com"}), dict(COMMIT, signature="x"),
                     {"message": COMMIT["message"], "tree": MADE}):
            self.assertFalse(may("POST", "commits", body), body)

    def test_the_branch_is_made_or_moved_forward_never_forced_and_no_other_ref_is_written(self):
        made, moved = {"ref": "refs/heads/" + BRANCH, "sha": MADE}, {"sha": MADE, "force": False}
        here, stands = "refs/heads/" + BRANCH, told(head=PARENT)
        # Where the Decision admitted no branch it is made, and never moved; where it admitted a head, the reverse.
        self.assertTrue(may("POST", "refs", made))
        self.assertFalse(may("PATCH", here, moved))
        self.assertTrue(may("PATCH", here, moved, stands))
        self.assertFalse(may("POST", "refs", made, stands))
        for body in (None, dict(made, ref="refs/heads/main"), dict(made, ref="refs/heads/" + BRANCH + "-2"),
                     dict(made, ref="refs/tags/factory/v0.1.13"), dict(made, ref=BRANCH), dict(made, sha="main"),
                     dict(made, force=True), {"ref": "refs/heads/" + BRANCH}):
            self.assertFalse(may("POST", "refs", body), body)
        for body in (None, dict(moved, force=True), dict(moved, force=0), dict(moved, force=None), {"sha": MADE},
                     dict(moved, sha="main"), dict(moved, ref="refs/heads/main")):
            self.assertFalse(may("PATCH", here, body, stands), body)
        for rest in ("refs/heads/main", "refs/heads/" + BRANCH + "0", "refs/heads/" + BRANCH + "/x", "refs/heads/",
                     "refs/tags/factory/v0.1.12", "refs/heads/factory-work/issue-838-2", "refs"):
            self.assertFalse(may("PATCH", rest, moved, stands), rest)
        for method in ("DELETE", "PUT", "POST"):
            self.assertFalse(may(method, here, moved, stands), method)
            self.assertFalse(may(method, here, None, stands), method)

    def test_a_push_told_in_part_or_wrongly_is_permitted_nothing(self):
        ask = lambda said: push.permits("GET", "/repos/%s/git/commits/%s" % (said.get("repo"), PARENT), None, said)
        self.assertTrue(ask(PUSH))
        self.assertTrue(ask(told(head=MADE, repo="a-b/c_d.e", branch="factory-work/issue-1-10")))
        for said in ({k: v for k, v in PUSH.items() if k != "head"}, told(more=1), told(repo="combsmith"),
                     told(repo="combsmith/software-factory/x"), told(repo="combsmith/.."), told(repo="../software-factory"),
                     told(repo="/software-factory"), told(repo="combsmith/"), told(repo="comb smith/x"), told(repo=None),
                     told(branch="main"), told(branch="factory-work/issue-838"), told(branch="factory-work/issue-0-1"),
                     told(branch="factory-work/issue-838-0"), told(branch="factory-work/issue-838-01"),
                     told(branch="factory-work/issue-838-1/x"), told(branch="factory-work/issue-838-1-1"),
                     told(branch="factory-work/issue--1"), told(branch="factory-work/issue-838-"),
                     told(branch="factory/v0.1.12"), told(branch="factory-wurk/issue-838-1"), told(branch="refs/heads/" + BRANCH), told(branch=None),
                     told(parent="main"), told(parent=None), told(tree=PARENT[1:]), told(tree=None), told(head="main"),
                     told(head=False), told(message=""), told(message=None), told(message=b"x"), told(changes=None)):
            self.assertFalse(ask(said), said)
        self.assertFalse(push.permits("GET", GIT + "commits/" + PARENT, None, None))
        # Nor changes in any shape but the one `applied` gives: a file's two modes, bytes, and no path both ways.
        shaped = lambda **changed: told(changes=dict(CHANGES, **changed))
        for said in (shaped(written={"docs/a.md": ("120000", b"x")}), shaped(written={"docs/a.md": (FILE, "x")}),
                     shaped(written={"docs/a.md": [FILE, b"x"]}), shaped(written={"docs/a.md": (FILE, b"x", b"y")}),
                     shaped(written={"tests/t.py": (FILE, b"x")}), shaped(written={1: (FILE, b"x")}),
                     shaped(written=[("docs/a.md", (FILE, b"x"))]), shaped(removed=("tests/t.py",)),
                     shaped(removed=["tests/t.py", "tests/t.py"]), shaped(removed=[None]),
                     shaped(written={}, removed=[])):
            self.assertFalse(ask(said), said["changes"])
        self.assertTrue(ask(shaped(written={})))
        self.assertTrue(ask(shaped(removed=[])))


if __name__ == "__main__":
    unittest.main()
