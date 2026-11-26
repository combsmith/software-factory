"""The guards on a Role's own writes (issue 838). `guards/patch.py`: a Role's patch, read as git writes it and applied
byte for byte, or not at all. `guards/push.py`: what a push is told, and the paths apply is asked about."""
from __future__ import annotations

import os
import pathlib
import random
import subprocess
import tempfile
import unicodedata
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
RENAMED = (b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 87%\nrename from docs/a.md\nrename to docs/b.md\n"
           b"index 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/b.md\n@@ -1,2 +1,2 @@\n-a\n+A\n b\n")
COPIED = b"diff --git a/docs/a.md b/docs/c.md\nsimilarity index 100%\ncopy from docs/a.md\ncopy to docs/c.md\n"
MODE = b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 100755\n"
EMPTY = b"diff --git a/%s b/%s\nnew file mode 100644\nindex 0000000..e69de29\n"
TREE = {"docs/a.md": FILE, "run.sh": "100755", "link": "120000", "vendored": "160000", "tests/t.py": FILE}
HELD = {"docs/a.md": OLD, "run.sh": b"#!/bin/sh\n", "link": b"docs/a.md", "tests/t.py": b"x\n"}


def readable(data: bytes) -> list:
    """The sections of a patch `patch.read` reads: where it reads none an assertion fails, so a rule broken to refuse
    what git writes fails a test, and never raises in one."""
    said = patch.read(data)
    assert said is not None, data
    return said


def section(name: str, hunks: bytes, old: str = None, extended: bytes = b"index 1111111..2222222 100644\n") -> bytes:
    """One section that changes `name`, or `old` into `name`, as git writes it."""
    was = (old or name).encode()
    return b"diff --git a/%s b/%s\n%s--- a/%s\n+++ b/%s\n%s" % (was, name.encode(), extended, was, name.encode(), hunks)


def new_file(hunks: bytes) -> bytes:
    return b"diff --git a/n b/n\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n+++ b/n\n" + hunks


def gone_file(hunks: bytes) -> bytes:
    return b"diff --git a/f b/f\ndeleted file mode 100644\nindex 1111111..0000000\n--- a/f\n+++ /dev/null\n" + hunks


def after(old: bytes, hunks: bytes):
    """What a file of `old` holds once `hunks`, as a patch writes them, are applied; None where they are not its."""
    return patch.content(old, readable(section("docs/a.md", hunks))[0]["hunks"])


def landed(data, tree=None, held=None):
    return patch.applied(data, TREE if tree is None else tree, HELD if held is None else held)


class Patch(unittest.TestCase):
    def test_a_patch_is_read_section_by_section_as_git_writes_it(self):
        line = lambda sign, text: {"sign": sign, "text": text, "bare": False}
        hunk = {"old_start": 1, "old_count": 2, "new_start": 1, "new_count": 2, "lines": [line(b"-", b"a"), line(b"+", b"A"), line(b" ", b"b")]}
        self.assertEqual(patch.read(RENAMED), [{"kind": "rename", "old": "docs/a.md", "new": "docs/b.md", "hunks": [hunk],
                                                "index_mode": "100644", "old_mode": None, "new_mode": None}])
        # Each section in its order: a copy, a change of mode, a file moved, and an empty file made and one removed.
        empty = b"diff --git a/docs/e b/docs/e\nnew file mode 100755\nindex 0000000..e69de29\n"
        gone = b"diff --git a/docs/g b/docs/g\ndeleted file mode 100644\nindex e69de29..0000000\n"
        said = [(s["kind"], s["old"], s["new"], s["old_mode"], s["new_mode"], s["index_mode"])
                for s in readable(COPIED + MODE.replace(b"docs/a.md", b"docs/m.md") + RENAMED + empty + gone)]
        # A link's mode and a submodule's are modes git writes of a file made or removed, and are read: whether such a
        # file may be written is not asked in reading. An index line gives a mode only where the section has no line
        # of its own for one.
        other = (b"diff --git a/l b/l\nnew file mode 120000\nindex 0000000..2222222\n"
                 b"diff --git a/m b/m\ndeleted file mode 160000\nindex 1111111..0000000\n")
        self.assertEqual([(s["old_mode"], s["new_mode"]) for s in readable(other)], [(None, "120000"), ("160000", None)])
        self.assertIsNone(patch.read(MODE + b"index 1111111..2222222\n")[0]["index_mode"])
        self.assertEqual(readable(RENAMED.replace(b" 100644", b" 100755"))[0]["index_mode"], "100755")
        plain = readable(b"diff --git a/f b/f\nold mode 100755\nnew mode 100644\n")[0]       # a mode changed either way
        self.assertEqual((plain["old_mode"], plain["new_mode"]), ("100755", "100644"))
        self.assertEqual(said, [("copy", "docs/a.md", "docs/c.md", None, None, None),
                                ("change", "docs/m.md", "docs/m.md", "100644", "100755", None),
                                ("rename", "docs/a.md", "docs/b.md", None, None, "100644"),
                                ("new", "docs/e", "docs/e", None, "100755", None),
                                ("deleted", "docs/g", "docs/g", "100644", None, None)])
        # A rename that changes the mode is read with both modes, in the order git writes its lines.
        runnable = (b"diff --git a/docs/a.md b/docs/r\nold mode 100644\nnew mode 100755\nsimilarity index 100%\n"
                    b"rename from docs/a.md\nrename to docs/r\n")
        self.assertEqual([(s["kind"], s["old_mode"], s["new_mode"]) for s in readable(runnable)], [("rename", "100644", "100755")])
        # A hash is read from git's shortest abbreviation to a SHA-256 name in full, each side to its own length; a
        # name git abbreviates may be all zeros on a side a file has.
        for hashes in (b"a" * 64 + b".." + b"b" * 64, b"abcd..1234567", b"1234567..abcd", b"0000000..2222222", b"1111111..0000"):
            self.assertEqual(len(readable(RENAMED.replace(b"1111111..2222222", hashes))), 1, hashes)

    def test_a_name_is_read_one_way_or_not_at_all(self):
        good = MODE
        self.assertEqual(len(readable(good)), 1)
        self.assertEqual(landed(good)[1], None)
        names = (b'"docs/a\\303\\251.md"', b"docs/a b.md", b"docs/caf\xc3\xa9.md", b"docs/a\\b.md", b'docs/a"b.md',
                 b"docs/../x", b"./x", b"docs//x", b"/x", b"x/", b".git/config", b"docs/.GIT/x", b"docs/a\tb", b"",
                 b"docs/..", b"docs/.", b"..", b"docs/a\x7f.md", b"C:.git/note", b"C:/note", b"a:b")
        for name in names:
            with self.subTest(name=name):
                data = good.replace(b"docs/a.md", name)
                self.assertIsNone(patch.read(data))
                self.assertEqual(landed(data), (None, patch.UNREADABLE))
        # git's own directory in each form git knows it by on some file system, at any depth; and names that only
        # look like it, which are read.
        for name in (b"git~1/config", b"GIT~1/config", b"docs/git~2/x", b".git./config", b".GIT.../hooks/x", b"git~"):
            with self.subTest(name=name):
                self.assertIsNone(patch.read(good.replace(b"docs/a.md", name)))
        for name in (b".gitignore", b"docs/.gitkeep", b".github/x", b"x.git/y", b"legit~1", b"docs/.git-x", b"git/x"):
            with self.subTest(name=name):
                self.assertEqual(readable(good.replace(b"docs/a.md", name))[0]["new"], name.decode())
        # A name may hold capitals, as most do.
        self.assertEqual((readable(good.replace(b"docs/a.md", b"README.md"))[0]["new"], patch.named("docs/README.md")),
                         ("README.md", True))
        # A name is read alike as text, for a caller that holds a path and no patch; and what is no text is no name.
        self.assertIs(patch.named("docs/a.md"), True)
        # Nor is text of a subclass of str, whose own methods would be read in place of the built-in ones.

        class Said(str):
            def split(self, sep=None, maxsplit=-1):
                return ["docs"]
        self.assertEqual((patch.named(Said("docs")), patch.named(Said("docs/../x"))), (False, False))
        for name in ("", "docs/a b.md", "docs/../x", "docs//x", ".git/config", "docs/caf\u00e9.md", b"docs/a.md", None, ["docs/a.md"],
                     "docs/a.md\n", "docs/a\r", "a\x00b", "a\x7f"):
            self.assertIs(patch.named(name), False, name)
        # A name has no more parts than the bound, which git does not have and no path of this repo's is near.
        deep = "/".join(["d"] * len(patch.DEEPEST))
        self.assertEqual((len(patch.DEEPEST), patch.named(deep), patch.named(deep + "/x")), (32, True, False))
        self.assertEqual(readable(good.replace(b"docs/a.md", deep.encode()))[0]["new"], deep)
        self.assertIsNone(patch.read(good.replace(b"docs/a.md", deep.encode() + b"/x")))
        # Every line that names a file names what the header names: a rename's line, a copy's.
        moved = b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 100%\nrename from docs/a.md\nrename to docs/b.md\n"
        # A file copied and then moved, as `git diff -C` writes one: a copy's source alone is named again.
        self.assertEqual([said["kind"] for said in readable(COPIED + moved)], ["copy", "rename"])
        for data in (moved.replace(b"rename from docs/a.md", b"rename from run.sh"),
                     moved.replace(b"rename to docs/b.md", b"rename to run.sh"),
                     moved.replace(b"rename to docs/b.md\n", b""), moved.replace(b"similarity index 100%\n", b""),
                     moved.replace(b"rename from docs/a.md\n", b""), COPIED.replace(b"copy from docs/a.md\n", b""),
                     RENAMED.replace(b"similarity index 87%\n", b""),      # and one with hunks, as below 100% alike
                     moved.replace(b"rename", b"copy", 1), moved.replace(b"b/docs/b.md", b"b/docs/a.md"),
                     moved.replace(b"docs/b.md", b"docs/a.md"),      # a file renamed to itself
                     COPIED.replace(b"docs/c.md", b"docs/a.md"),     # and one copied to itself
                     # a rename and a copy are held name by name: a name that is none, on one side alone
                     moved.replace(b"docs/b.md", b".git/config"), moved.replace(b"docs/a.md", b".git/config"),
                     COPIED.replace(b"docs/c.md", b"docs/c d.md"), COPIED.replace(b"docs/a.md", b"docs/.."),
                     # a copy whose own lines name another file than its header does, on either side
                     COPIED.replace(b"copy from docs/a.md", b"copy from run.sh"), COPIED.replace(b"copy to docs/c.md", b"copy to run.sh"),
                     # one line of a rename or a copy, on a section that is otherwise a change of mode
                     b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 100755\nrename from run.sh\n",
                     b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 100755\ncopy to run.sh\n",
                     moved.replace(b"similarity index 100%", b"similarity index x%"), RENAMED.replace(b"index 87%", b"index x%"),
                     b"diff --git a/docs/a.md b/run.sh\nold mode 100644\nnew mode 100755\n",     # two names and no rename
                     moved + b"copy from docs/a.md\ncopy to docs/b.md\n"):
            with self.subTest(data=data):
                self.assertIsNone(patch.read(data))
                self.assertEqual(landed(data), (None, patch.UNREADABLE))

    def test_what_is_not_a_patch_as_git_writes_it_is_unreadable(self):
        cases = (
            b"", "", None, MODE.decode(), MODE[:-1], b"\n", b"From x\n" + MODE, MODE + b"\n", MODE + b"trailer\n", MODE + b" ",
            MODE.replace(b"diff --git a/docs/a.md b/docs/a.md\n", b""),
            # A section's first line is git's, with git's two sides before its two names.
            b"some words a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 100755\n",
            MODE.replace(b"diff --git a/", b"diff --git "), MODE.replace(b" b/docs/a.md\nold", b" docs/a.md\nold"),
            MODE.replace(b" b/docs/a.md\nold", b" x/docs/a.md\nold"), MODE.replace(b"diff --git a/", b"diff --git x/"),
            # The lines under it are git's, each once; an index line gives two hashes, and a mode git writes or none.
            RENAMED.replace(b"index 1111111..2222222 100644\n", b"something else\n"),
            RENAMED.replace(b"index 1111111..2222222 100644\n", b"index 1111111..2222222 100644\nindex 1111111..2222222 100644\n"),
            RENAMED.replace(b"1111111..2222222", b"1111111.2222222"),
            RENAMED.replace(b"2222222 100644", b"2222222 file"),
            b"diff --git a/x.bin b/x.bin\nindex 1111111..2222222 100644\nGIT binary patch\nliteral 2\nJcmZQ%0000\n\n",
            b"diff --git a/x.bin b/x.bin\nindex 1111111..2222222 100644\nBinary files a/x.bin and b/x.bin differ\n",
            b"diff --git a/docs/a.md b/docs/a.md\nindex 1111111..2222222 100644\n",           # a section that changes nothing
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\n",
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode rwx\n",
            b"diff --git a/n b/n\ndeleted file mode 100644\nnew file mode 100644\nindex 0000000..0000000\n",
            b"diff --git a/n b/n\nold mode 100644\nnew mode 100755\nnew file mode 100644\nindex 0000000..2222222\n",
            # A mode git does not write; a change of mode to the same mode; a second mode on the index line.
            b"diff --git a/f b/f\nold mode 100644\nnew mode 999\n", b"diff --git a/f b/f\nold mode 1\nnew mode 100644\n",
            b"diff --git a/n b/n\nnew file mode 7\nindex 0000000..2222222\n",
            b"diff --git a/f b/f\ndeleted file mode 0100644\nindex 1111111..0000000\n",
            b"diff --git a/f b/f\nold mode 100644\nnew mode 100644\n",
            b"diff --git a/n b/n\nnew file mode 100644\nindex 0000000..2222222 100755\n",
            b"diff --git a/f b/f\ndeleted file mode 100644\nindex 1111111..0000000 100644\n",
            b"diff --git a/f b/f\nindex 1111111..2222222 120000\nold mode 100644\nnew mode 100755\n",
            MODE + b"index 1111111..2222222 100755\n",
            # What only a rename or a copy has, on a section that is neither.
            b"diff --git a/a b/b\nnew file mode 100644\nsimilarity index 100%\nrename from a\nrename to b\nindex 0000000..2222222\n",
            b"diff --git a/f b/f\nold mode 100644\nnew mode 100755\nsimilarity index 100%\n",
            b"diff --git a/a b/b\ndeleted file mode 100644\nsimilarity index 100%\nrename from a\nrename to b\nindex 1111111..0000000\n",
            b"diff --git a/f b/f\nold mode 100644\nnew mode 100755\ndeleted file mode 100644\nindex 1111111..0000000\n",
            # How alike two files are is a whole number of percent, of a digit at least and 100 at most.
            RENAMED.replace(b"index 87%", b"index 87"), RENAMED.replace(b"index 87%", b"index 101%"),
            RENAMED.replace(b"index 87%", b"index 1000%"), RENAMED.replace(b"index 87%", b"index 087%"),
            RENAMED.replace(b"index 87%", b"index 07%"), RENAMED.replace(b"index 87%", b"index %"),
            # One section git does not write, after one it does, leaves the patch unread, not read in part.
            MODE + b"diff --git a/x b/x\nold mode 100644\n",
            # A change of mode is a file's, between its two modes: git writes a change of type as a removal and a new file.
            b"diff --git a/f b/f\nold mode 100644\nnew mode 120000\n", b"diff --git a/f b/f\nold mode 120000\nnew mode 100644\n",
            b"diff --git a/f b/f\nold mode 100755\nnew mode 160000\n",
            b"diff --git a/a b/l\nold mode 100644\nnew mode 120000\nsimilarity index 100%\nrename from a\nrename to l\n",
            b"diff --git a/l b/c\nold mode 120000\nnew mode 100644\nsimilarity index 100%\ncopy from l\ncopy to c\n",
            # git writes a section's lines in one order: its modes, how alike, a rename's or a copy's lines, the index.
            b"diff --git a/f b/f\nnew mode 100755\nold mode 100644\n",
            b"diff --git a/a b/b\nsimilarity index 100%\nrename to b\nrename from a\n",
            b"diff --git a/a b/c\nsimilarity index 100%\ncopy to c\ncopy from a\n",
            b"diff --git a/a b/b\nrename from a\nrename to b\nsimilarity index 100%\n",
            b"diff --git a/a b/b\nsimilarity index 100%\nold mode 100644\nnew mode 100755\nrename from a\nrename to b\n",
            RENAMED.replace(b"similarity index 87%\n", b"index 1111111..2222222 100644\nsimilarity index 87%\n"),
            b"diff --git a/n b/n\nindex 0000000..2222222\nnew file mode 100644\n",
            # An index line's hashes are lower hex, of four characters to a SHA-256 name in full; a new file's first is
            # zeros and a removed one's second. A new file and a removed one have an index line, and a section with no
            # mode line of its own has its mode there.
            RENAMED.replace(b"1111111..2222222", b"1111111..222222F"), RENAMED.replace(b"1111111..2222222", b"111111F..2222222"),
            RENAMED.replace(b"1111111..2222222", b"a" * 65 + b"..2222222"), RENAMED.replace(b"1111111..2222222", b"1111111.." + b"b" * 65),
            RENAMED.replace(b"1111111..", b"1.."), RENAMED.replace(b"1111111..", b"11.."), RENAMED.replace(b"1111111..", b"111.."),
            RENAMED.replace(b"..2222222", b"..2"), RENAMED.replace(b"..2222222", b"..22"), RENAMED.replace(b"..2222222", b"..222"),
            b"diff --git a/n b/n\nnew file mode 100644\nindex 1111111..2222222\n",
            b"diff --git a/f b/f\ndeleted file mode 100644\nindex 1111111..2222222\n",
            b"diff --git a/n b/n\nnew file mode 100644\n", b"diff --git a/f b/f\ndeleted file mode 100644\n",
            RENAMED.replace(b" 100644", b""),
            # No path is in two sections: none written twice, and no file removed and one made at its path, which is
            # how git writes a change of a file's type.
            MODE + MODE, RENAMED + MODE.replace(b"docs/a.md", b"docs/b.md"), COPIED + COPIED.replace(b"docs/a.md", b"run.sh"),
            MODE + COPIED + MODE,
            # Nor is a path named again once a section renames or removes it, nor one a section made read again.
            RENAMED + RENAMED.replace(b"docs/b.md", b"docs/c.md"), RENAMED + MODE,
            RENAMED + b"diff --git a/run.sh b/docs/a.md\nsimilarity index 100%\nrename from run.sh\nrename to docs/a.md\n",
            b"diff --git a/docs/a.md b/docs/a.md\ndeleted file mode 100644\nindex 1111111..0000000\n" + RENAMED,
            RENAMED + b"diff --git a/docs/b.md b/docs/c.md\nsimilarity index 100%\nrename from docs/b.md\nrename to docs/c.md\n",
            # Nor is a path changed in place moved away after: git writes a copy of it after its change, never a rename.
            MODE + RENAMED,
            # No file made stands where another made needs a directory, whichever comes first, at any depth.
            EMPTY % ((b"d/e",) * 2) + EMPTY % ((b"d/e/x",) * 2), EMPTY % ((b"d/e/x",) * 2) + EMPTY % ((b"d/e",) * 2),
            b"diff --git a/f b/f\ndeleted file mode 100644\nindex 1111111..0000000\n"
            b"diff --git a/f b/f\nnew file mode 120000\nindex 0000000..2222222\n",
            b"diff --git a/f b/f\nnew file mode 100644\nindex 0000000..2222222\n"
            b"diff --git a/f b/f\ndeleted file mode 100644\nindex 1111111..0000000\n",
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertIsNone(patch.read(data))
                self.assertIsNone(patch.sources(data))
                self.assertEqual(landed(data), (None, patch.UNREADABLE))
        # A file removed and a directory made in its place, as git writes it, is read.
        gone = EMPTY.replace(b"new", b"deleted").replace(b"0000000..e69de29", b"e69de29..0000000")
        self.assertEqual(len(readable(gone % ((b"e",) * 2) + EMPTY % ((b"e/x",) * 2))), 2)
        # A file changed in place and then copied, as git writes it, is read.
        self.assertEqual([said["kind"] for said in readable(MODE + COPIED)], ["change", "copy"])
        # How alike two files are is asked its length before its value, which is never built of a count too long.
        said, number = [], patch._number
        patch._number = lambda digits: said.append(digits) or number(digits)
        try:
            self.assertIsNone(patch.read(RENAMED.replace(b"87", b"9" * 4000)))
        finally:
            patch._number = number
        self.assertEqual(said, [])
        # Two files wholly alike and wholly unlike are read: the first with no hunk, the second with its hunks.
        self.assertEqual([len(readable(data)) for data in (COPIED, RENAMED.replace(b"index 87%", b"index 0%"))], [1, 1])
        # git says a rename is 100% alike where it only moved lines, and still writes the hunk that moves them.
        moved = (b"diff --git a/f b/g\nsimilarity index 100%\nrename from f\nrename to g\nindex 422c2b7..0e1677a 100644\n"
                 b"--- a/f\n+++ b/g\n@@ -1,2 +1,2 @@\n-a\n b\n+a\n")
        self.assertEqual([len(section["hunks"]) for section in readable(moved)], [1])
        # What is bytes of a subclass is not read: its own methods would be read in place of the built-in ones.

        class Said(bytes):
            def split(self, sep=None, maxsplit=-1):
                return MODE.split(b"\n")
        self.assertIsNone(patch.read(Said(b"x")))

    def test_a_sections_hunks_are_read_as_their_headers_count_them(self):
        line = lambda sign, text: {"sign": sign, "text": text, "bare": False}
        hunk = {"old_start": 2, "old_count": 3, "new_start": 2, "new_count": 3,
                "lines": [line(b" ", b"b"), line(b"-", b"c"), line(b"+", b"C"), line(b" ", b"d")]}
        self.assertEqual(patch.read(CHANGE), [{"kind": "change", "old": "docs/a.md", "new": "docs/a.md", "hunks": [hunk],
                                               "index_mode": "100644", "old_mode": None, "new_mode": None}])
        # A file changed and then copied, as git writes it; the file moved is another, as no file changed is moved.
        moved = RENAMED.replace(b"docs/a.md", b"run.sh")
        said = [(s["kind"], s["old"], s["new"], len(s["hunks"])) for s in readable(NEW + GONE + MODE + COPIED + moved)]
        self.assertEqual(said, [("new", "docs/n.md", "docs/n.md", 1), ("deleted", "tests/t.py", "tests/t.py", 1),
                                ("change", "docs/a.md", "docs/a.md", 0), ("copy", "docs/a.md", "docs/c.md", 0),
                                ("rename", "run.sh", "docs/b.md", 1)])
        # A copy with edits is read with its hunks, as a rename with edits is.
        edited = (COPIED.replace(b"100%", b"87%") + b"index 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/c.md\n"
                  b"@@ -1 +1 @@\n-a\n+A\n")
        self.assertEqual([(s["kind"], len(s["hunks"])) for s in readable(edited)], [("copy", 1)])
        # After a header's second `@@` git writes nothing, or a space and the line the hunk stands under. A line's
        # bytes are its own to the last: a space, a tab or a carriage return at its end is read.
        under = readable(section("docs/a.md", b"@@ -2,3 +2,3 @@ def f():\n b \t\r\n-c \r\n+C\t\r\n d\n"))[0]["hunks"][0]
        self.assertEqual([said["text"] for said in under["lines"]], [b"b \t\r", b"c \r", b"C\t\r", b"d"])
        # And from the first: a line put in with spaces before it, and an empty one, are each their own bytes.
        spaced = readable(section("docs/a.md", b"@@ -1 +1,3 @@\n a\n+    x\n+\n"))[0]["hunks"][0]
        self.assertEqual([(said["sign"], said["text"]) for said in spaced["lines"]], [(b" ", b"a"), (b"+", b"    x"), (b"+", b"")])
        # Each hunk of a section is read, with each side's own place and count.
        two = readable(section("docs/a.md", b"@@ -2,2 +2,3 @@\n b\n+C\n d\n@@ -9,3 +10,2 @@\n x\n-y\n z\n"))[0]["hunks"]
        self.assertEqual([(h["old_start"], h["old_count"], h["new_start"], h["new_count"], len(h["lines"])) for h in two],
                         [(2, 2, 2, 3, 3), (9, 3, 10, 2, 3)])
        self.assertEqual(readable(section("docs/a.md", b"@@ -999999999 +999999999 @@\n-a\n+A\n"))[0]["hunks"][0]["old_start"],
                         999999999)
        # A count of 0 says where a hunk stands: after the line its start names, or at the top for 0. Lines taken out
        # leave the new side at the line before them, and each new side stands where the hunks before it put it.
        for hunks, places in ((b"@@ -0,0 +1 @@\n+x\n", [(0, 0, 1, 1)]), (b"@@ -2,0 +3 @@\n+x\n", [(2, 0, 3, 1)]),
                              (b"@@ -2,2 +1,0 @@\n-b\n-c\n", [(2, 2, 1, 0)]),
                              (b"@@ -1 +1,3 @@\n-a\n+x\n+y\n+z\n@@ -3,0 +6 @@\n+w\n", [(1, 1, 1, 3), (3, 0, 6, 1)]),
                              (b"@@ -1,3 +0,0 @@\n-a\n-b\n-c\n@@ -5 +2 @@\n-e\n+E\n", [(1, 3, 0, 0), (5, 1, 2, 1)])):
            with self.subTest(hunks=hunks):
                read = readable(section("docs/a.md", hunks))[0]["hunks"]
                self.assertEqual([(h["old_start"], h["old_count"], h["new_start"], h["new_count"]) for h in read], places)
        # A hunk changes a line, or only the newline at a last line's end; a line may move past one both sides hold.
        for hunks in (b"@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+a\n", b"@@ -1,2 +1,2 @@\n-a\n b\n+a\n"):
            self.assertEqual(len(readable(section("docs/a.md", hunks))[0]["hunks"]), 1, hunks)
        # A count a header leaves out is one line; git's marker says the line before it has no newline at its end,
        # in a hunk or after its last line.
        marker = b"\\ No newline at end of file\n"
        for lines, bare in ((b"-a\n" + marker + b"+A\n", [True, False]), (b"-a\n+A\n" + marker, [False, True]),
                            (b"-a\n" + marker + b"+A\n" + marker, [True, True])):
            hunk = readable(section("docs/a.md", b"@@ -1 +1 @@\n" + lines))[0]["hunks"][0]
            self.assertEqual((hunk["old_count"], hunk["new_count"], [said["bare"] for said in hunk["lines"]]), (1, 1, bare))
            self.assertEqual([said["text"] for said in hunk["lines"]], [b"a", b"A"])      # a marked line's bytes are its own
        ends = readable(section("docs/a.md", b"@@ -1,2 +1,2 @@\n-a\n+A\n b\n" + marker))[0]["hunks"][0]
        self.assertEqual([(said["text"], said["bare"]) for said in ends["lines"]], [(b"a", False), (b"A", False), (b"b", True)])

    def test_a_hunk_or_a_side_git_does_not_write_is_unreadable(self):
        marker = b"\\ No newline at end of file\n"
        good = section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\n")
        self.assertEqual(len(readable(good)), 1)
        cases = (
            CHANGE.decode(), CHANGE[:-1], CHANGE + b"\n", CHANGE + b"trailer\n", CHANGE + b" ",
            # Each side names what the header names, the old side of a new file and the new side of a removed one nothing.
            good.replace(b"--- a/docs/a.md", b"--- a/run.sh"), good.replace(b"+++ b/docs/a.md", b"+++ b/run.sh"),
            good.replace(b"+++ b/docs/a.md", b"+++ /dev/null"), good.replace(b"--- a/docs/a.md", b"--- /dev/null"),
            good.replace(b"+++ b/docs/a.md", b"+++ b/docs/a.md\t"),
            NEW.replace(b"--- /dev/null", b"--- a/docs/n.md"), GONE.replace(b"+++ /dev/null", b"+++ b/tests/t.py"),
            # The sides with no hunk under them; one side alone; a side as a patch's last line.
            CHANGE.replace(b"+++ b/docs/a.md\n", b""), CHANGE.replace(b"@@ -2,3 +2,3 @@\n b\n-c\n+C\n d\n", b""),
            new_file(b""), b"diff --git a/f b/f\nold mode 100644\nnew mode 100755\n--- a/f\n+++ b/f\n",
            b"diff --git a/f b/f\nindex 1111111..2222222 100644\n--- a/f\n",
            # A hunk cut short, or longer than its header counts; a line with no sign; a header git does not write.
            CHANGE.replace(b" d\n", b""), CHANGE.replace(b" d\n", b" d\n e\n"), CHANGE.replace(b" b\n", b"b\n"),
            CHANGE.replace(b" b\n", b"\n"), CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 @@"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,3"), CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,03 +2,3 @@"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,x @@"), CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,3,1 @@"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,-3 @@"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -1000000000,3 +2,3 @@"), CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -1000000000,3 +1000000000,3 @@"),
            section("docs/a.md", b"@@ -0,x +1 @@\n+A\n"), section("docs/a.md", b"@@ -1 +0,x @@\n-a\n"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,3 @@def f():"), CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,3 @@@"),
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -2,3 +2,3 @@\r"),
            section("docs/a.md", b"@@ -1,0 +1,0 @@\n"), section("docs/a.md", b"@@ -1 +1 @@\n" + marker + b"-a\n+A\n"),
            section("docs/a.md", b"@@ -1 +1 @@\n-a\n" + marker + marker + b"+A\n"),
            section("docs/a.md", b"@@ -1 +1 @@\n-a\n\\ No newline\n+A\n"),
            # A hunk that changes nothing; a new file with an old line or two hunks; a removed one with a new line.
            section("docs/a.md", b"@@ -1,2 +1,2 @@\n a\n b\n"),
            new_file(b"@@ -1 +1,2 @@\n a\n+b\n"), new_file(b"@@ -0,0 +1 @@\n+x\n@@ -0,0 +2 @@\n+y\n"),
            gone_file(b"@@ -1,2 +1 @@\n a\n-b\n"), gone_file(b"@@ -1 +0,0 @@\n-a\n@@ -2 +0,0 @@\n-b\n"),
            new_file(b"@@ -0,0 +1 @@\n+x\n@@ -0,0 +1 @@\n+y\n"), gone_file(b"@@ -1 +0,0 @@\n-a\n@@ -1 +0,0 @@\n-b\n"),
            new_file(b"@@ -0,0 +1 @@\n+x\n@@ -1,0 +3 @@\n+y\n"), gone_file(b"@@ -1 +0,0 @@\n-a\n@@ -3 +1,0 @@\n-c\n"),
            # The one hunk of either stands at line 1 of the side that has lines, and at line 0 of the other.
            new_file(b"@@ -7,0 +8 @@\n+x\n"), new_file(b"@@ -0,0 +2 @@\n+x\n"), new_file(b"@@ -0,1 +1,2 @@\n a\n+b\n"),
            gone_file(b"@@ -2 +1,0 @@\n-a\n"), gone_file(b"@@ -2 +0,0 @@\n-a\n"), gone_file(b"@@ -1,2 +0,1 @@\n-a\n b\n"),
            # A hunk after one that holds git's marker: the file ended there, on one side or on both.
            section("f", b"@@ -1 +1 @@\n-a\n" + marker + b"+A\n" + marker + b"@@ -3 +3 @@\n-b\n+B\n"),
            section("f", b"@@ -1 +1 @@\n-a\n+A\n" + marker + b"@@ -3 +3 @@\n-c\n+C\n"),
            section("f", b"@@ -1 +1 @@\n-a\n" + marker + b"+A\n@@ -3,0 +4 @@\n+c\n"),
            # git's marker on a line that is not the last of its side, which git would join to the next.
            section("f", b"@@ -1 +1,2 @@\n-a\n+A\n" + marker + b"+B\n"), section("f", b"@@ -1,2 +1 @@\n-a\n" + marker + b"-b\n+A\n"),
            section("f", b"@@ -1,2 +1,2 @@\n a\n" + marker + b"-b\n+B\n"), section("f", b"@@ -1,2 +1,2 @@\n-a\n+A\n" + marker + b" b\n"),
            section("f", b"@@ -1 +1 @@\n-a\n+A\n" + marker + marker),
            # A line both sides hold after git's marker on an old line, or on a new one: that side had ended.
            section("f", b"@@ -1,2 +1 @@\n-a\n" + marker + b" b\n"), section("f", b"@@ -1 +1,2 @@\n+A\n" + marker + b" b\n"),
            # git's marker on an empty line, in a hunk or after its last: a line of no byte and no newline is no line.
            section("f", b"@@ -1 +1,2 @@\n a\n+\n" + marker), section("f", b"@@ -1 +1 @@\n-\n" + marker + b"+A\n"),
            section("f", b"@@ -1 +1 @@\n+\n" + marker + b"-a\n"), section("f", b"@@ -1,2 +1 @@\n a\n-\n" + marker),
            section("f", b"@@ -1,2 +1,2 @@\n-a\n+A\n \n" + marker),
            # A NUL in a line is a binary change written as text, and in the line a hunk stands under too.
            section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\x00\n"), section("docs/a.md", b"@@ -1 +1 @@\n-a\x00\n+A\n"),
            section("docs/a.md", b"@@ -1 +1 @@ f\x00g\n-a\n+A\n"),
            # Hunks out of their order, over each other, touching, or one again; a new side's start that is not where
            # the old side's and the hunks before put it; a start of 0 on a side that counts lines.
            section("f", b"@@ -5 +5 @@\n-b\n+B\n@@ -2 +2 @@\n-x\n+X\n"), section("f", b"@@ -5,2 +5 @@\n-b\n-c\n+B\n@@ -6 +5 @@\n-c\n+X\n"),
            section("f", b"@@ -5 +5 @@\n-b\n+B\n@@ -6 +6 @@\n-c\n+C\n"), section("f", b"@@ -5 +5 @@\n-b\n+B\n@@ -5,0 +6 @@\n+x\n"),
            section("f", b"@@ -1 +1 @@\n-a\n+A\n@@ -1 +1 @@\n-a\n+A\n"), section("f", b"@@ -0,0 +1 @@\n+x\n@@ -0,0 +2 @@\n+z\n"),
            section("f", b"@@ -5,2 +4,2 @@\n b\n-c\n+C\n"), section("f", b"@@ -5,2 +1,0 @@\n-b\n-c\n"),
            section("f", b"@@ -5,2 +5,0 @@\n-b\n-c\n"), section("f", b"@@ -8,0 +8 @@\n+x\n"),
            section("f", b"@@ -2,2 +2,3 @@\n b\n+C\n d\n@@ -9,3 +9,2 @@\n x\n-y\n z\n"),
            section("f", b"@@ -0,2 +0,2 @@\n a\n-b\n+B\n"), section("f", b"@@ -1 +0 @@\n-a\n+A\n"),
            # A count of one written out, which git leaves out; a space after the second `@@` and no line after it.
            section("f", b"@@ -1,1 +1 @@\n-a\n+A\n"), section("f", b"@@ -1 +1,1 @@\n-a\n+A\n"),
            section("f", b"@@ -1 +1 @@ \n-a\n+A\n"),
            # A line put in before one taken out, in a run of changes: git writes the old side's first.
            section("f", b"@@ -1 +1 @@\n+A\n-a\n"), section("f", b"@@ -1,3 +1,3 @@\n a\n+B\n-b\n c\n"),
            # A hunk whose two sides are the same lines, newline for newline: it changes nothing.
            section("f", b"@@ -1 +1 @@\n-a\n+a\n"), section("f", b"@@ -1,3 +1,3 @@\n a\n-b\n+b\n c\n"),
            section("f", b"@@ -1 +1 @@\n-a\n" + marker + b"+a\n" + marker),
            # Hunks with no index line, which git writes for every change of bytes.
            section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\n", extended=b""),
            # A rename or a copy below 100% alike with no hunk.
            RENAMED[:RENAMED.index(b"--- ")], COPIED.replace(b"100%", b"87%") + b"index 1111111..2222222 100644\n",
            # The old side's name, run on.
            good.replace(b"--- a/docs/a.md", b"--- a/docs/a.md.bak"),
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertIsNone(patch.read(data))
                self.assertIsNone(patch.sources(data))
                self.assertEqual(landed(data), (None, patch.UNREADABLE))

    def test_sources_names_each_file_a_patch_reads_once_and_no_new_file(self):
        self.assertEqual(patch.sources(CHANGE), ["docs/a.md"])
        self.assertEqual(patch.sources(NEW), [])
        self.assertEqual(patch.sources(RENAMED), ["docs/a.md"])
        # A file read with no hunk is read all the same: a copy, a rename and a change of mode, each alone.
        whole = b"diff --git a/run.sh b/bin/run.sh\nsimilarity index 100%\nrename from run.sh\nrename to bin/run.sh\n"
        self.assertEqual([patch.sources(data) for data in (COPIED, whole, MODE)], [["docs/a.md"], ["run.sh"], ["docs/a.md"]])
        self.assertEqual(patch.sources(CHANGE + COPIED + GONE), ["docs/a.md", "tests/t.py"])
        self.assertEqual(patch.sources(COPIED + CHANGE), ["docs/a.md"])      # by the name it reads, not the one it writes
        # In the patch's order, not the names': and two files of one name in two directories are two files.
        self.assertEqual(patch.sources(GONE + CHANGE), ["tests/t.py", "docs/a.md"])
        self.assertEqual(patch.sources(CHANGE.replace(b"docs/a.md", b"tests/a.md") + CHANGE), ["tests/a.md", "docs/a.md"])
        # A new file reads none, and the files after it are named all the same.
        self.assertEqual(patch.sources(NEW + CHANGE + NEW.replace(b"n.md", b"m.md") + GONE), ["docs/a.md", "tests/t.py"])

    def test_a_hunk_stands_where_its_header_says_and_nowhere_else(self):
        # Two hunks of one file, each where its header says; a line added at the top, one taken from the end. Where
        # hunks stand to each other and where each new side begins `read` holds, from the patch alone.
        self.assertEqual(after(OLD, b"@@ -1,2 +1,3 @@\n+z\n a\n b\n@@ -7,2 +8 @@\n g\n-h\n"), b"z\na\nb\nc\nd\ne\nf\ng\n")
        # A hunk of no context: lines put in after line 3, and lines taken out with nothing put back.
        self.assertEqual(after(OLD, b"@@ -3,0 +4,2 @@\n+x\n+y\n"), b"a\nb\nc\nx\ny\nd\ne\nf\ng\nh\n")
        self.assertEqual(after(OLD, b"@@ -2,2 +1,0 @@\n-b\n-c\n"), b"a\nd\ne\nf\ng\nh\n")
        # Lines put in after a hunk that grew the file stand by the old side's count, not the new side's.
        self.assertEqual(after(b"a\nb\nc\n", b"@@ -0,0 +1 @@\n+x\n@@ -2,0 +4 @@\n+y\n"), b"x\na\nb\ny\nc\n")
        # A file's bytes are bytes, not text: a line no hunk names is kept as it is, whatever it holds.
        self.assertEqual(after(b"a\n\xff\xfe\n", b"@@ -1 +1 @@\n-a\n+A\n"), b"A\n\xff\xfe\n")
        # An empty line is a line like another: one the file does not hold there is not this file's.
        self.assertIsNone(after(b"keep\n", b"@@ -1 +0,0 @@\n-\n"))
        self.assertEqual(after(b"\nkeep\n", b"@@ -1 +0,0 @@\n-\n"), b"keep\n")
        # A carriage return is a byte of its line, and stays one: at a line's end, or in the middle of it.
        self.assertEqual(after(b"a\r\nb\r\n", b"@@ -1,2 +1,2 @@\n-a\r\n+A\r\n b\r\n"), b"A\r\nb\r\n")
        self.assertEqual(after(b"a\rb\nc\x0cd\n", b"@@ -1 +1 @@\n-a\rb\n+A\rb\n"), b"A\rb\nc\x0cd\n")
        self.assertIsNone(after(b"a\r\nb\r\n", b"@@ -1,2 +1,2 @@\n a\n-b\r\n+B\r\n"))      # and a line without it is another line
        # No hunk at all leaves the bytes as they were, whatever their last line ends in.
        self.assertEqual([patch.content(old, []) for old in (b"keep\n", b"keep", b"", b"\n", b"a\n\n")],
                         [b"keep\n", b"keep", b"", b"\n", b"a\n\n"])
        # Nothing is searched for: lines that are the file's two lines further down are not this hunk's.
        twice = b"a\nb\nc\nd\nb\nc\nd\n"
        self.assertEqual(after(twice, b"@@ -5,2 +5,2 @@\n b\n-c\n+C\n"), b"a\nb\nc\nd\nb\nC\nd\n")
        # Lines taken from further down with nothing put back; a line put in after the file's last.
        self.assertEqual(after(twice, b"@@ -5,2 +4,0 @@\n-b\n-c\n"), b"a\nb\nc\nd\nd\n")
        self.assertEqual(after(twice, b"@@ -7,0 +8 @@\n+x\n"), twice + b"x\n")
        self.assertEqual(after(twice, b"@@ -0,0 +1 @@\n+x\n"), b"x\n" + twice)      # and one before its first
        for wrong in (b"@@ -3,2 +3,2 @@\n b\n-c\n+C\n",          # the lines of line 2, said to stand at line 3
                      b"@@ -5,2 +5,2 @@\n b\n-x\n+C\n",          # a line the file does not hold there
                      b"@@ -5,2 +5,2 @@\n b \n-c\n+C\n",         # a line with a space more
                      b"@@ -7,2 +7,2 @@\n d\n-e\n+E\n",          # a hunk past the file's end
                      b"@@ -8,0 +9 @@\n+x\n",                   # a line put in a line past the file's end
                      b"@@ -1 +1 @@\n-a\n+A\n@@ -7,2 +7,2 @@\n d\n-e\n+E\n"):     # a second hunk past it
            with self.subTest(wrong=wrong):
                self.assertIsNone(after(twice, wrong))

        # Two hunks with a line between them each stand; the first hunk may stand at the file's first line.
        apart = b"@@ -1 +1 @@\n-a\n+A\n@@ -3 +3 @@\n-c\n+C\n@@ -5 +5 @@\n-b\n+B\n"
        self.assertEqual(after(twice, apart), b"A\nb\nC\nd\nB\nc\nd\n")

    def test_the_newline_at_a_files_end_is_as_the_patch_says(self):
        marker = b"\\ No newline at end of file\n"
        bare = b"a\nb"
        cases = (
            # the last line gains its newline; loses it; is changed and keeps none; a line is added after a bare one
            (bare, b"@@ -1,2 +1,2 @@\n a\n-b\n" + marker + b"+b\n", b"a\nb\n"),
            (b"a\nb\n", b"@@ -1,2 +1,2 @@\n a\n-b\n+b\n" + marker, b"a\nb"),
            (bare, b"@@ -1,2 +1,2 @@\n a\n-b\n" + marker + b"+B\n" + marker, b"a\nB"),
            (bare, b"@@ -1,2 +1,3 @@\n a\n-b\n" + marker + b"+b\n+c\n", b"a\nb\nc\n"),
            # a bare last line left as context; a bare last line removed, so the line before it ends the file
            (bare, b"@@ -1,2 +1,2 @@\n-a\n+A\n b\n" + marker, b"A\nb"),
            (bare, b"@@ -1,2 +1 @@\n a\n-b\n" + marker, b"a\n"),
            # a hunk that begins at a bare last line: the line before it keeps its newline
            (bare, b"@@ -2 +1,0 @@\n-b\n" + marker, b"a\n"), (bare, b"@@ -2 +2 @@\n-b\n" + marker + b"+B\n", b"a\nB\n"),
            # a hunk that stops short of a bare last line leaves it bare
            (b"a\nb\nc", b"@@ -1 +1 @@\n-a\n+A\n", b"A\nb\nc"),
            # an empty file gains lines; a file loses every line and stays
            (b"", b"@@ -0,0 +1,2 @@\n+a\n+b\n", b"a\nb\n"),
            (b"a\n", b"@@ -1 +0,0 @@\n-a\n", b""),
        )
        for old, hunks, new in cases:
            with self.subTest(hunks=hunks):
                self.assertEqual(after(old, hunks), new)
        wrong = (
            (bare, b"@@ -1,2 +1,2 @@\n a\n-b\n+B\n"),                               # the bare line read as whole
            (b"a\nb\n", b"@@ -1,2 +1,2 @@\n a\n-b\n" + marker + b"+B\n"),             # a whole line read as bare
            (b"a\nb\n", b"@@ -1 +1 @@\n-a\n" + marker + b"+A\n"),                    # a line not the last read bare
            (bare, b"@@ -1 +1 @@\n-a\n" + marker + b"+A\n"),                         # the same, where the last line is bare
            (bare, b"@@ -2,0 +3 @@\n+c\n"),                                          # a line added after a bare one
            # A last line both sides hold says of its newline what the file does, as a line the old side holds must.
            (bare, b"@@ -1,2 +1,2 @@\n-a\n+A\n b\n"),
            (b"a\nb\n", b"@@ -1,2 +1,2 @@\n-a\n+A\n b\n" + marker),
            # A new line with no newline at its end is the file's last: no line of the file follows its hunk, where
            # git would join the two lines into one. (A marker in a hunk that is not the last is no patch at all.)
            (b"a\nb\n", b"@@ -1 +1 @@\n-a\n+A\n" + marker),
            (b"a\nb\nc\n", b"@@ -1,2 +1,2 @@\n-a\n+A\n b\n" + marker),
        )
        for old, hunks in wrong:
            with self.subTest(hunks=hunks):
                self.assertIsNone(after(old, hunks))
        # What is no bytes is no file's content, an empty file's least of all.
        gains = readable(section("docs/a.md", b"@@ -0,0 +1 @@\n+x\n"))[0]["hunks"]
        self.assertEqual(patch.content(b"", gains), b"x\n")
        for old in (None, "", 0, [], {}, "a\n", [b"a"]):
            self.assertIsNone(patch.content(old, gains), old)
            self.assertIsNone(patch.content(old, []), old)      # with no hunk to apply, all the same

        # Nor is a subclass of bytes, whose own methods would be read where the file's lines are asked for.
        class Said(bytes):
            def split(self, *_):
                return [b"a", b""]
        changed = readable(section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\n"))[0]["hunks"]
        self.assertEqual(patch.content(b"a\n", changed), b"A\n")
        for hunks in (changed, []):
            self.assertIsNone(patch.content(Said(b"zzz\n"), hunks))

    def test_a_patch_lands_the_bytes_it_says_and_no_others(self):
        changes, why = landed(CHANGE)
        self.assertEqual((changes, why), ({"written": {"docs/a.md": (FILE, b"a\nb\nC\nd\ne\nf\ng\nh\n")}, "removed": [],
                                           "read": []}, None))
        self.assertEqual(patch.sources(CHANGE), ["docs/a.md"])
        self.assertEqual((patch.UNREADABLE, patch.NOT_APPLIED, patch.NOT_A_FILE),
                         ("bundle_unreadable", "patch_does_not_apply", "push_not_a_file"))
        # Each file a patch changes, each by its own hunks; a carriage return is a byte of its line, and stays one.
        both = CHANGE + section("run.sh", b"@@ -1 +1,2 @@\n #!/bin/sh\r\n+exit\r\n", extended=b"index 1111111..2222222 100755\n")
        self.assertEqual(landed(both, held=dict(HELD, **{"run.sh": b"#!/bin/sh\r\n"}))[0]["written"],
                         {"docs/a.md": (FILE, b"a\nb\nC\nd\ne\nf\ng\nh\n"), "run.sh": ("100755", b"#!/bin/sh\r\nexit\r\n")})
        # Hunks that are not the file's land nothing, of this file or of any other the patch names.
        wrong = CHANGE + section("run.sh", b"@@ -1 +1 @@\n-#!/bin/bash\n+exit\n", extended=b"index 1111111..2222222 100755\n")
        self.assertEqual(landed(wrong), (None, patch.NOT_APPLIED))
        # A last line with no newline lands with none: no byte is added where git's marker stands.
        bare = (b"diff --git a/n b/n\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n+++ b/n\n"
                b"@@ -0,0 +1 @@\n+x\n\\ No newline at end of file\n")
        self.assertEqual(landed(bare), ({"written": {"n": (FILE, b"x")}, "removed": [], "read": []}, None))

    def test_a_new_a_removed_a_renamed_and_a_copied_file_are_each_what_the_patch_says(self):
        new = (b"diff --git a/docs/n.md b/docs/n.md\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n"
               b"+++ b/docs/n.md\n@@ -0,0 +1,2 @@\n+x\n+y\n")
        self.assertEqual(landed(new)[0], {"written": {"docs/n.md": (FILE, b"x\ny\n")}, "removed": [], "read": []})
        self.assertEqual(patch.sources(new), [])
        empty = b"diff --git a/docs/e b/docs/e\nnew file mode 100755\nindex 0000000..e69de29\n"
        self.assertEqual(landed(empty)[0]["written"], {"docs/e": ("100755", b"")})
        gone = (b"diff --git a/tests/t.py b/tests/t.py\ndeleted file mode 100644\nindex 1111111..0000000\n"
                b"--- a/tests/t.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
        self.assertEqual(landed(gone), ({"written": {}, "removed": ["tests/t.py"], "read": []}, None))
        moved = (b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 87%\nrename from docs/a.md\nrename to docs/b.md\n"
                 b"index 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/b.md\n@@ -1,2 +1,2 @@\n-a\n+A\n b\n")
        self.assertEqual(landed(moved)[0], {"written": {"docs/b.md": (FILE, b"A" + OLD[1:])}, "removed": ["docs/a.md"],
                                            "read": ["docs/a.md"]})
        whole = b"diff --git a/run.sh b/bin/run.sh\nsimilarity index 100%\nrename from run.sh\nrename to bin/run.sh\n"
        self.assertEqual(landed(whole), ({"written": {"bin/run.sh": ("100755", b"#!/bin/sh\n")}, "removed": ["run.sh"],
                                          "read": ["run.sh"]}, None))
        copied = b"diff --git a/docs/a.md b/docs/c.md\nsimilarity index 100%\ncopy from docs/a.md\ncopy to docs/c.md\n"
        self.assertEqual(landed(copied), ({"written": {"docs/c.md": (FILE, OLD)}, "removed": [], "read": ["docs/a.md"]}, None))
        # A section of no hunk lands the bytes that were read, themselves: a copy costs the patch no bytes anew.
        self.assertIs(landed(copied)[0]["written"]["docs/c.md"][1], OLD)
        # A copy reads the file as the admitted commit holds it, whatever another section makes of it.
        both = landed(CHANGE + copied)[0]["written"]
        self.assertEqual(patch.sources(CHANGE + copied), ["docs/a.md"])
        self.assertEqual((both["docs/a.md"][1], both["docs/c.md"][1]), (b"a\nb\nC\nd\ne\nf\ng\nh\n", OLD))
        mode = b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 100755\n"
        self.assertEqual(landed(mode)[0]["written"], {"docs/a.md": ("100755", OLD)})
        # A mode change may take the bit away as well as give it, with a hunk or without.
        plain = b"diff --git a/run.sh b/run.sh\nold mode 100755\nnew mode 100644\n"
        self.assertEqual(landed(plain)[0]["written"], {"run.sh": (FILE, b"#!/bin/sh\n")})
        edited = plain + b"index 1111111..2222222\n--- a/run.sh\n+++ b/run.sh\n@@ -1 +1 @@\n-#!/bin/sh\n+#!/bin/bash\n"
        self.assertEqual(landed(edited)[0]["written"], {"run.sh": (FILE, b"#!/bin/bash\n")})
        # Each file a rename or a copy reads is said, and each a rename takes away.
        two = (b"diff --git a/docs/a.md b/docs/c.md\nsimilarity index 100%\ncopy from docs/a.md\ncopy to docs/c.md\n"
               b"diff --git a/run.sh b/r2\nsimilarity index 100%\ncopy from run.sh\ncopy to r2\n")
        self.assertEqual(landed(two)[0]["read"], ["docs/a.md", "run.sh"])
        moves = landed(two.replace(b"copy ", b"rename "))[0]
        self.assertEqual((moves["read"], moves["removed"]), (["docs/a.md", "run.sh"], ["docs/a.md", "run.sh"]))
        mixed = landed(two.replace(b"copy from run.sh\ncopy to", b"rename from run.sh\nrename to"))[0]
        self.assertEqual((mixed["read"], mixed["removed"]), (["docs/a.md", "run.sh"], ["run.sh"]))
        # A copy with a hunk is the admitted commit's file with the hunk applied, and the file itself stays.
        changed = (copied.replace(b"100%", b"87%") + b"index 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/c.md\n"
                   b"@@ -1,2 +1,2 @@\n-a\n+A\n b\n")
        self.assertEqual(landed(changed)[0], {"written": {"docs/c.md": (FILE, b"A" + OLD[1:])}, "removed": [], "read": ["docs/a.md"]})
        # A rename and a copy may each change the mode, as a change does.
        runnable = b"diff --git a/docs/a.md b/docs/r\nold mode 100644\nnew mode 100755\nsimilarity index 100%\n"
        self.assertEqual(landed(runnable + b"rename from docs/a.md\nrename to docs/r\n")[0],
                         {"written": {"docs/r": ("100755", OLD)}, "removed": ["docs/a.md"], "read": ["docs/a.md"]})
        self.assertEqual(landed(runnable + b"copy from docs/a.md\ncopy to docs/r\n")[0],
                         {"written": {"docs/r": ("100755", OLD)}, "removed": [], "read": ["docs/a.md"]})
        # A copy of a runnable file is runnable. A file copied and moved in one patch is said to be read once.
        self.assertEqual(landed(b"diff --git a/run.sh b/r2\nsimilarity index 100%\ncopy from run.sh\ncopy to r2\n")[0]["written"],
                         {"r2": ("100755", b"#!/bin/sh\n")})
        self.assertEqual(landed(copied + moved)[0], {"written": {"docs/c.md": (FILE, OLD), "docs/b.md": (FILE, b"A" + OLD[1:])},
                                                     "removed": ["docs/a.md"], "read": ["docs/a.md"]})
        # A copy's mode is else the admitted commit's, whatever another section makes of the file.
        self.assertEqual(landed(mode + copied)[0]["written"], {"docs/a.md": ("100755", OLD), "docs/c.md": (FILE, OLD)})

    def test_a_file_is_written_once_and_only_where_the_patch_says_it_stands(self):
        new = (b"diff --git a/%s b/%s\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n+++ b/%s\n"
               b"@@ -0,0 +1 @@\n+x\n")
        gone = (b"diff --git a/tests/t.py b/tests/t.py\ndeleted file mode 100644\nindex 1111111..0000000\n"
                b"--- a/tests/t.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
        moved = b"diff --git a/docs/a.md b/%s\nsimilarity index 100%%\nrename from docs/a.md\nrename to %s\n"
        copied = b"diff --git a/docs/a.md b/%s\nsimilarity index 100%%\ncopy from docs/a.md\ncopy to %s\n"
        not_applied = (
            new % ((b"docs/a.md",) * 3),                                       # a new file where the tree holds one
            section("docs/none.md", b"@@ -1 +1 @@\n-a\n+b\n"),                 # a change to a file the tree has not
            moved % ((b"run.sh",) * 2),                                        # a rename onto a file
            copied % ((b"run.sh",) * 2),                                       # a copy onto a file
            gone[:gone.index(b"--- ")],                                        # a removal, of no hunk, of a file that holds bytes
            gone.replace(b"deleted file mode 100644", b"deleted file mode 100755"),      # another mode than the tree's
            CHANGE.replace(b"2222222 100644", b"2222222 100755"),
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100755\nnew mode 100644\n",
            # the same of a rename: the mode its index line gives, and the mode it says the file had
            RENAMED.replace(b"2222222 100644", b"2222222 100755"),
            b"diff --git a/docs/a.md b/docs/b.md\nold mode 100755\nnew mode 100644\nsimilarity index 100%\n"
            b"rename from docs/a.md\nrename to docs/b.md\n",
            b"diff --git a/docs/a.md b/docs/c.md\nold mode 100755\nnew mode 100644\nsimilarity index 100%\n"
            b"copy from docs/a.md\ncopy to docs/c.md\n",                       # and of a copy
            section("docs/a.md", b"@@ -2,3 +2,3 @@\n b\n-x\n+C\n d\n"),      # a hunk that is not the file's
            # a copy is held as a change is: the mode its index line gives, and its hunks
            (copied % ((b"docs/c.md",) * 2)).replace(b"100%", b"87%") + b"index 1111111..2222222 100755\n--- a/docs/a.md\n+++ b/docs/c.md\n@@ -1 +1 @@\n-a\n+A\n",
            (copied % ((b"docs/c.md",) * 2)).replace(b"100%", b"87%") + b"index 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/c.md\n@@ -1 +1 @@\n-x\n+A\n",
            # a rename and a copy of a file the tree has not
            moved.replace(b"docs/a.md", b"docs/none.md") % ((b"docs/b.md",) * 2),
            copied.replace(b"docs/a.md", b"docs/none.md") % ((b"docs/c.md",) * 2),
            # a new file, a rename and a copy onto a link or a submodule, which the tree holds as it holds a file
            new % ((b"link",) * 3), new % ((b"vendored",) * 3), moved % ((b"link",) * 2), moved % ((b"vendored",) * 2),
            copied % ((b"link",) * 2), copied % ((b"vendored",) * 2),
        )
        for data in not_applied:
            with self.subTest(data=data):
                self.assertEqual(landed(data), (None, patch.NOT_APPLIED))
        # A removal that leaves bytes is no removal: the tree holds more than the patch takes.
        self.assertEqual(landed(gone, held=dict(HELD, **{"tests/t.py": b"x\ny\n"})), (None, patch.NOT_APPLIED))
        # An empty file is removed with no hunk, as git writes it; one whose bytes were not handed over is not, and that
        # is a person's.
        self.assertEqual(landed(gone[:gone.index(b"--- ")], held={}), (None, patch.TREE_UNREAD))
        self.assertEqual(landed(gone[:gone.index(b"--- ")], held=dict(HELD, **{"tests/t.py": b""}))[0]["removed"], ["tests/t.py"])
        # A file removed that the tree does not hold is not the tree's, with no hunk as with one.
        self.assertEqual(landed(CHANGE + b"diff --git a/missing b/missing\ndeleted file mode 100644\nindex e69de29..0000000\n"),
                         (None, patch.NOT_APPLIED))
        # Bytes read for a name the tree does not hold are no read of the tree: a person's.
        self.assertEqual(landed(section("docs/none.md", b"@@ -1 +1 @@\n-a\n+b\n"), held={"docs/none.md": b"a\n"}),
                         (None, patch.TREE_UNREAD))
        # A file the tree holds whose bytes were not handed over, or are no bytes, is not guessed at: with hunks or
        # with none, nothing lands.
        class Said(bytes):      # nor a subclass of bytes, which would land as the file's bytes, its own methods and all
            pass
        for data in (CHANGE, moved % ((b"docs/b.md",) * 2), copied % ((b"docs/c.md",) * 2), MODE):
            for held in ({}, {"docs/a.md": OLD.decode()}, {"docs/a.md": Said(OLD)}):
                self.assertEqual(landed(data, held=held), (None, patch.TREE_UNREAD), (data, held))
        away = b"diff --git a/tests/t.py b/x\nsimilarity index 100%\nrename from tests/t.py\nrename to x\n"
        twice = (CHANGE + CHANGE, CHANGE + moved % ((b"docs/b.md",) * 2), moved % ((b"docs/b.md",) * 2) + CHANGE,
                 gone + new % ((b"tests/t.py",) * 3), new % ((b"n",) * 3) + new % ((b"n",) * 3),
                 gone + away, moved % ((b"docs/b.md",) * 2) + moved % ((b"docs/c.md",) * 2),      # a file moved once it is gone
                 copied % ((b"docs/c.md",) * 2) + copied % ((b"docs/c.md",) * 2),
                 copied % ((b"docs/c.md",) * 2) + copied % ((b"docs/d.md",) * 2),     # a file copied twice
                 copied % ((b"docs/c.md",) * 2) + b"diff --git a/run.sh b/r2\nsimilarity index 100%\ncopy from run.sh\n"
                 b"copy to r2\n" + copied % ((b"docs/d.md",) * 2),                     # and with another copy between
                 # two files moved onto one name; a new file and a copy on one name
                 moved % ((b"x",) * 2) + away, new % ((b"docs/c.md",) * 3) + copied % ((b"docs/c.md",) * 2))
        for data in twice:
            with self.subTest(data=data):
                self.assertEqual(landed(data), (None, patch.UNREADABLE))

    def test_what_is_no_file_is_never_written(self):
        new = (b"diff --git a/%s b/%s\nnew file mode %s\nindex 0000000..2222222\n--- /dev/null\n+++ b/%s\n"
               b"@@ -0,0 +1 @@\n+docs/a.md\n")
        cases = (
            EMPTY % (b"ok", b"ok") + EMPTY % (b"link/x", b"link/x"),             # each file is asked, not the first
            EMPTY % (b"link/x", b"link/x") + EMPTY % (b"ok", b"ok"),             # nor the last
            new % (b"l", b"l", b"120000", b"l"),                               # a link
            new % (b"m", b"m", b"160000", b"m"),                               # a submodule
            section("link", b"@@ -1 +1 @@\n-docs/a.md\n\\ No newline at end of file\n+run.sh\n\\ No newline at end of file\n",
                    extended=b"index 1111111..2222222 120000\n"),              # a link pointed elsewhere
            b"diff --git a/link b/link\ndeleted file mode 120000\nindex 1111111..0000000\n--- a/link\n+++ /dev/null\n"
            b"@@ -1 +0,0 @@\n-docs/a.md\n\\ No newline at end of file\n",       # a link removed
            b"diff --git a/link b/link\nold mode 100755\nnew mode 100644\n",              # a link taken for a file
            new % (b"link/x", b"link/x", b"100644", b"link/x"),                # a file under a link
            new % (b"run.sh/x", b"run.sh/x", b"100644", b"run.sh/x"),          # a file under a file
            new % (b"docs", b"docs", b"100644", b"docs"),                      # a file where a directory stands
            b"diff --git a/link b/l2\nsimilarity index 100%\nrename from link\nrename to l2\n",    # a link moved
            b"diff --git a/link b/l2\nsimilarity index 100%\ncopy from link\ncopy to l2\n",        # a link copied
            # A submodule changed, removed, moved, and written under: no bytes of one are read, and none are needed.
            section("vendored", b"@@ -1 +1 @@\n-a\n+b\n", extended=b"index 1111111..2222222 160000\n"),
            b"diff --git a/vendored b/vendored\ndeleted file mode 160000\nindex 1111111..0000000\n",
            b"diff --git a/vendored b/v2\nsimilarity index 100%\nrename from vendored\nrename to v2\n",
            b"diff --git a/vendored b/v2\nsimilarity index 100%\ncopy from vendored\ncopy to v2\n",
            new % (b"vendored/x", b"vendored/x", b"100644", b"vendored/x"),
            # A rename and a copy are held as a new file is: none lands under a file, or where a directory stands.
            b"diff --git a/docs/a.md b/run.sh/x\nsimilarity index 100%\nrename from docs/a.md\nrename to run.sh/x\n",
            b"diff --git a/docs/a.md b/docs\nsimilarity index 100%\ncopy from docs/a.md\ncopy to docs\n",
            b"diff --git a/run.sh b/tests\nsimilarity index 100%\nrename from run.sh\nrename to tests\n",
            # Nor under a file that stands further up than its own directory, or that itself stands in a directory.
            new % (b"run.sh/sub/x", b"run.sh/sub/x", b"100644", b"run.sh/sub/x"),
            b"diff --git a/docs/a.md b/link/sub/x\nsimilarity index 100%\ncopy from docs/a.md\ncopy to link/sub/x\n",
            new % (b"docs/a.md/x", b"docs/a.md/x", b"100644", b"docs/a.md/x"),
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(landed(data), (None, patch.NOT_A_FILE))
        # One file the patch makes under another it makes, of any kind, is no patch git writes: it is not read.
        for data in (new % (b"n", b"n", b"100644", b"n") + new % (b"n/x", b"n/x", b"100644", b"n/x"),
                     new % (b"d/n/x", b"d/n/x", b"100644", b"d/n/x") + new % (b"d/n", b"d/n", b"100644", b"d/n"),
                     new % (b"l", b"l", b"120000", b"l") + new % (b"l/x", b"l/x", b"100644", b"l/x")):
            self.assertEqual(landed(data), (None, patch.UNREADABLE), data)
        # A directory that holds a link or a submodule alone is a directory all the same.
        for tree in ({"d/l": "120000"}, {"d/sub": "160000"}):
            self.assertEqual(landed(new % (b"d", b"d", b"100644", b"d"), tree=tree, held={}), (None, patch.NOT_A_FILE), tree)
        # A directory is one at any depth: where the tree holds `a/b/c`, neither `a/b` nor `a` is a file's place.
        for name in (b"a/b", b"a"):
            self.assertEqual(landed(new % (name, name, b"100644", name), tree=dict(TREE, **{"a/b/c": FILE})),
                             (None, patch.NOT_A_FILE), name)
        # Where a file stands is asked of the tree the push leaves, as git writes it: a file removed or moved away
        # leaves its place to a directory, and a directory whose every file is removed leaves its place to a file.
        empty_gone = b"diff --git a/%s b/%s\ndeleted file mode 100644\nindex e69de29..0000000\n"
        empty_new = b"diff --git a/%s b/%s\nnew file mode 100644\nindex 0000000..e69de29\n"
        self.assertEqual(landed(empty_gone % (b"e", b"e") + empty_new % (b"e/x", b"e/x"), tree={"e": FILE}, held={"e": b""}),
                         ({"written": {"e/x": (FILE, b"")}, "removed": ["e"], "read": []}, None))
        self.assertEqual(landed(empty_new % (b"d", b"d") + empty_gone % (b"d/x", b"d/x"), tree={"d/x": FILE}, held={"d/x": b""}),
                         ({"written": {"d": (FILE, b"")}, "removed": ["d/x"], "read": []}, None))
        away = b"diff --git a/run.sh b/r\nsimilarity index 100%\nrename from run.sh\nrename to r\n"
        self.assertEqual(landed(away + empty_new % (b"run.sh/x", b"run.sh/x"))[0]["written"],
                         {"r": ("100755", b"#!/bin/sh\n"), "run.sh/x": (FILE, b"")})
        into = b"diff --git a/run.sh b/run.sh/x\nsimilarity index 100%\nrename from run.sh\nrename to run.sh/x\n"
        self.assertEqual(landed(into)[0], {"written": {"run.sh/x": ("100755", b"#!/bin/sh\n")}, "removed": ["run.sh"],
                                           "read": ["run.sh"]})      # and a file moved under its own old name
        # Each file removed leaves its place, not the first or the last alone.
        for first, second in ((b"e", b"f"), (b"f", b"e")):
            data = empty_gone % (first, first) + empty_gone % (second, second) + empty_new % (b"f/x", b"f/x")
            self.assertEqual(landed(data, tree={"e": FILE, "f": FILE}, held={"e": b"", "f": b""})[0]["written"],
                             {"f/x": (FILE, b"")}, data)
        # A directory that keeps one file, or a file that stays, is still in the way.
        for data, tree, held in ((empty_new % (b"d", b"d") + empty_gone % (b"d/x", b"d/x"), {"d/x": FILE, "d/y": FILE},
                                  {"d/x": b""}),
                                 (empty_gone % (b"e", b"e") + empty_new % (b"f/x", b"f/x"), {"e": FILE, "f": FILE}, {"e": b""})):
            self.assertEqual(landed(data, tree=tree, held=held), (None, patch.NOT_A_FILE), data)

    def test_no_file_lands_beside_another_that_differs_by_case_alone(self):
        # Where case is not told apart, git checks out two paths that differ by case alone as one: the second lands
        # over the first. So no file is written where it, or a directory above it, is another path the push leaves
        # in another case: a file, a directory, or a file the same patch writes.
        for name in (b"TESTS/t.py", b"Docs/A.md", b"DOCS", b"docs/A.md", b"Run.sh", b"tests/T.PY"):
            self.assertEqual(landed(EMPTY % (name, name)), (None, patch.PATH_TWIN), name)
        self.assertEqual(landed(EMPTY % (b"n", b"n") + EMPTY % (b"N", b"N")), (None, patch.PATH_TWIN))
        self.assertEqual(landed(EMPTY % (b"d/n", b"d/n") + EMPTY % (b"D/m", b"D/m")), (None, patch.PATH_TWIN))
        # A directory at any depth above the file is asked, not the top one or the nearest alone.
        self.assertEqual(landed(EMPTY % (b"Docs/b/x", b"Docs/b/x"), tree={"docs/a.md": FILE}, held={}), (None, patch.PATH_TWIN))
        self.assertEqual(landed(EMPTY % (b"docs/X/n", b"docs/X/n"), tree={"docs/x/m": FILE}, held={}), (None, patch.PATH_TWIN))
        moved = b"diff --git a/%s b/%s\nsimilarity index 100%%\nrename from %s\nrename to %s\n"
        copied = b"diff --git a/%s b/%s\nsimilarity index 100%%\ncopy from %s\ncopy to %s\n"
        self.assertEqual(landed(copied % ((b"docs/a.md", b"docs/A.md") * 2)), (None, patch.PATH_TWIN))
        # A name in another canonical form is the same name: U+037E is a semicolon, U+1FEF a grave accent.
        for name, other in ((b"a;", "a\u037e"), (b"x`", "x\u1fef"), (b"l;/x", "l\u037e"), (b"a;;", "a\u037e\u037e"),
                            (b"x``", "x\u1fef\u1fef")):
            self.assertEqual(landed(EMPTY % (name, name), tree={other: FILE}, held={}), (None, patch.PATH_TWIN), other)
        # A character macOS passes over is dropped from either name: U+200C in the tree's, in a file's or a directory's.
        for other in ("a\u200c.py", "A.py\ufe0f", "\u00ada.py", "a.py\U000e0001", "a.\U000e0fffpy"):
            self.assertEqual(landed(EMPTY % (b"a.py", b"a.py"), tree={other: FILE}, held={}), (None, patch.PATH_TWIN), other)
        self.assertEqual(landed(EMPTY % (b"d/y", b"d/y"), tree={"d\u200d/x": FILE}, held={}), (None, patch.PATH_TWIN))
        for other in ("a\u200c\u200c.py", "a\u200c.p\u200dy", "\u00ad\ufe0fa.py\U000e0001"):
            self.assertEqual(landed(EMPTY % (b"a.py", b"a.py"), tree={other: FILE}, held={}), (None, patch.PATH_TWIN), other)
        # One alone is no twin: a tree that holds such a name takes a push beside it.
        self.assertEqual(landed(EMPTY % (b"a.py", b"a.py"), tree={"\u2764\ufe0f.md": FILE, "a\u200a.py": FILE}, held={})[0]["written"],
                         {"a.py": (FILE, b"")})
        # Each file written is asked, the first and the last alike.
        for data in (EMPTY % (b"Docs/n", b"Docs/n") + EMPTY % (b"ok", b"ok"), EMPTY % (b"ok", b"ok") + EMPTY % (b"Docs/n", b"Docs/n")):
            self.assertEqual(landed(data), (None, patch.PATH_TWIN), data)
        # A directory between is folded as a file is.
        self.assertEqual(landed(EMPTY % (b"r/p;/two/new", b"r/p;/two/new"), tree={"r/p\u037e/one/old": FILE}, held={}),
                         (None, patch.PATH_TWIN))
        # A file changed or moved in beside a twin that stays is refused as a new one is.
        self.assertEqual(landed(MODE, tree={"docs/a.md": FILE, "docs/A.md": FILE}, held={"docs/a.md": OLD}),
                         (None, patch.PATH_TWIN))
        self.assertEqual(landed(moved % ((b"run.sh", b"docs/A.md") * 2)), (None, patch.PATH_TWIN))
        # A file renamed to its own name in another case leaves its old name, and lands; so does a file whose name
        # differs from no other's, beside two the tree already holds in two cases that the patch does not touch.
        self.assertEqual(landed(moved % ((b"docs/a.md", b"docs/A.md") * 2))[0]["written"], {"docs/A.md": (FILE, OLD)})
        self.assertEqual(landed(moved % ((b"docs/a.md", b"Docs/a.md") * 2))[0]["written"], {"Docs/a.md": (FILE, OLD)})
        self.assertEqual(landed(EMPTY % (b"n", b"n"), tree=dict(TREE, **{"x": FILE, "X": FILE}))[0]["written"],
                         {"n": (FILE, b"")})
        self.assertEqual(landed(EMPTY % (b"docs/n", b"docs/n"))[0]["written"], {"docs/n": (FILE, b"")})
        # The code is its own, by its letters, and no other's.
        self.assertEqual(patch.PATH_TWIN, "push_path_collision")
        self.assertNotIn(patch.PATH_TWIN, (patch.UNREADABLE, patch.NOT_APPLIED, patch.NOT_A_FILE))


    def test_what_a_port_did_not_read_is_refused_under_its_own_code(self):
        # A tree or contents in no shape a port gives is a person's, whatever the patch is: a path is text.
        for tree, held in ((None, HELD), (TREE, None), ([], HELD), (TREE, []), ({**TREE, b"f": FILE}, HELD),
                           ({**TREE, None: FILE}, HELD), ({1: FILE}, HELD), ({**TREE, "unread": None}, HELD),
                           ({**TREE, "lone": "040000"}, HELD), ({**TREE, "n": 100644}, HELD), ({**TREE, "n": b"100644"}, HELD),
                           # a tree that holds a file where it holds a directory; contents whose path is no text, or
                           # that are no bytes, though the patch reads none of them
                           ({**TREE, "run.sh/x": FILE}, HELD), ({**TREE, "docs/a.md/x/y": FILE}, HELD),
                           ({**TREE, "link/x": FILE}, HELD), ({**TREE, "vendored/x": FILE}, HELD),     # or a link, or a submodule
                           # a path git holds in no tree: an empty one, one with an empty part, one with a NUL
                           ({**TREE, "": FILE}, HELD), ({**TREE, "docs//x": FILE}, HELD), ({**TREE, "x/": FILE}, HELD),
                           ({**TREE, "a\x00b": FILE}, HELD),
                           # and a pair in no shape stands anywhere, the first as well as the last
                           ({b"f": FILE, **TREE}, HELD), ({"lone": "040000", **TREE}, HELD), ({1: FILE, **TREE}, HELD),
                           (TREE, {b"other": b"", **HELD}), (TREE, {"tests/t.py": None, "docs/a.md": OLD}),
                           ({"/".join(["d"] * 33): FILE, **TREE}, HELD), ({"docs/./x": FILE, **TREE}, HELD),
                           (TREE, {"other": b"", **HELD}),
                           # git's own directory, in any case; and bytes for a submodule, which has none to read
                           ({**TREE, "d/.git/config": FILE}, HELD), ({**TREE, ".GIT": FILE}, HELD),
                           ({**TREE, "src/.GiT/f": FILE}, HELD),
                           (TREE, {**HELD, "vendored": b"x"}), (TREE, {**HELD, "vendored": b""}),
                           # what stands under a file is in no tree, whatever it is; nor is a surrogate alone
                           ({**TREE, "run.sh/sub": "160000"}, HELD), ({**TREE, "run.sh/l": "120000"}, HELD),
                           ({**TREE, "bad\ud800": FILE}, HELD), ({**TREE, "bad\udfff/x": FILE}, HELD),
                           # nor a `.` or `..` part, which would name another path: docs/./a.md is docs/a.md
                           ({**TREE, "docs/./x": FILE}, HELD), ({**TREE, "docs/../x": FILE}, HELD),
                           ({**TREE, "./x": FILE}, HELD), ({**TREE, "x/..": FILE}, HELD), ({**TREE, ".": FILE}, HELD),
                           (TREE, {**HELD, b"other": b""}), (TREE, {**HELD, "tests/t.py": None}),
                           (TREE, {**HELD, "tests/t.py": "text"})):
            self.assertEqual(patch.applied(CHANGE, tree, held), (None, patch.TREE_UNREAD))
            self.assertEqual(patch.applied(b"no patch\n", tree, held), (None, patch.TREE_UNREAD))
        # Each is of its type exactly: a subclass of dict, str or bytes would be read by its own methods.
        class Map(dict):
            pass

        class Text(str):
            pass

        class Said(bytes):
            pass
        for tree, held in ((Map(TREE), HELD), (TREE, Map(HELD)), ({**TREE, Text("n"): FILE}, HELD),
                           ({**TREE, "n": Text(FILE)}, HELD), (TREE, {"docs/a.md": OLD, Text("run.sh"): b""}),
                           (TREE, {**HELD, "run.sh": Said(b"")})):
            self.assertEqual(patch.applied(CHANGE, tree, held), (None, patch.TREE_UNREAD), (tree, held))
        # A path of more parts than DEEPEST has characters is in no tree a port gives; one of as many parts is.
        # A path whose part holds .git but is not it is a name; a link's bytes may be handed over.
        self.assertIsNone(patch.applied(CHANGE, {**TREE, ".github/x": FILE, "x.git": FILE, "git~1/x": FILE, ".git.": FILE}, HELD)[1])
        # Refusing reads no key that is not plain text, so no method of one is called: not its hash, nor its equality.
        class Counted(str):
            calls = []

            def __hash__(self):
                Counted.calls.append("hash")
                return str.__hash__(self)

            def __eq__(self, other):
                Counted.calls.append("eq")
                return str.__eq__(self, other)
        for tree, held in (({**TREE, Counted("n"): FILE}, HELD), (TREE, {**HELD, Counted("n"): b""}),
                           ({"d/x": FILE, Counted("d"): FILE}, {})):
            del Counted.calls[:]
            self.assertEqual(patch.applied(CHANGE, tree, held), (None, patch.TREE_UNREAD))
            self.assertEqual(Counted.calls, [])
        # A character either side of the surrogates is a character of a name.
        self.assertIsNone(patch.applied(CHANGE, {**TREE, "a\ud7ff": FILE, "b\ue000": FILE}, HELD)[1])
        # A part that begins or ends with dots is a name all the same.
        self.assertIsNone(patch.applied(CHANGE, {**TREE, ".x/...": FILE, "..y": FILE}, HELD)[1])
        deepest = "/".join(["d"] * len(patch.DEEPEST))
        self.assertEqual(patch.applied(CHANGE, {**TREE, deepest + "/e": FILE}, HELD), (None, patch.TREE_UNREAD))
        self.assertIsNone(patch.applied(CHANGE, {**TREE, deepest: FILE}, HELD)[1])
        # A mode git does not write, a file listed before the file above it, an absolute path, and bytes for a name
        # the tree does not hold are in no shape a port gives either.
        for tree, held in (({**TREE, "other": "100600"}, HELD), ({**TREE, "z/child": FILE, "z": FILE}, HELD),
                           ({**TREE, "/x": FILE}, HELD), (TREE, {**HELD, "other": b""})):
            self.assertEqual(patch.applied(CHANGE, tree, held), (None, patch.TREE_UNREAD), (tree, held))
        # Missing bytes are a person's before any fault of the Role's, in whatever section either stands: beside
        # an old mode that is not the tree's, and after a section whose index mode is not.
        wrong = CHANGE.replace(b"2222222 100644", b"2222222 100755")
        self.assertEqual(landed(b"diff --git a/docs/a.md b/docs/a.md\nold mode 100755\nnew mode 100644\n", held={}),
                         (None, patch.TREE_UNREAD))
        self.assertEqual(landed(wrong + GONE, held={"docs/a.md": OLD}), (None, patch.TREE_UNREAD))
        self.assertEqual(landed(CHANGE + GONE, held={"tests/t.py": b"x\n"}), (None, patch.TREE_UNREAD))
        plain = b"diff --git a/run.sh b/run.sh\nold mode 100755\nnew mode 100644\n"     # a runnable file's bytes too
        self.assertEqual(landed(plain, held={}), (None, patch.TREE_UNREAD))
        self.assertEqual(landed(wrong + GONE + EMPTY % (b"n", b"n"), held={"docs/a.md": OLD}), (None, patch.TREE_UNREAD))
        self.assertEqual(landed(wrong + GONE), (None, patch.NOT_APPLIED))
        # A new file reads nothing, and a new file where the tree holds one is the Role's, read or not.
        self.assertEqual(landed(EMPTY % (b"docs/a.md", b"docs/a.md"), held={}), (None, patch.NOT_APPLIED))
        # So is a file the tree holds whose bytes were not handed over, or are no bytes: with hunks or with none, it is
        # not guessed at. What is no patch is the Role's all the same, and so is a file the tree does not hold.
        moved = b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 100%\nrename from docs/a.md\nrename to docs/b.md\n"
        for data in (CHANGE, moved, COPIED, MODE):
            for held in ({}, {"docs/a.md": OLD.decode()}, {"docs/a.md": None}):
                self.assertEqual(landed(data, held=held), (None, patch.TREE_UNREAD), (data, held))
        # Missing bytes are a person's whatever else the section says: beside a mode that is not the tree's too.
        self.assertEqual(landed(CHANGE.replace(b"2222222 100644", b"2222222 100755"), held={}), (None, patch.TREE_UNREAD))
        # A person's code is its own, by its letters, and none of the Role's.
        self.assertEqual(patch.TREE_UNREAD, "push_tree_unreadable")
        self.assertNotIn(patch.TREE_UNREAD, (patch.UNREADABLE, patch.NOT_APPLIED, patch.NOT_A_FILE, patch.PATH_TWIN))
        for data in (GONE, GONE[:GONE.index(b"--- ")]):      # a file removed, by its hunk or with none
            self.assertEqual(landed(data, held={}), (None, patch.TREE_UNREAD), data)
        self.assertEqual(landed(b"no patch\n", held={}), (None, patch.UNREADABLE))
        self.assertEqual(landed(section("docs/none.md", b"@@ -1 +1 @@\n-a\n+b\n"), held={}), (None, patch.NOT_APPLIED))
        # A link and a submodule are refused before any bytes of one are asked for.
        for name, mode in (("link", b"120000"), ("vendored", b"160000")):
            hunks, extended = b"@@ -1 +1 @@\n-a\n+b\n", b"index 1111111..2222222 %s\n" % mode
            self.assertEqual(landed(section(name, hunks, extended=extended), held={}), (None, patch.NOT_A_FILE), name)

    def test_a_name_is_folded_as_macos_folds_it_wherever_that_is_ascii(self):
        # Every character, against the real fold: where either fold is ASCII, the two are the same. A name's fold is
        # its characters' folds, so this holds for every name of NAME_CHARS and every name it is compared with. Both
        # sides drop the characters IGNORABLE holds; that table is held apart, below.
        def dropped(name):
            return "".join(c for c in name if not any(first <= c <= last for first, last in patch.IGNORABLE))

        for point in range(0x110000):
            if 0xD800 <= point <= 0xDFFF:
                continue
            said = chr(point)
            real = dropped(unicodedata.normalize("NFD", unicodedata.normalize("NFD", said).casefold()))
            if real.isascii() or patch._folded(said).isascii():
                self.assertEqual(patch._folded(said), real, hex(point))
        self.assertEqual(patch._folded("Docs/A\u037e\u1fefK\u212a"), "docs/a;`kk")
        # IGNORABLE is Unicode 13.0's Default_Ignorable_Code_Point, written out (perl 5.34's \p{DICP}): each range's
        # two ends are dropped, and the characters just outside them kept.
        table = [(0xAD, 0xAD), (0x34F, 0x34F), (0x61C, 0x61C), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180E),
                 (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
                 (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF)]
        self.assertEqual([(ord(first), ord(last)) for first, last in patch.IGNORABLE], table)
        for first, last in table:
            for point in (first, last):
                self.assertEqual(patch._folded("a" + chr(point) + "b"), "ab", hex(point))
            for point in (first - 1, last + 1):
                self.assertEqual(len(patch._folded("a" + chr(point) + "b")), 3, hex(point))

    def test_a_patch_as_git_writes_it_lands_what_git_would(self):
        # Against git itself, on fixed seeds, under no configuration, attributes or ignore rules but git's own. Files
        # changed, removed, moved, copied, made runnable or plain, and added; lines that are empty, end in a carriage
        # return or begin as a patch's own lines do; last lines with and without a newline; read by `git diff` with and
        # without renames, copies and context. Then each patch is broken, at random and with aim, and what `applied`
        # still lands of it is what git lands too.
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

        def snapshot(tree):
            # What git's index holds, each blob's bytes read from git itself, never from a checkout a filter may change.
            listed = [entry.split(b"\t") for entry in run(tree, "ls-files", "-s", "-z").stdout.split(b"\0") if entry]
            return {name.decode(): (meta.split()[0].decode(), run(tree, "cat-file", "blob", meta.split()[1].decode()).stdout)
                    for meta, name in listed}

        def both(tree, first, wrong):
            # What each of git's two ways lands of `wrong` on the tree `first`: the files, or what git said in refusing.
            out = []
            for way in (("--unidiff-zero",), ()):
                run(tree, "read-tree", first)
                applied = run(tree, "apply", "--cached", *way, "-", data=wrong, check=False)
                if applied.returncode:
                    out.append(applied.stderr)
                else:
                    out.append(snapshot(tree))
            return out

        def parted(data):
            # Whether a patch holds the shape in which git's two ways part: removals alone, to a last line with no newline.
            return any(not hunk["new_count"] and hunk["lines"][-1]["bare"] for said in patch.read(data) for hunk in said["hunks"])

        def side(first, count):
            # One side of a hunk's header, for the side's first line: git names the line before where it holds none.
            return b"%d,0" % (first - 1) if not count else b"%d" % first if count == 1 else b"%d,%d" % (first, count)

        def halves(rng, hunk):
            # The hunk as two that touch, each side's lines counted anew: to git, the same change.
            old, new = ([int(n) for n in (part + b",1").split(b",")[:2]] for part in hunk[0][4:hunk[0].index(b" @@", 2)].split(b" +"))
            cuts = [k for k in range(2, len(hunk)) if hunk[k] != marker]
            if not cuts:
                return hunk
            cut, out = cuts[below(rng, len(cuts))], []
            firsts = [old[0] if old[1] else old[0] + 1, new[0] if new[1] else new[0] + 1]
            for part in (hunk[1:cut], hunk[cut:]):
                counts = [len([line for line in part if line[:1] in (b" ", sign)]) for sign in (b"-", b"+")]
                out += [b"@@ -%s +%s @@" % (side(firsts[0], counts[0]), side(firsts[1], counts[1]))] + part
                firsts = [firsts[0] + counts[0], firsts[1] + counts[1]]
            return out

        def broken(rng, data):
            said = data.split(b"\n")[:-1]
            for _ in range(1 + below(rng, 2)):
                at, kind = below(rng, len(said)), below(rng, 10)
                headers = [i for i, line in enumerate(said) if line.startswith(b"@@ -")]
                marked = [i for i, line in enumerate(said) if line == marker]
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
                elif kind in (5, 6, 7) and headers:
                    i = headers[below(rng, len(headers))]
                    j = min(k for k in range(i + 1, len(said) + 1) if k == len(said) or said[k].startswith((b"@@ -", b"diff ")))
                    if kind == 5:       # the hunk again, where it stands
                        said[j:j] = said[i:j]
                    elif kind == 6:     # a number of its header, one more or one fewer
                        digits = [k for k in range(said[i].index(b" @@", 2)) if said[i][k] in b"0123456789"]
                        k = digits[below(rng, len(digits))]
                        said[i] = said[i][:k] + b"%d" % ((said[i][k] - 48 + (1 if rng.random() < 0.5 else 9)) % 10) + said[i][k + 1:]
                    else:
                        said[i:j] = halves(rng, said[i:j])
                elif kind in (8, 9) and marked:     # git's marker at a file's end dropped, or moved a line up
                    i = marked[below(rng, len(marked))]
                    del said[i]
                    if kind == 9:
                        said.insert(i - 1, marker)
            return b"\n".join(said) + b"\n"

        kinds, copied_with_hunks, lands = set(), 0, 0
        for seed in range(24):
            rng = random.Random(seed)
            with tempfile.TemporaryDirectory() as where:
                tree = pathlib.Path(where) / "tree"
                tree.mkdir()
                run(tree, "init", "-q", "--template=" + os.devnull)
                names = ["a.py", "docs/b.md", "docs/deep/c.txt", "tests/d.py", "e", "run.sh", "one"]
                for name in names:
                    (tree / name).parent.mkdir(parents=True, exist_ok=True)
                    (tree / name).write_bytes(b"\n" if name == "one" else body(rng))
                (tree / "docs" / "long.md").write_bytes(b"".join(b"a long line, number %d\n" % n for n in range(30)))
                os.chmod(tree / "run.sh", 0o700)   # git keeps the owner's execute bit alone
                run(tree, "add", "-A")
                first, before = run(tree, "write-tree").stdout.decode().strip(), snapshot(tree)
                # A file system that keeps no mode would make every file plain, and the modes below would test nothing.
                self.assertEqual(before["run.sh"][0], "100755", "this file system keeps no executable bit")
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
                        os.chmod(tree / (name + ".moved" if 0.6 < draw < 0.7 else name), 0o600 if name == "run.sh" else 0o700)
                if rng.random() < 0.6:
                    (tree / "new").mkdir()
                    (tree / "new" / "f.py").write_bytes(body(rng))
                    if rng.random() < 0.5:
                        os.chmod(tree / "new" / "f.py", 0o700)
                if rng.random() < 0.6:
                    (tree / "twin.md").write_bytes(before["docs/long.md"][1] + b"one line more\n")
                run(tree, "add", "-A")
                flags = (("--no-renames",), ("-M",), ("-M", "-C", "--find-copies-harder"), ("-U0", "--no-renames"),
                         ("-U1", "-M"), ("-U0", "-M", "-C", "--find-copies-harder"))[below(rng, 6)]
                data, then = run(tree, "diff", "--cached", *flags, first).stdout, snapshot(tree)
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
                    self.assertEqual(got, then)
                    self.assertEqual(changes["read"], list(dict.fromkeys(s["old"] for s in sections if s["kind"] in ("rename", "copy"))))
                # The same patch, broken: most of it is then no patch of this tree. What still lands, git lands alike,
                # read in one of its two ways: with `--unidiff-zero`, which it wants for a hunk of no context, or
                # without, where that takes removals at a last line with no newline a line higher than they stand.
                # That it does only where the line above reads alike, or differs in white space at its end alone; a
                # patch of that shape with another hunk of no context neither way lands rightly (the first takes the
                # wrong line, the second refuses the other hunk). Turns of these seeds draw the removals, none with
                # such a line above, and no turn is left out; the shape is held below.
                for turn in range(40):
                    wrong = broken(rng, data)
                    need = patch.sources(wrong)
                    changes, why = patch.applied(wrong, mode_of, {name: before[name][1] for name in need or () if name in before})
                    if why is not None or wrong == data:
                        continue
                    with self.subTest(seed=seed, turn=turn, wrong=wrong):
                        lands += 1
                        got = {name: held for name, held in before.items() if name not in changes["removed"]}
                        got.update(changes["written"])
                        self.assertIn(got, both(tree, first, wrong))
        self.assertEqual(kinds, {"change", "new", "deleted", "rename", "copy"})
        # Enough broken patches still land for the comparison to say something: far fewer, and the breaking has lost its aim.
        self.assertTrue(copied_with_hunks and lands >= 30, (copied_with_hunks, lands))
        # The shape in which git's two ways part, as `git diff` itself writes it, alone and beside another hunk of no
        # context: what `applied` lands is what git's own index holds, whatever `git apply` makes of its own patch.
        for old, new in ((b"b\nb", b"b\n"), (b"x\nb\nb", b"X\nb\n"), (b"x\nb \nb", b"X\nb \n")):
            with tempfile.TemporaryDirectory() as where:
                tree = pathlib.Path(where) / "tree"
                tree.mkdir()
                run(tree, "init", "-q", "--template=" + os.devnull)
                (tree / "f").write_bytes(old)
                run(tree, "add", "-A")
                first = run(tree, "write-tree").stdout.decode().strip()
                (tree / "f").write_bytes(new)
                run(tree, "add", "-A")
                data = run(tree, "diff", "--cached", "-U0", first).stdout
                self.assertTrue(parted(data), data)
                self.assertEqual(patch.applied(data, {"f": FILE}, {"f": old})[0]["written"], {"f": (FILE, new)})


REPO = "combsmith/software-factory"
BRANCH = "factory-work/issue-838-1"
PARENT, ROOT_TREE, MADE = "a" * 40, "b" * 40, "d" * 40
NEW_A = "e" * 40
NEW_TREE, COMMITTED = "c" * 40, "f" * 40
WROTE = {"written": {"docs/a.md": (FILE, b"A\n"), "docs/n.md": ("100755", b"x\n")}, "removed": ["tests/t.py"],
         "read": []}
BLOBS = {"docs/a.md": "QQo=", "docs/n.md": "eAo="}
PUSH = {"repo": REPO, "branch": BRANCH, "parent": PARENT, "head": None, "message": "Add the notes (issue 838)",
        "changes": WROTE, "blobs": BLOBS}
MOVE = dict(PUSH, head=PARENT)
READING = dict(PUSH, changes=None, blobs=None)
NOT_PERMITTED = (None, "push_not_permitted")
GIT = "/repos/" + REPO + "/git/"
AT_BRANCH, AT_COMMIT, AT_TREE = GIT + "ref/heads/" + BRANCH, GIT + "commits/" + PARENT, GIT + "trees/" + ROOT_TREE + "?recursive=1"
BLOB_A, BLOB_T, BLOB_L, BLOB_X = "1" * 40, "2" * 40, "3" * 40, "5" * 40
# The port's listing of the admitted tree, as `adapters/push.py`'s `listed` gives it: marked whole, at the tree read.
LISTING = {"tree": {"docs/a.md": FILE, "docs/b.md": FILE, "tests/t.py": FILE, "bin/l": "120000", "vendor": "160000", "bin/x": "100755"},
           "blobs": {"docs/a.md": (BLOB_A, 2), "docs/b.md": (BLOB_A, 2), "tests/t.py": (BLOB_T, 0), "bin/l": (BLOB_L, 4), "bin/x": (BLOB_X, 9)},
           "sha": ROOT_TREE, "whole": True}
ABSENT = {"status": "404", "body": {"message": "Not Found"}}
COMMIT = {"status": "200", "body": {"sha": PARENT, "tree": {"sha": ROOT_TREE}}}


def ref(sha, branch=BRANCH):
    """The branch's read at `sha`, as GitHub answers it."""
    return {"status": "200", "body": {"ref": "refs/heads/" + branch, "object": {"sha": sha, "type": "commit"}}}


class Text(str):
    """Text of another kind, with the right characters: what `+` and `==` on it do is its own to say."""


class Unequal(str):
    """Text of another kind that equals nothing, so `in` finds no path under it."""
    def __eq__(self, other):
        return False

    __hash__ = str.__hash__


class Raising(str):
    """Text of another kind that may not be compared: a key is held to its type before any comparison reads it."""
    def __eq__(self, other):
        raise AssertionError("a key of another kind was compared")

    __hash__ = str.__hash__


class Mapping(dict):
    """A mapping of another kind, with the right keys: what `in`, `set` and `[]` on it do is its own to say."""


class Listed(list):
    """A list of another kind, with the right things in it."""


class Pair(tuple):
    """A tuple of another kind, with the right two things in it."""


class Said(bytes):
    """Bytes of another kind, with the right bytes."""


class Push(unittest.TestCase):
    def test_a_push_is_told_whole_or_begins_nothing(self):
        for told in (PUSH, MOVE, READING, dict(PUSH, branch="factory-work/issue-1-10"),
                     dict(READING, parent="0123456789abcdef" * 2 + "01234567"), dict(PUSH, repo="Comb_smith9/.github-x")):
            self.assertEqual(push.began(told)[0]["push"], told)
            self.assertIsNone(push.began(told)[1])
        self.assertEqual(push.began(PUSH), ({
            "push": PUSH, "tree": None, "before": None, "branch_read": False, "blobs_read": (), "made": {}, "new": None, "checked": False,
            "commit": None, "commit_back": False, "moved": False, "landed": False}, None))
        # A push told wrongly is the Factory's own fault in describing it, never the Role's: a person's (issue 838).
        self.assertEqual(push.NOT_PERMITTED, "push_not_permitted")
        less = {k: v for k, v in PUSH.items() if k != "message"}
        for said, told in (
                ("no push", None), ("a list", [PUSH]), ("a key more", dict(PUSH, tree=ROOT_TREE)), ("a key fewer", less),
                ("a repo of one part", dict(PUSH, repo="software-factory")), ("no repo", dict(PUSH, repo=None)),
                ("a repo of three parts", dict(PUSH, repo=REPO + "/git")), ("no owner", dict(PUSH, repo="/x")),
                ("no name", dict(PUSH, repo="combsmith/")), ("the directory above", dict(PUSH, repo="combsmith/..")),
                ("a repo with a query", dict(PUSH, repo=REPO + "?x")), ("an owner that is a dot", dict(PUSH, repo="./x")),
                ("the default branch", dict(PUSH, branch="main")), ("a tag", dict(PUSH, branch="factory/v0.1.12")),
                ("a branch that is no text", dict(PUSH, branch=None)),
                ("a work branch of no issue", dict(PUSH, branch="factory-work/issue--1")),
                ("a work branch of issue 0", dict(PUSH, branch="factory-work/issue-0-1")),
                ("a work branch never opened", dict(PUSH, branch="factory-work/issue-838")),
                ("a work branch opened no times", dict(PUSH, branch="factory-work/issue-838-")),
                ("a work branch of three numbers", dict(PUSH, branch="factory-work/issue-838-1-2")),
                ("a work branch opened 0 times", dict(PUSH, branch="factory-work/issue-838-0")),
                ("a branch under a work branch", dict(PUSH, branch=BRANCH + "/x")),
                ("a branch that only ends as one", dict(PUSH, branch="x/" + BRANCH)),
                ("a work branch of an issue that is no number", dict(PUSH, branch="factory-work/issue-x-1")),
                ("a branch as long as a work branch's head", dict(PUSH, branch="x" * len("factory-work/issue-") + "838-1")),
                ("a parent that is a list of characters", dict(PUSH, parent=list(PARENT))),
                ("a parent of a character more", dict(PUSH, parent=PARENT + "a")),
                ("a parent of a letter that is no hex digit", dict(READING, parent="g" * 40)),
                ("a parent of one letter that is no hex digit", dict(READING, parent="a" * 39 + "g")),
                ("a work branch of an issue led by 0", dict(PUSH, branch="factory-work/issue-01-1")),
                ("a work branch opened 01 times", dict(PUSH, branch="factory-work/issue-1-01")),
                ("a work branch of a digit git's own are not", dict(PUSH, branch="factory-work/issue-\u0663-1")),
                ("an owner that is the directory above", dict(PUSH, repo="../x")), ("a name that is a dot", dict(PUSH, repo="x/.")),
                ("a message in parts", dict(PUSH, message=["Add the notes"])),
                ("a parent by its short name", dict(PUSH, parent=PARENT[1:])), ("no parent", dict(PUSH, parent=None)),
                ("a parent in capitals", dict(PUSH, parent=PARENT.upper())),
                ("a parent that is a ref", dict(PUSH, parent="main")),
                ("a head that is another commit", dict(PUSH, head=MADE)), ("a head that is no commit", dict(PUSH, head="")),
                ("a message that is none", dict(PUSH, message=None)), ("an empty message", dict(PUSH, message="")),
                ("changes with no blobs", dict(PUSH, blobs=None)), ("blobs with no changes", dict(PUSH, changes=None)),
                ("a written file with no blob", dict(PUSH, blobs={"docs/a.md": "QQo="})),
                ("a blob of no written file", dict(PUSH, blobs=dict(BLOBS, x="QQo="))),
                ("a blob that is bytes", dict(PUSH, blobs=dict(BLOBS, **{"docs/a.md": b"QQo="}))),
                ("a second blob that is bytes", dict(PUSH, blobs=dict(BLOBS, **{"docs/n.md": b"eAo="}))),
                ("blobs that are a list", dict(PUSH, blobs=list(BLOBS))),
                ("a repo of another kind", dict(PUSH, repo=Text(REPO))), ("a branch of another kind", dict(PUSH, branch=Text(BRANCH))),
                ("a parent of another kind", dict(PUSH, parent=Text(PARENT))), ("a head of another kind", dict(MOVE, head=Text(PARENT))),
                ("a message of another kind", dict(PUSH, message=Text(PUSH["message"]))),
                ("a blob of another kind", dict(PUSH, blobs=dict(BLOBS, **{"docs/a.md": Text("QQo=")}))),
                ("a push of another kind", Mapping(PUSH)), ("blobs of another kind", dict(PUSH, blobs=Mapping(BLOBS))),
                ("a key of the push of another kind", {Text(key): value for key, value in PUSH.items()}),
                ("a last key of the push of another kind, never compared",
                 dict({key: value for key, value in PUSH.items() if key != "blobs"}, **{Raising("blobs"): BLOBS})),
                ("a blob's path of another kind", dict(PUSH, blobs={Text(path): text for path, text in BLOBS.items()}))):
            self.assertEqual(push.began(told), NOT_PERMITTED, said)
        # The state holds a copy: what the caller changes after the push was checked is never what it holds.
        told = {key: value for key, value in PUSH.items()}
        told["changes"] = {"written": dict(WROTE["written"]), "removed": list(WROTE["removed"]), "read": []}
        told["blobs"] = dict(BLOBS)
        state = push.began(told)[0]
        told["changes"]["written"]["guards/x.py"] = (FILE, b"")
        told["changes"]["removed"].append("x")
        told["changes"]["read"].append("x")
        told["blobs"]["guards/x.py"] = ""
        told["message"] = "Other"
        self.assertEqual(state["push"], PUSH)

    def test_a_pushs_changes_are_what_applied_gives_path_by_path(self):
        def told(**changed):
            changes = dict(WROTE, **changed)
            blobs = {path: "QQo=" for path in changes["written"]} if isinstance(changes.get("written"), dict) else {}
            return dict(PUSH, changes=changes, blobs=blobs)
        for good in (told(), told(removed=[]), told(written={}), told(read=["docs/a.md", "docs/z.md"]),
                     told(written={"a/b": (FILE, b"")}, removed=["a/c", "ab"]),
                     # A file replaced by a directory, and a directory by a file: `applied` gives both.
                     told(written={"a/b": (FILE, b"")}, removed=["a"]), told(written={"d": (FILE, b"")}, removed=["d/b"]),
                     # A rename reads the file it removes.
                     told(written={"x": (FILE, b"")}, removed=["tests/t.py"], read=["tests/t.py"])):
            self.assertIsNotNone(push.began(good)[0], good["changes"])
            self.assertIsNone(push.touched(good["changes"])[1])
            held = {path: FILE for path in good["changes"]["removed"] + good["changes"]["read"]}
            self.assertIsNone(push.existing(good["changes"], held)[1])
        wrote = WROTE["written"]
        for said, bad in (
                ("nothing written and nothing removed", told(written={}, removed=[])),
                ("a name above the repo", told(written={"../x": (FILE, b"")})),
                ("git's own directory", told(written={".git/config": (FILE, b"")})),
                ("an empty part", told(written={"tests//t.py": (FILE, b"")})),
                ("a directory's name", told(written={"a/": (FILE, b"")})),
                ("a removed name git does not write", told(removed=["tests/../x"])),
                ("a read name git does not write", told(read=["docs/a b.md"])),
                ("a read path that is no text", told(read=[None])),
                ("a second read name git does not write", told(read=["docs/a.md", "docs/a b.md"])),
                ("a path that is no text", told(written={("docs/a.md",): (FILE, b"")})),
                ("a removed path that is no text", told(removed=[["tests/t.py"]])),
                ("a file written above a file written", told(written={"a": (FILE, b""), "a/b": (FILE, b"")})),
                ("a file written two above a file written", told(written={"a": (FILE, b""), "a/b/c": (FILE, b"")})),
                ("a file written under a file written, deeper", told(written={"a/b": (FILE, b""), "a/b/c": (FILE, b"")})),
                ("a file removed above a file removed", told(written={"x": (FILE, b"")}, removed=["a", "a/b"])),
                ("a file written and removed", told(removed=["docs/a.md"])),
                ("a file removed twice", told(removed=["tests/t.py", "tests/t.py"])),
                ("a file read twice", told(read=["docs/a.md", "docs/a.md"])),
                ("a file read under a file removed", told(written={"x": (FILE, b"")}, removed=["src"], read=["src/old"])),
                ("a file removed under a file read", told(written={"x": (FILE, b"")}, removed=["src/old"], read=["src"])),
                ("a link written", told(written={"l": ("120000", b"x")})),
                ("a submodule written", told(written={"m": ("160000", b"x")})),
                ("a file of text", told(written={"docs/a.md": (FILE, "A\n")})),
                ("a second file that is a link", told(written=dict(wrote, **{"docs/n.md": ("120000", b"x")}))),
                ("a file that is a list", told(written={"docs/a.md": [FILE, b"A\n"]})),
                ("a file with a thing more", told(written={"docs/a.md": (FILE, b"A\n", NEW_A)})),
                ("a file of bytes alone", told(written={"docs/a.md": (b"A\n",)})),
                ("removed as a tuple", told(removed=("tests/t.py",))), ("read as a tuple", told(read=())),
                ("written as a list", told(written=list(wrote))),
                ("a key more", dict(PUSH, changes=dict(WROTE, kept=[]))),
                ("no read", dict(PUSH, changes={"written": wrote, "removed": []})),
                ("no changes at all", dict(PUSH, changes=[], blobs={})),
                ("changes of another kind", dict(PUSH, changes=Mapping(WROTE))),
                ("written of another kind", told(written=Mapping(wrote))),
                ("removed of another kind", told(removed=Listed(["tests/t.py"]))),
                ("read of another kind", told(read=Listed())),
                ("a file of another kind", told(written={"docs/a.md": Pair((FILE, b"A\n"))})),
                ("a file's bytes of another kind", told(written={"docs/a.md": (FILE, Said(b"A\n"))})),
                ("a file's mode of another kind", told(written={"docs/a.md": (Text(FILE), b"A\n")})),
                ("a key of the changes of another kind", dict(PUSH, changes={Text(key): value for key, value in WROTE.items()}))):
            self.assertEqual(push.began(bad), NOT_PERMITTED, said)
            self.assertEqual(push.touched(bad["changes"]), NOT_PERMITTED, said)
            self.assertEqual(push.existing(bad["changes"], {}), NOT_PERMITTED, said)

    def test_the_paths_apply_is_asked_about_are_the_paths_that_land(self):
        changes = {"written": {"docs/b.md": (FILE, b"x\n"), "docs/a.md": (FILE, b"A\n"), "tests/new.py": (FILE, b"")},
                   "removed": ["tests/t.py", "config/x.json"], "read": ["tests/t.py", "docs/a.md"]}
        self.assertEqual(push.touched(changes), ((["config/x.json", "docs/a.md", "docs/b.md", "tests/new.py", "tests/t.py"],
                                                  ["tests/t.py", "docs/a.md"]), None))
        tree = {"docs/a.md": FILE, "tests/t.py": FILE, "config/x.json": FILE, "run.sh": "100755"}
        self.assertEqual(push.existing(changes, tree), (["config/x.json", "docs/a.md", "tests/t.py"], None))
        self.assertEqual(push.existing(dict(changes, removed=[]), tree), (["docs/a.md"], None))
        self.assertEqual(push.existing(dict(changes, removed=[], read=[]), {}), ([], None))
        # A file written over, or a file removed, alone.
        for said in ({"written": {"tests/t.py": (FILE, b"x")}, "removed": [], "read": []},
                     {"written": {}, "removed": ["tests/t.py"], "read": []}):
            self.assertEqual(push.existing(said, {"tests/t.py": FILE}), (["tests/t.py"], None), said)
        self.assertEqual(push.existing(dict(changes, removed=["tests/t.py"], read=["tests/t.py"]), {"tests/t.py": FILE}),
                         (["tests/t.py"], None))
        # A file removed or read that the tree holds as no file, a directory among them, and a file written over a link
        # or a submodule the tree holds, were never `applied`'s.
        for said, tree_said in ((changes, {}), ({"written": {}, "removed": ["tests"], "read": []}, {"tests/t.py": FILE}),
                                ({"written": {"b": (FILE, b"")}, "removed": [], "read": ["a"]}, {}),
                                ({"written": {"m": (FILE, b"")}, "removed": [], "read": []}, {"m": "160000"}),
                                ({"written": {"a": (FILE, b""), "m": (FILE, b"")}, "removed": [], "read": []}, {"m": "160000"}),
                                ({"written": {"l": (FILE, b"")}, "removed": [], "read": []}, {"l": "120000"}),
                                ({"written": {}, "removed": ["l"], "read": []}, {"l": "120000"}),
                                ({"written": {"b": (FILE, b"")}, "removed": [], "read": ["l"]}, {"l": "120000"})):
            self.assertEqual(push.existing(said, tree_said), NOT_PERMITTED, (said, tree_said))
        self.assertEqual(push.existing({"written": {"r": ("100755", b"")}, "removed": ["x"], "read": ["x"]},
                                       {"r": FILE, "x": "100755"}), (["r", "x"], None))
        # A file written over an executable one is a file written over a file.
        self.assertEqual(push.existing({"written": {"r": (FILE, b"")}, "removed": [], "read": []}, {"r": "100755"}),
                         (["r"], None))
        # Changes that the tree they land on cannot hold were never `applied`'s: a file over a directory the tree keeps,
        # at any depth, or under a file it keeps. Where the push removes what stood in the way, they land.
        for wrote, tree_said in (({"tests": (FILE, b"x")}, {"tests/t.py": FILE}), ({"a/b": (FILE, b"")}, {"a": FILE}),
                                 ({"a": (FILE, b"")}, {"a/b/c": FILE}), ({"a/b/c": (FILE, b"")}, {"a": FILE}),
                                 ({"tests/unit": (FILE, b"")}, {"tests/unit/group/t.py": FILE}),
                                 ({"tests/unit/x/y": (FILE, b"")}, {"tests/unit": FILE})):
            said = {"written": wrote, "removed": [], "read": []}
            self.assertEqual(push.existing(said, tree_said), NOT_PERMITTED, tree_said)
        # A file kept still stands in the way, whatever else is removed.
        self.assertEqual(push.existing({"written": {"d": (FILE, b"")}, "removed": ["d/drop"], "read": []},
                                       {"d/drop": FILE, "d/keep": FILE}), NOT_PERMITTED)
        self.assertEqual(push.existing({"written": {"a/b": (FILE, b"")}, "removed": ["a"], "read": []}, {"a": FILE}),
                         (["a"], None))
        self.assertEqual(push.existing({"written": {"d": (FILE, b"")}, "removed": ["d/b"], "read": []},
                                       {"d/b": FILE, "e": FILE}), (["d/b"], None))
        # A tree in no shape a port gives is the port's read that this cannot take: a person's, as the patch guard's.
        for tree_said in (list(tree), None, Mapping(tree), dict(tree, **{"tests/t.py": None}), {5: FILE},
                          {Unequal("tests/t.py"): FILE}, dict(tree, **{"tests/t.py": Text(FILE)}), {"x": "040000"},
                          # A file that is a directory to another, which no tree holds, at any depth
                          dict(tree, **{"docs": FILE}), dict(tree, **{"x/y": FILE, "x/y/z/w": FILE}),
                          # and a path deeper than any name read, before it is split
                          dict(tree, **{"/".join("d" * (len(patch.DEEPEST) + 1)): FILE}), {"tests//t.py": FILE}, {"/a": FILE},
                          # and what the patch guard holds as no tree: a dotted part names another path, as does git's own
                          {"tests/./t.py": FILE}, {"dir/": FILE}, {".GIT/x": FILE}, {"tests/t.py\0": FILE},
                          {"tests/\ud800.py": FILE}, {"x": Raising(FILE)}):
            self.assertEqual(push.existing(changes, tree_said), (None, patch.TREE_UNREAD), tree_said)
        # What `applied` gave is what is asked about, as it gave it.
        got, reason = patch.applied(CHANGE + NEW + GONE + COPIED, TREE, HELD)
        self.assertIsNone(reason)
        self.assertEqual(push.touched(got), ((["docs/a.md", "docs/c.md", "docs/n.md", "tests/t.py"], ["docs/a.md"]), None))
        self.assertEqual(push.existing(got, TREE), (["docs/a.md", "tests/t.py"], None))
        self.assertIsNotNone(push.began(dict(PUSH, changes=got, blobs={path: "" for path in got["written"]}))[0])


    @staticmethod
    def read(told=PUSH, branch=None):
        """The state of `told` after its branch, as GitHub answers `branch`, its commit and its tree were read."""
        state, _ = push.began(told)
        for path, answer in ((AT_BRANCH, branch or ABSENT), (AT_COMMIT, COMMIT), (AT_TREE, LISTING)):
            state, why = push.seen(state, "GET", path, None, answer)
            assert why is None, (path, why)
        return state

    def test_a_push_reads_its_branch_commit_tree_and_files_once_each_in_order(self):
        first, _ = push.began(PUSH)
        blob = GIT + "blobs/" + BLOB_A
        self.assertEqual([push.permits(first, "GET", path, None) for path in (AT_BRANCH, AT_COMMIT, AT_TREE, blob)],
                         [True, False, False, False])
        branched, why = push.seen(first, "GET", AT_BRANCH, None, ABSENT)
        self.assertEqual(branched, dict(first, branch_read=True))
        self.assertIsNone(why)
        self.assertEqual([push.permits(branched, "GET", path, None) for path in (AT_BRANCH, GIT + "commits/" + NEW_A, AT_COMMIT)],
                         [False, False, True])
        committed, _ = push.seen(branched, "GET", AT_COMMIT, None, COMMIT)
        self.assertEqual(committed, dict(branched, tree=ROOT_TREE))
        self.assertEqual([push.permits(committed, "GET", path, None) for path in (AT_COMMIT, AT_TREE, blob, AT_TREE[:-12],
                                                                         GIT + "trees/" + NEW_A + "?recursive=1")],
                         [False, True, False, False, False])
        listed = dict(LISTING, tree=dict(LISTING["tree"]), blobs=dict(LISTING["blobs"]))
        state, why = push.seen(committed, "GET", AT_TREE, None, listed)
        self.assertEqual((state, why), (dict(committed, before=LISTING), None))
        # What the state holds is a copy: the caller's listing changed after is not what was taken.
        listed["tree"]["docs/a.md"], listed["blobs"]["x"] = "100755", (BLOB_A, 1)
        self.assertEqual(state["before"], LISTING)
        self.assertFalse(push.permits(state, "GET", AT_TREE, None))
        self.assertEqual(push.seen(committed, "GET", AT_TREE, None, None), (None, push.UNANSWERED))
        # A file's blob is read once, whatever its answer, which the port judges; a link's, a submodule's or another
        # blob is not read.
        for sha, may in ((BLOB_A, True), (BLOB_T, True), (BLOB_X, True), (BLOB_L, False), ("4" * 40, False),
                         (ROOT_TREE, False)):
            self.assertFalse(push.permits(state, "GET", GIT + "trees/" + sha, None), sha)
            self.assertEqual(push.permits(state, "GET", GIT + "blobs/" + sha, None), may, sha)
        once, _ = push.seen(state, "GET", blob, None, {"status": "200", "body": {}})
        self.assertEqual(once, dict(state, blobs_read=(BLOB_A,)))
        # A blob refused, or not answered, is a stop of its own, whoever judges the bytes given.
        for answer, why in ((None, push.UNANSWERED), ({"status": "503", "body": {}}, push.UNANSWERED),
                            ({"status": "404", "body": {}}, push.ANSWER_REFUSED), ({"status": "206", "body": {}}, push.ANSWER_REFUSED),
                            ({"status": "403", "body": {}}, push.ANSWER_REFUSED), ({"status": "401", "body": {}}, push.UNANSWERED),
                            ({"status": "429", "body": {}}, push.RATE_LIMITED)):
            self.assertEqual(push.seen(state, "GET", blob, None, answer), (None, why), answer)
        self.assertEqual([push.permits(once, "GET", GIT + "blobs/" + sha, None) for sha in (BLOB_A, BLOB_T)], [False, True])
        self.assertEqual(push.seen(once, "GET", blob, None, None), NOT_PERMITTED)
        twice, _ = push.seen(once, "GET", GIT + "blobs/" + BLOB_T, None, {"status": "200", "body": {}})
        self.assertEqual(twice["blobs_read"], (BLOB_A, BLOB_T))
        # The branch first: nothing of the commit is read before the branch is, nor once it was not as admitted.
        self.assertEqual(push.seen(first, "GET", AT_COMMIT, None, COMMIT), NOT_PERMITTED)
        self.assertEqual(self.read(MOVE, ref(PARENT))["branch_read"], True)
        self.assertEqual(self.read(READING)["before"], LISTING)
        # Nothing else leaves: a write, a body, another repo's or anything outside git's data, or a path of another kind.
        for method, path, body in (("POST", AT_BRANCH, None), ("POST", GIT + "blobs", {"content": "", "encoding": "base64"}), ("GET", AT_BRANCH, {}),
                                   ("PATCH", GIT + "refs/heads/" + BRANCH, None), ("get", AT_BRANCH, None),
                                   ("GET", "/repos/combsmith/other/git/ref/heads/" + BRANCH, None),
                                   ("GET", "/repos/combsmith/software-factorx/git/ref/heads/" + BRANCH, None),
                                   ("GET", "/repos/" + REPO + "/contents/docs/a.md", None),
                                   ("GET", AT_BRANCH + "/x", None), ("GET", GIT + "commits/" + "c" * 40, None),
                                   ("GET", GIT + "trees/" + ROOT_TREE, None), ("GET", Text(AT_BRANCH), None),
                                   (Text("GET"), AT_BRANCH, None), ("GET", GIT + "blobs/" + BLOB_A, None)):
            self.assertFalse(push.permits(first, method, path, body), (method, path))
            self.assertEqual(push.seen(first, method, path, body, ABSENT), NOT_PERMITTED, (method, path))

    def test_a_listing_the_port_did_not_mark_whole_or_read_at_another_tree_is_refused(self):
        branched, _ = push.seen(push.began(PUSH)[0], "GET", AT_BRANCH, None, ABSENT)
        committed, _ = push.seen(branched, "GET", AT_COMMIT, None, COMMIT)
        self.assertTrue(push.permits(committed, "GET", AT_TREE, None))
        unmarked = {key: value for key, value in LISTING.items() if key != "whole"}
        for said, listing in (("no mark", unmarked), ("a mark that is no True", dict(LISTING, whole=1)),
                              ("another tree's", dict(LISTING, sha=PARENT)),
                              ("GitHub's own answer", {"status": "200", "body": {"sha": ROOT_TREE, "truncated": False, "tree": []}}),
                              ("a key more", dict(LISTING, truncated=False)), ("a mapping of another kind", Mapping(LISTING)),
                              ("paths of another kind", dict(LISTING, tree=list(LISTING["tree"]))),
                              ("blobs of another kind", dict(LISTING, blobs=Mapping(LISTING["blobs"]))),
                              ("a blob of no name", dict(LISTING, blobs={"docs/a.md": (None, 2)})),
                              ("a blob of a list", dict(LISTING, blobs={"docs/a.md": [BLOB_A, 2]})),
                              ("a blob of one thing", dict(LISTING, blobs={"docs/a.md": (BLOB_A,)})),
                              ("a blob of no size", dict(LISTING, blobs={"docs/a.md": (BLOB_A, None)})),
                              ("a blob of a size below 0", dict(LISTING, blobs={"docs/a.md": (BLOB_A, -1)})),
                              ("a mode not git's", dict(LISTING, tree=dict(LISTING["tree"], **{"docs/a.md": "100600"}))),
                              ("a mode of another kind", dict(LISTING, tree=dict(LISTING["tree"], **{"docs/a.md": Text(FILE)}))),
                              ("a path of another kind", dict(LISTING, tree={Raising("docs/a.md"): FILE})),
                              ("a blob's path of another kind", dict(LISTING, blobs={5: (BLOB_A, 2)}))):
            self.assertEqual(push.seen(committed, "GET", AT_TREE, None, listing), NOT_PERMITTED, said)

    def test_each_read_says_whose_a_stop_is(self):
        self.assertEqual((push.BRANCH_MOVED, push.ANSWER_REFUSED, push.UNANSWERED, push.RATE_LIMITED),
                         ("push_branch_moved", "push_answer_refused", "push_unanswered", "push_rate_limited"))
        moved, refused, unanswered = (None, push.BRANCH_MOVED), (None, push.ANSWER_REFUSED), (None, push.UNANSWERED)
        limited = (None, push.RATE_LIMITED)
        for told, answer, why in (
                # The branch as the Decision did not admit it: someone else wrote it.
                (PUSH, ref(NEW_A), moved), (PUSH, ref(PARENT), moved), (MOVE, ABSENT, moved), (MOVE, ref(NEW_A), moved),
                # An answer the push cannot go on from: another branch's, no commit, or a refusal.
                (PUSH, ref(NEW_A, BRANCH + "x"), refused), (MOVE, ref(PARENT, "main"), refused), (MOVE, ref(None), refused), (MOVE, ref("x" * 40), refused),
                (MOVE, {"status": "200", "body": {"ref": "refs/heads/" + BRANCH, "object": PARENT}}, refused),
                (MOVE, {"status": "200", "body": [ref(PARENT)["body"]]}, refused),
                (PUSH, {"status": "422", "body": {}}, refused),
                # A well-formed ref under another status proves nothing: not the admitted head, nor someone's write.
                (MOVE, dict(ref(PARENT), status="422"), refused), (MOVE, dict(ref(NEW_A), status="422"), refused),
                # A ref to what is no commit is no head.
                (MOVE, {"status": "200", "body": dict(ref(PARENT)["body"], object={"sha": PARENT, "type": "blob"})}, refused),
                (MOVE, {"status": "404", "body": None}, moved),
                # No answer, or one read as none.
                (PUSH, None, unanswered), (MOVE, {"status": "500", "body": {}}, unanswered),
                (PUSH, {"status": "401", "body": {}}, unanswered),
                (MOVE, {"status": "403", "body": {}}, unanswered), (PUSH, {"status": "429", "body": {}}, limited), (MOVE, {"status": "599", "body": {}}, unanswered),
                # An answer in no shape `send` gives is the caller's to have checked.
                (PUSH, {"status": 404, "body": {}}, NOT_PERMITTED), (PUSH, {"status": "404"}, NOT_PERMITTED),
                (PUSH, Mapping(ABSENT), NOT_PERMITTED), (PUSH, {"status": "5oops", "body": {}}, NOT_PERMITTED),
                (PUSH, {"status": "600", "body": {}}, NOT_PERMITTED), (PUSH, {"status": "5x0", "body": {}}, NOT_PERMITTED), (PUSH, {"status": "099", "body": {}}, NOT_PERMITTED),
                (PUSH, {"status": Text("404"), "body": {}}, NOT_PERMITTED), (PUSH, {"status": "4040", "body": {}}, NOT_PERMITTED),
                # A key of the body of another kind is held before any key is looked up.
                (MOVE, {"status": "200", "body": {Raising("ref"): "refs/heads/" + BRANCH, "object": {"sha": PARENT}}}, refused),
                (MOVE, {"status": "200", "body": {"ref": "refs/heads/" + BRANCH, "object": {"type": "commit", Text("sha"): PARENT}}}, refused)):
            self.assertEqual(push.seen(push.began(told)[0], "GET", AT_BRANCH, None, answer), why, (told["head"], answer))
        first, _ = push.seen(push.began(PUSH)[0], "GET", AT_BRANCH, None, ABSENT)
        for answer, why in (({"status": "404", "body": {}}, refused), ({"status": "403", "body": {}}, refused),
                            ({"status": "401", "body": {}}, unanswered), ({"status": "429", "body": {}}, limited), ({"status": "200", "body": {"sha": NEW_A, "tree": {"sha": ROOT_TREE}}}, refused),
                            ({"status": "200", "body": {"sha": PARENT, "tree": {"sha": "x"}}}, refused),
                            ({"status": "200", "body": {"sha": PARENT, "tree": ROOT_TREE}}, refused),
                            ({"status": "200", "body": {"sha": PARENT}}, refused), ({"status": "200", "body": None}, refused),
                            ({"status": "200", "body": {"sha": Text(PARENT), "tree": {"sha": ROOT_TREE}}}, refused),
                            ({"status": "201", "body": COMMIT["body"]}, refused),
                            ({"status": "200", "body": {Raising("sha"): PARENT, "tree": {"sha": ROOT_TREE}}}, refused),
                            ({"status": "200", "body": {"sha": PARENT, "tree": {Raising("sha"): ROOT_TREE}}}, refused),
                            (None, unanswered), ({"status": "503", "body": COMMIT["body"]}, unanswered)):
            self.assertEqual(push.seen(first, "GET", AT_COMMIT, None, answer), why, answer)

    def test_a_state_in_no_shape_lets_nothing_leave(self):
        first, _ = push.began(PUSH)
        state = self.read()
        less = {key: value for key, value in first.items() if key != "landed"}
        for said, bad in (("none", None), ("a list", [first]), ("a key fewer", less),
                          ("a mapping of another kind", Mapping(first)), ("a push told wrongly", dict(state, push=dict(PUSH, message=""))),
                          ("a tree of no name", dict(first, tree="x", branch_read=True)), ("a listing before the tree", dict(first, before=LISTING)),
                          ("a listing of another tree", dict(state, tree=NEW_A)), ("a listing unmarked", dict(state, before=dict(LISTING, whole=False))),
                          ("the branch read as 1", dict(first, branch_read=1)), ("landed", dict(first, landed=True)), ("landed as 0", dict(first, landed=0)),
                          ("a blob made", dict(first, made={"docs/a.md": MADE})), ("made as a list", dict(first, made=[])), ("a tree made", dict(first, new=MADE)),
                          ("a tree before the branch", dict(first, tree=ROOT_TREE)),
                          ("moved", dict(first, moved=True)), ("checked", dict(first, checked=True)),
                          ("a commit read back", dict(first, commit_back=True)), ("a commit made", dict(first, commit=MADE)),
                          ("a blob read before the listing", dict(first, blobs_read=(BLOB_A,))),
                          ("a blob read twice", dict(state, blobs_read=(BLOB_A, BLOB_A))),
                          ("a link's blob read", dict(state, blobs_read=(BLOB_L,))),
                          ("a blob's name of another kind read", dict(state, blobs_read=(Text(BLOB_A),))),
                          ("blobs read as a list", dict(state, blobs_read=[]))):
            for path in (AT_BRANCH, AT_COMMIT, AT_TREE, GIT + "blobs/" + BLOB_A, GIT + "blobs/" + BLOB_T):
                self.assertFalse(push.permits(bad, "GET", path, None), (said, path))
                self.assertEqual(push.seen(bad, "GET", path, None, ABSENT), NOT_PERMITTED, (said, path))


    # What a push writes, once it read its branch and the admitted tree's listing: a blob of each written content, then
    # one tree of exactly the changes upon that tree.
    TREE = {"base_tree": ROOT_TREE, "tree": [{"path": "docs/a.md", "mode": FILE, "type": "blob", "sha": MADE},
                                             {"path": "docs/n.md", "mode": "100755", "type": "blob", "sha": NEW_A},
                                             {"path": "tests/t.py", "mode": FILE, "type": "blob", "sha": None}]}

    @staticmethod
    def made(state=None):
        """`state`, or `read`'s, after a blob was made of each written file, `docs/a.md`'s named `MADE`."""
        state = state or Push.read()
        for content, name in (("QQo=", MADE), ("eAo=", NEW_A)):
            state, why = push.seen(state, "POST", GIT + "blobs", {"content": content, "encoding": "base64"},
                                   {"status": "201", "body": {"sha": name}})
            assert why is None, why
        return state

    def test_nothing_is_written_before_the_branch_and_the_listing_were_read(self):
        blob = {"content": "QQo=", "encoding": "base64"}
        first, _ = push.began(PUSH)
        branched, _ = push.seen(first, "GET", AT_BRANCH, None, ABSENT)
        committed, _ = push.seen(branched, "GET", AT_COMMIT, None, COMMIT)
        for state in (first, branched, committed, self.read(READING)):
            self.assertFalse(push.permits(state, "POST", GIT + "blobs", blob))
            self.assertEqual(push.seen(state, "POST", GIT + "blobs", blob, {"status": "201", "body": {"sha": MADE}}),
                             NOT_PERMITTED)
        state = self.read()
        self.assertTrue(push.permits(state, "POST", GIT + "blobs", blob))
        self.assertFalse(push.permits(state, "PUT", GIT + "blobs", blob))
        # A state that says the listing was read but not the branch is no state `seen` gives: nothing leaves.
        self.assertFalse(push.permits(dict(state, branch_read=False), "POST", GIT + "blobs", blob))
        # Once a write began, nothing more is read.
        once, _ = push.seen(state, "POST", GIT + "blobs", blob, {"status": "201", "body": {"sha": MADE}})
        self.assertTrue(push.permits(state, "GET", GIT + "blobs/" + BLOB_A, None))
        self.assertFalse(push.permits(once, "GET", GIT + "blobs/" + BLOB_A, None))
        # A push that only removes makes no blob: once its tree is made, nothing is read either.
        gone = dict(PUSH, changes={"written": {}, "removed": ["tests/t.py"], "read": []}, blobs={})
        body = {"base_tree": ROOT_TREE, "tree": [{"path": "tests/t.py", "mode": FILE, "type": "blob", "sha": None}]}
        made, _ = push.seen(self.read(gone), "POST", GIT + "trees", body, {"status": "201", "body": {"sha": NEW_A}})
        self.assertEqual(made["new"], NEW_A)
        self.assertFalse(push.permits(made, "GET", GIT + "blobs/" + BLOB_A, None))
        # A tree made is held only once the listing was read.
        self.assertFalse(push.permits(dict(push.began(gone)[0], new=NEW_A), "GET", AT_BRANCH, None))

    def test_a_blob_is_made_once_of_each_written_content(self):
        state = self.read()
        made = self.made(state)
        self.assertEqual(made, dict(state, made={"docs/a.md": MADE, "docs/n.md": NEW_A}))
        # Each content once, and only one the push writes, as `send` would ask it.
        for body in ({"content": "QQo=", "encoding": "base64"}, {"content": "eAo=", "encoding": "base64"},
                     {"content": "Ywo=", "encoding": "base64"}):
            self.assertFalse(push.permits(made, "POST", GIT + "blobs", body), body)
        for body in ({"content": "Ywo=", "encoding": "base64"}, {"content": "QQo=", "encoding": "utf-8"}, {"content": "QQo="}, dict(content="QQo=", encoding="base64", x=1),
                     {"content": Text("QQo="), "encoding": "base64"}, {"content": "QQo=", "encoding": Text("base64")},
                     Mapping(content="QQo=", encoding="base64"), {Raising("content"): "QQo=", "encoding": "base64"}, None):
            self.assertFalse(push.permits(state, "POST", GIT + "blobs", body), body)
        # Two files of one content are one blob.
        same = dict(PUSH, changes=dict(WROTE, written={"docs/a.md": (FILE, b"A\n"), "docs/b.md": (FILE, b"A\n")}),
                    blobs={"docs/a.md": "QQo=", "docs/b.md": "QQo="})
        both, _ = push.seen(self.read(same), "POST", GIT + "blobs", {"content": "QQo=", "encoding": "base64"},
                            {"status": "201", "body": {"sha": MADE}})
        self.assertEqual(both["made"], {"docs/a.md": MADE, "docs/b.md": MADE})
        entries = [{"path": path, "mode": FILE, "type": "blob", "sha": MADE} for path in ("docs/a.md", "docs/b.md")]
        self.assertTrue(push.permits(both, "POST", GIT + "trees", {"base_tree": ROOT_TREE, "tree": entries + [
            {"path": "tests/t.py", "mode": FILE, "type": "blob", "sha": None}]}))
        # Files of one content are named by one blob in any state.
        self.assertFalse(push.permits(dict(self.read(same), made={"docs/a.md": MADE}), "POST", GIT + "blobs",
                                      {"content": "QQo=", "encoding": "base64"}))
        # A state that says it made what it did not lets nothing more leave.
        blob = {"content": "eAo=", "encoding": "base64"}
        half, _ = push.seen(state, "POST", GIT + "blobs", {"content": "QQo=", "encoding": "base64"},
                            {"status": "201", "body": {"sha": MADE}})
        self.assertTrue(push.permits(half, "POST", GIT + "blobs", blob))
        for bad in (dict(half, made={"docs/b.md": MADE}), dict(half, made={"docs/a.md": "x"}), dict(half, new=NEW_A),
                    dict(half, made=Mapping(half["made"])), dict(half, made={"docs/a.md": Text(MADE)}),
                    dict(half, before=None, tree=None)):
            self.assertFalse(push.permits(bad, "POST", GIT + "blobs", blob), bad["made"])

    def test_the_one_tree_names_exactly_the_changes_by_the_blobs_made(self):
        made = self.made()
        # Not before every blob is made.
        half, _ = push.seen(self.read(), "POST", GIT + "blobs", {"content": "QQo=", "encoding": "base64"},
                            {"status": "201", "body": {"sha": MADE}})
        self.assertFalse(push.permits(half, "POST", GIT + "trees", self.TREE))
        self.assertTrue(push.permits(made, "POST", GIT + "trees", self.TREE))
        tree, why = push.seen(made, "POST", GIT + "trees", self.TREE, {"status": "201", "body": {"sha": "c" * 40}})
        self.assertEqual((tree, why), (dict(made, new="c" * 40), None))
        self.assertFalse(push.permits(tree, "POST", GIT + "trees", self.TREE))
        entries = self.TREE["tree"]
        for said, entries_said in (
                ("an entry fewer", entries[:2]), ("an entry twice", entries + entries[:1]),
                ("a path twice in place of another", [entries[0], entries[0], entries[2]]),
                ("another path", [dict(entries[0], path="docs/b.md")] + entries[1:]),
                ("another blob", [dict(entries[0], sha=NEW_A)] + entries[1:]),
                ("another mode", [dict(entries[0], mode="100755")] + entries[1:]),
                ("a removed file of another mode", entries[:2] + [dict(entries[2], mode="100755")]),
                ("a removed file's blob", entries[:2] + [dict(entries[2], sha=MADE)]),
                ("a written file removed", [dict(entries[0], sha=None)] + entries[1:]),
                ("another file removed", entries[:2] + [dict(entries[2], path="docs/b.md")]),
                ("a mode of another kind", [dict(entries[0], mode=Raising(FILE))] + entries[1:]),
                ("another type", [dict(entries[0], type="commit")] + entries[1:]),
                ("a key more", [dict(entries[0], size=2)] + entries[1:]),
                ("an entry of another kind", [Mapping(entries[0])] + entries[1:]),
                ("a path of another kind", [dict(entries[0], path=Text("docs/a.md"))] + entries[1:]),
                ("a list of another kind", Listed(entries))):
            self.assertFalse(push.permits(made, "POST", GIT + "trees", dict(self.TREE, tree=entries_said)), said)
        for body in (dict(self.TREE, base_tree=PARENT), dict(self.TREE, x=1), Mapping(self.TREE), {"tree": entries}):
            self.assertFalse(push.permits(made, "POST", GIT + "trees", body), body)
        # Changes the admitted tree cannot hold, as `existing` reads them, write nothing: a file over a directory,
        # under a link, over a submodule, or a submodule removed.
        for written, removed in (({"docs": (FILE, b"A\n")}, []), ({"bin/l/y": (FILE, b"A\n")}, []),
                                 ({"vendor": (FILE, b"A\n")}, []), ({"x": (FILE, b"A\n")}, ["vendor"])):
            told = dict(PUSH, changes={"written": written, "removed": removed, "read": []},
                        blobs={path: "QQo=" for path in written})
            state = self.read(told)
            self.assertFalse(push.permits(state, "POST", GIT + "blobs", {"content": "QQo=", "encoding": "base64"}), written)
            held = dict(state, made={path: MADE for path in written})
            body = {"base_tree": ROOT_TREE, "tree": [{"path": path, "mode": FILE, "type": "blob", "sha": MADE} for path in written]
                    + [{"path": path, "mode": LISTING["tree"][path], "type": "blob", "sha": None} for path in removed]}
            self.assertFalse(push.permits(held, "POST", GIT + "trees", body), written)
        # A removed file the listing does not hold was never `applied`'s to remove.
        gone = self.read(dict(PUSH, changes=dict(WROTE, removed=["tests/u.py"])))
        self.assertFalse(push.permits(gone, "POST", GIT + "blobs", {"content": "QQo=", "encoding": "base64"}))
        self.assertFalse(push.permits(dict(gone, made=made["made"]), "POST", GIT + "trees",
                                      dict(self.TREE, tree=entries[:2] + [dict(entries[2], path="tests/u.py")])))
        # Nor to another repo's git data, nor one name for two contents.
        self.assertFalse(push.permits(made, "POST", "/repos/combsmith/software-factorx/git/trees", self.TREE))
        two = dict(made, made={"docs/a.md": MADE, "docs/n.md": MADE})
        self.assertFalse(push.permits(two, "POST", GIT + "trees", dict(self.TREE, tree=[entries[0], dict(entries[1], sha=MADE), entries[2]])))

    def test_each_write_says_whose_a_stop_is(self):
        state, blob = self.read(), {"content": "QQo=", "encoding": "base64"}
        made = self.made(state)
        for answer, why in (
                # GitHub refused the write, or answered with what was not made.
                ({"status": "422", "body": {}}, push.ANSWER_REFUSED), ({"status": "403", "body": {}}, push.ANSWER_REFUSED),
                # A token expired is the port's; GitHub's limit on it, a code of its own.
                ({"status": "401", "body": {}}, push.UNANSWERED), ({"status": "429", "body": {}}, push.RATE_LIMITED),
                ({"status": "200", "body": {"sha": MADE}}, push.ANSWER_REFUSED),
                ({"status": "201", "body": {"sha": "x"}}, push.ANSWER_REFUSED), ({"status": "201", "body": None}, push.ANSWER_REFUSED),
                ({"status": "201", "body": {"sha": Text(MADE)}}, push.ANSWER_REFUSED),
                ({"status": "201", "body": {Raising("sha"): MADE}}, push.ANSWER_REFUSED),
                # No answer, or GitHub's own failure.
                (None, push.UNANSWERED), ({"status": "502", "body": {}}, push.UNANSWERED),
                # An answer in no shape `send` gives.
                ({"status": 201, "body": {"sha": MADE}}, push.NOT_PERMITTED), ({"status": "201"}, push.NOT_PERMITTED)):
            self.assertEqual(push.seen(state, "POST", GIT + "blobs", blob, answer), (None, why), answer)
            self.assertEqual(push.seen(made, "POST", GIT + "trees", self.TREE, answer), (None, why), answer)
        # A blob named as another content's was not made of these bytes.
        half, _ = push.seen(state, "POST", GIT + "blobs", blob, {"status": "201", "body": {"sha": MADE}})
        self.assertEqual(push.seen(half, "POST", GIT + "blobs", {"content": "eAo=", "encoding": "base64"},
                                   {"status": "201", "body": {"sha": MADE}}), (None, push.ANSWER_REFUSED))
        # A tree named as a blob made is not the tree; one that is the admitted one made nothing of the changes.
        self.assertEqual(push.seen(made, "POST", GIT + "trees", self.TREE, {"status": "201", "body": {"sha": MADE}}),
                         (None, push.ANSWER_REFUSED))
        self.assertEqual(push.seen(made, "POST", GIT + "trees", self.TREE, {"status": "201", "body": {"sha": ROOT_TREE}}),
                         (None, push.ANSWER_REFUSED))


    # What a push writes past its tree, and reads back: the tree made, one commit of it, the branch written once at
    # that commit, and the branch read again.
    AFTER = {"tree": {"docs/a.md": FILE, "docs/b.md": FILE, "docs/n.md": "100755", "bin/l": "120000", "vendor": "160000",
                      "bin/x": "100755"},
             "blobs": {"docs/a.md": (MADE, 2), "docs/b.md": (BLOB_A, 2), "docs/n.md": (NEW_A, 2), "bin/l": (BLOB_L, 4),
                       "bin/x": (BLOB_X, 9)}, "sha": NEW_TREE, "whole": True}
    BACK = {"status": "200", "body": {"sha": COMMITTED, "message": PUSH["message"], "tree": {"sha": NEW_TREE},
                                      "parents": [{"sha": PARENT}]}}

    def landing(self, told=PUSH):
        """Each request of `told` from its tree on, in order, with the answer under which it goes on."""
        write = (("PATCH", GIT + "refs/heads/" + BRANCH, {"sha": COMMITTED, "force": False}, ref(COMMITTED))
                 if told["head"] else
                 ("POST", GIT + "refs", {"ref": "refs/heads/" + BRANCH, "sha": COMMITTED}, dict(ref(COMMITTED), status="201")))
        return [("POST", GIT + "trees", self.TREE, {"status": "201", "body": {"sha": NEW_TREE}}),
                ("GET", GIT + "trees/" + NEW_TREE + "?recursive=1", None, self.AFTER),
                ("POST", GIT + "commits", {"message": told["message"], "tree": NEW_TREE, "parents": [PARENT]},
                 {"status": "201", "body": {"sha": COMMITTED}}),
                ("GET", GIT + "commits/" + COMMITTED, None, self.BACK), write, ("GET", AT_BRANCH, None, ref(COMMITTED))]

    def upto(self, told, steps):
        """The state of `told` once its blobs were made and the first `steps` of `landing` went on."""
        state = self.made(self.read(told, ref(PARENT) if told["head"] else None))
        for method, path, body, answer in self.landing(told)[:steps]:
            state, why = push.seen(state, method, path, body, answer)
            assert why is None, (path, why)
        return state

    def test_a_push_lands_its_commit_and_branch_read_back(self):
        for told in (PUSH, MOVE):
            state, landing = self.upto(told, 0), self.landing(told)
            for at, (method, path, body, answer) in enumerate(landing):
                # Each request leaves in its turn alone, and once.
                for later in landing[at + 1:]:
                    self.assertFalse(push.permits(state, *later[:3]), (at, later[:2]))
                self.assertTrue(push.permits(state, method, path, body), (at, path))
                state, why = push.seen(state, method, path, body, answer)
                self.assertIsNone(why, (at, path))
                self.assertFalse(push.permits(state, method, path, body), (at, path))
            self.assertEqual([state[key] for key in ("new", "checked", "commit", "commit_back", "moved", "landed")],
                             [NEW_TREE, True, COMMITTED, True, True, True])
            for method, path, body, _ in landing[:1] + self.landing(MOVE if told is PUSH else PUSH)[4:5]:
                self.assertFalse(push.permits(state, method, path, body), path)
        # The commit is of the tree made, on the admitted commit, with the push's message, and nothing else.
        checked, commit = self.upto(PUSH, 2), self.landing()[2][2]
        for body in (dict(commit, message="Other"), dict(commit, tree=ROOT_TREE), dict(commit, parents=[PARENT, NEW_A]),
                     dict(commit, parents=[NEW_A]), dict(commit, parents=(PARENT,)), dict(commit, message=Text(commit["message"])),
                     dict(commit, parents=[Text(PARENT)]), dict(commit, x=1), Mapping(commit)):
            self.assertFalse(push.permits(checked, "POST", GIT + "commits", body), body)
        # The branch is made where none was admitted and moved where one was, at the commit read back, never by force.
        made, moving = self.upto(PUSH, 4), self.upto(MOVE, 4)
        for state, method, path, body in (
                (made, "POST", GIT + "refs", {"ref": "refs/heads/" + BRANCH, "sha": NEW_A}),
                (made, "POST", GIT + "refs", {"ref": "refs/heads/main", "sha": COMMITTED}),
                (made, "POST", GIT + "refs", {"ref": Text("refs/heads/" + BRANCH), "sha": COMMITTED}),
                (moving, "PATCH", GIT + "refs/heads/" + BRANCH, {"sha": COMMITTED, "force": True}),
                (moving, "PATCH", GIT + "refs/heads/" + BRANCH, {"sha": COMMITTED, "force": 0}),
                (moving, "PATCH", GIT + "refs/heads/" + BRANCH, {"sha": COMMITTED}),
                (moving, "PATCH", GIT + "refs/heads/main", {"sha": COMMITTED, "force": False}),
                (moving, "POST", GIT + "refs/heads/" + BRANCH, {"sha": COMMITTED, "force": False}),
                (moving, "POST", GIT + "refs", {"ref": "refs/heads/" + BRANCH, "sha": COMMITTED}),
                (made, "PATCH", GIT + "refs/heads/" + BRANCH, {"sha": COMMITTED, "force": False})):
            self.assertFalse(push.permits(state, method, path, body), (method, path, body))
        # Nothing past the tree is written by a state that says it read back what it did not.
        for bad in (dict(made, checked=False), dict(made, commit_back=False), dict(made, new=None),
                    dict(made, commit=None), dict(made, commit="x"), dict(made, landed=True), dict(made, checked=1)):
            self.assertFalse(push.permits(bad, *self.landing()[4][:3]))
        self.assertFalse(push.permits(dict(self.upto(PUSH, 5), commit="x"), "GET", AT_BRANCH, None))

    def test_each_read_back_and_branch_write_says_whose_a_stop_is(self):
        refused, moved, unanswered = (None, push.ANSWER_REFUSED), (None, push.BRANCH_MOVED), (None, push.UNANSWERED)
        limited, gone = (None, push.RATE_LIMITED), {"status": "404", "body": {}}
        after, blobs = self.AFTER, self.AFTER["blobs"]
        for told in (PUSH, MOVE):
            landing = self.landing(told)
            for step, answer, why in (
                    # The tree read back is the admitted one with exactly the changes in it, or a refusal.
                    (1, dict(after, blobs=dict(blobs, **{"docs/a.md": (BLOB_A, 2)})), refused),
                    (1, dict(after, blobs=dict(blobs, **{"docs/a.md": (MADE, 3)})), refused),
                    (1, dict(after, tree=dict(after["tree"], **{"docs/a.md": "100755"})), refused),
                    (1, dict(after, tree=dict(after["tree"], **{"tests/t.py": FILE}), blobs=dict(blobs, **{"tests/t.py": (BLOB_T, 0)})), refused),
                    (1, dict(after, whole=False), NOT_PERMITTED), (1, None, unanswered),
                    # A commit named as what was made before it is none made.
                    (2, {"status": "201", "body": {"sha": PARENT}}, refused), (2, {"status": "201", "body": {"sha": NEW_TREE}}, refused),
                    (2, {"status": "422", "body": {}}, refused), (2, {"status": "401", "body": {}}, unanswered),
                    (2, {"status": "429", "body": {}}, limited),
                    # The commit read back is the one made: its tree, its one parent, its message.
                    (3, dict(self.BACK, body=dict(self.BACK["body"], tree={"sha": ROOT_TREE})), refused),
                    (3, dict(self.BACK, body=dict(self.BACK["body"], parents=[{"sha": PARENT}, {"sha": NEW_A}])), refused),
                    (3, dict(self.BACK, body=dict(self.BACK["body"], message="Other")), refused),
                    (3, dict(self.BACK, body=dict(self.BACK["body"], sha=NEW_A)), refused),
                    (3, gone, refused), (3, {"status": "403", "body": {}}, refused), (3, None, unanswered),
                    (3, {"status": "401", "body": {}}, unanswered), (3, {"status": "429", "body": {}}, limited),
                    # A branch write refused as no fast-forward, or as standing, was overtaken; any other refusal,
                    # a protection's 403 among them, is a person's.
                    (4, {"status": "422", "body": {}}, moved), (4, {"status": "403", "body": {}}, refused),
                    (4, {"status": "404", "body": {}}, refused), (4, dict(ref(NEW_A), status=landing[4][3]["status"]), refused),
                    (4, dict(ref(COMMITTED), status="202"), refused),
                    (4, {"status": "401", "body": {}}, unanswered), (4, {"status": "429", "body": {}}, limited),
                    (4, {"status": "502", "body": {}}, unanswered), (4, None, unanswered),
                    # The branch read again at another commit, or gone, was written by someone else; read as none, it
                    # has not landed.
                    (5, ref(NEW_A), moved), (5, gone, moved), (5, {"status": "403", "body": {}}, refused),
                    (5, ref(COMMITTED, BRANCH + "x"), refused), (5, None, unanswered), (5, {"status": "401", "body": {}}, unanswered),
                    (5, {"status": "500", "body": {}}, unanswered), (5, {"status": "429", "body": {}}, limited)):
                self.assertEqual(push.seen(self.upto(told, step), *landing[step][:3], answer), why, (told["head"], step, answer))
        # A branch made answers 201 and one moved 200: the other status is no answer of that write.
        self.assertEqual(push.seen(self.upto(PUSH, 4), *self.landing()[4][:3], ref(COMMITTED)), refused)
        self.assertEqual(push.seen(self.upto(MOVE, 4), *self.landing(MOVE)[4][:3], dict(ref(COMMITTED), status="201")), refused)


if __name__ == "__main__":
    unittest.main()
