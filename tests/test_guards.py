"""The guards on a Role's own writes (issue 838). `guards/patch.py`: a Role's patch, read as git writes it and applied
byte for byte, or not at all. `guards/push.py`: what a push may read, and the answers it takes."""
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
            # A rename or a copy below 100% alike with no hunk, and one wholly alike with a hunk.
            RENAMED[:RENAMED.index(b"--- ")], COPIED.replace(b"100%", b"87%") + b"index 1111111..2222222 100644\n",
            RENAMED.replace(b"87%", b"100%"),
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
        # A new file reads none, and the files after it are named all the same.
        self.assertEqual(patch.sources(NEW + CHANGE + NEW.replace(b"n.md", b"m.md") + GONE), ["docs/a.md", "tests/t.py"])

    def test_a_hunk_stands_where_its_header_says_and_nowhere_else(self):
        # Two hunks of one file, each where its header says; a line added at the top, one taken from the end. Where
        # hunks stand to each other and where each new side begins `read` holds, from the patch alone.
        self.assertEqual(after(OLD, b"@@ -1,2 +1,3 @@\n+z\n a\n b\n@@ -7,2 +8 @@\n g\n-h\n"), b"z\na\nb\nc\nd\ne\nf\ng\n")
        # A hunk of no context: lines put in after line 3, and lines taken out with nothing put back.
        self.assertEqual(after(OLD, b"@@ -3,0 +4,2 @@\n+x\n+y\n"), b"a\nb\nc\nx\ny\nd\ne\nf\ng\nh\n")
        self.assertEqual(after(OLD, b"@@ -2,2 +1,0 @@\n-b\n-c\n"), b"a\nd\ne\nf\ng\nh\n")
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
        self.assertEqual(landed(whole)[0], {"written": {"bin/run.sh": ("100755", b"#!/bin/sh\n")}, "removed": ["run.sh"],
                                            "read": ["run.sh"]})
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
        )
        for data in not_applied:
            with self.subTest(data=data):
                self.assertEqual(landed(data), (None, patch.NOT_APPLIED))
        # A removal that leaves bytes is no removal: the tree holds more than the patch takes.
        self.assertEqual(landed(gone, held=dict(HELD, **{"tests/t.py": b"x\ny\n"})), (None, patch.NOT_APPLIED))
        # An empty file is removed with no hunk, as git writes it.
        self.assertEqual(landed(gone[:gone.index(b"--- ")], held=dict(HELD, **{"tests/t.py": b""}))[0]["removed"], ["tests/t.py"])
        # A file the tree does not hold is not the patch's to change, whatever bytes were read for its name.
        self.assertEqual(landed(section("docs/none.md", b"@@ -1 +1 @@\n-a\n+b\n"), held={"docs/none.md": b"a\n"}),
                         (None, patch.NOT_APPLIED))
        # A file the tree holds whose bytes were not handed over, or are no bytes, is not guessed at: with hunks or
        # with none, nothing lands.
        for data in (CHANGE, moved % ((b"docs/b.md",) * 2), copied % ((b"docs/c.md",) * 2), MODE):
            for held in ({}, {"docs/a.md": OLD.decode()}):
                self.assertEqual(landed(data, held=held), (None, patch.TREE_UNREAD), (data, held))
        away = b"diff --git a/tests/t.py b/x\nsimilarity index 100%\nrename from tests/t.py\nrename to x\n"
        twice = (CHANGE + CHANGE, CHANGE + moved % ((b"docs/b.md",) * 2), moved % ((b"docs/b.md",) * 2) + CHANGE,
                 gone + new % ((b"tests/t.py",) * 3), new % ((b"n",) * 3) + new % ((b"n",) * 3),
                 gone + away, moved % ((b"docs/b.md",) * 2) + moved % ((b"docs/c.md",) * 2),      # a file moved once it is gone
                 copied % ((b"docs/c.md",) * 2) + copied % ((b"docs/c.md",) * 2),
                 copied % ((b"docs/c.md",) * 2) + copied % ((b"docs/d.md",) * 2),     # a file copied twice
                 # two files moved onto one name; a new file and a copy on one name
                 moved % ((b"x",) * 2) + away, new % ((b"docs/c.md",) * 3) + copied % ((b"docs/c.md",) * 2))
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
        for held in ({"d/l": "120000"}, {"d/sub": "160000"}):
            self.assertEqual(landed(new % (b"d", b"d", b"100644", b"d"), tree=held), (None, patch.NOT_A_FILE), held)
        # A directory is one at any depth: where the tree holds `a/b/c`, neither `a/b` nor `a` is a file's place.
        for name in (b"a/b", b"a"):
            self.assertEqual(landed(new % (name, name, b"100644", name), tree=dict(TREE, **{"a/b/c": FILE})),
                             (None, patch.NOT_A_FILE), name)

    def test_what_a_port_did_not_read_is_the_factorys_under_its_own_code(self):
        # A tree or contents in no shape a port gives is the Factory's, whatever the patch is: a path is text.
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
                           (TREE, {**HELD, b"other": b""}), (TREE, {**HELD, "other": None}), (TREE, {**HELD, "other": "text"})):
            self.assertEqual(patch.applied(CHANGE, tree, held), (None, patch.TREE_UNREAD))
            self.assertEqual(patch.applied(b"no patch\n", tree, held), (None, patch.TREE_UNREAD))
        # So is a file the tree holds whose bytes were not handed over, or are no bytes: with hunks or with none, it is
        # not guessed at. What is no patch is the Role's all the same, and so is a file the tree does not hold.
        moved = b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 100%\nrename from docs/a.md\nrename to docs/b.md\n"
        for data in (CHANGE, moved, COPIED, MODE):
            for held in ({}, {"docs/a.md": OLD.decode()}, {"docs/a.md": None}):
                self.assertEqual(landed(data, held=held), (None, patch.TREE_UNREAD), (data, held))
        # Missing bytes are the Factory's whatever else the section says: beside a mode that is not the tree's too.
        self.assertEqual(landed(CHANGE.replace(b"2222222 100644", b"2222222 100755"), held={}), (None, patch.TREE_UNREAD))
        # The Factory's code is its own, by its letters, and none of the Role's three.
        self.assertEqual(patch.TREE_UNREAD, "push_tree_unreadable")
        self.assertNotIn(patch.TREE_UNREAD, (patch.UNREADABLE, patch.NOT_APPLIED, patch.NOT_A_FILE))
        for data in (GONE, GONE[:GONE.index(b"--- ")]):      # a file removed, by its hunk or with none
            self.assertEqual(landed(data, held={}), (None, patch.TREE_UNREAD), data)
        self.assertEqual(landed(b"no patch\n", held={}), (None, patch.UNREADABLE))
        self.assertEqual(landed(section("docs/none.md", b"@@ -1 +1 @@\n-a\n+b\n"), held={}), (None, patch.NOT_APPLIED))
        # A link and a submodule are refused before any bytes of one are asked for.
        for name, mode in (("link", b"120000"), ("vendored", b"160000")):
            hunks, extended = b"@@ -1 +1 @@\n-a\n+b\n", b"index 1111111..2222222 %s\n" % mode
            self.assertEqual(landed(section(name, hunks, extended=extended), held={}), (None, patch.NOT_A_FILE), name)

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

        def snapshot(tree, out="."):
            listed = [entry.split(b"\t") for entry in run(tree, "ls-files", "-s", "-z").stdout.split(b"\0") if entry]
            return {name.decode(): (meta.split()[0].decode(), (tree / out / name.decode()).read_bytes()) for meta, name in listed}

        def both(tree, first, wrong, tag):
            # What each of git's two ways lands of `wrong` on the tree `first`: the files, or what git said in refusing.
            out = []
            for form, way in enumerate((("--unidiff-zero",), ())):
                run(tree, "read-tree", first)
                applied = run(tree, "apply", "--cached", *way, "-", data=wrong, check=False)
                if applied.returncode:
                    out.append(applied.stderr)
                else:
                    run(tree, "checkout-index", "-a", "-f", "--prefix=../out-%s-%d/" % (tag, form))
                    out.append(snapshot(tree, "../out-%s-%d" % (tag, form)))
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
                        self.assertIn(got, both(tree, first, wrong, turn))
        self.assertEqual(kinds, {"change", "new", "deleted", "rename", "copy"})
        # Enough broken patches still land for the comparison to say something: far fewer, and the breaking has lost its aim.
        self.assertTrue(copied_with_hunks and lands >= 30, (copied_with_hunks, lands))
        # The shape in which git's two ways part, as `git diff` itself writes it, alone and beside another hunk of no
        # context: what `applied` lands is what git's own index holds, whatever `git apply` makes of its own patch.
        for old, new in ((b"b\nb", b"b\n"), (b"x\nb\nb", b"X\nb\n"), (b"x\nb \nb", b"X\nb \n")):
            with tempfile.TemporaryDirectory() as where:
                tree = pathlib.Path(where) / "tree"
                tree.mkdir()
                run(tree, "init", "-q")
                (tree / "f").write_bytes(old)
                run(tree, "add", "-A")
                first = run(tree, "write-tree").stdout.decode().strip()
                (tree / "f").write_bytes(new)
                run(tree, "add", "-A")
                data = run(tree, "diff", "--cached", "-U0", first).stdout
                self.assertTrue(parted(data), data)
                self.assertEqual(patch.applied(data, {"f": FILE}, {"f": old})[0]["written"], {"f": (FILE, new)})


REPO = "combsmith/software-factory"
GIT = "/repos/%s/git/" % REPO
BRANCH = "factory-work/issue-838-1"
PARENT, ROOT_TREE, MADE_TREE, MADE = "a" * 40, "b" * 40, "c" * 40, "d" * 40
BLOB_A, BLOB_RUN, BLOB_T, BLOB_LINK, PINNED = "1" * 40, "2" * 40, "3" * 40, "4" * 40, "5" * 40
NEW_A = "e" * 40
BEFORE = {"docs/a.md": (FILE, BLOB_A), "run.sh": ("100755", BLOB_RUN), "tests/t.py": (FILE, BLOB_T),
          "link": ("120000", BLOB_LINK), "vendored": ("160000", PINNED)}
WROTE = {"written": {"docs/a.md": (FILE, b"A\n"), "docs/n.md": ("100755", b"x\n")}, "removed": ["tests/t.py"],
         "read": []}
BLOBS = {"docs/a.md": "QQo=", "docs/n.md": "eAo="}
PUSH = {"repo": REPO, "branch": BRANCH, "parent": PARENT, "head": None, "message": "Add the notes (issue 838)",
        "changes": WROTE, "blobs": BLOBS}
MOVE = dict(PUSH, head=PARENT)
READING = dict(PUSH, changes=None, blobs=None)



def listed(name: str, held: dict, **more) -> dict:
    """A tree's listing as GitHub answers it, whole: each path of `held`, and each directory above one."""
    folders = sorted({"/".join(path.split("/")[:n]) for path in held for n in range(1, path.count("/") + 1)})
    entries = [{"path": path, "mode": "040000", "type": "tree", "sha": "9" * 40} for path in folders]
    entries += [{"path": path, "mode": mode, "type": "commit" if mode == "160000" else "blob", "sha": sha}
                for path, (mode, sha) in held.items()]
    return dict({"sha": name, "tree": entries, "truncated": False}, **more)


def answer(status: int, body=None) -> dict:
    """An answer as the caller gives it: GitHub's status as text, and what it said."""
    return {"status": str(status), "body": body}


def ref(sha: str, branch: str = BRANCH) -> dict:
    return {"ref": "refs/heads/" + branch, "object": {"sha": sha, "type": "commit"}}


def honest(told: dict) -> list:
    """Each request of a push told as `told`, in an order the guard allows, with what GitHub answers it."""
    moves = told["head"] is not None
    steps = [("commit", "GET", "commits/" + PARENT, None, answer(200, {"sha": PARENT, "tree": {"sha": ROOT_TREE}})),
             ("tree", "GET", "trees/" + ROOT_TREE + "?recursive=1", None, answer(200, listed(ROOT_TREE, BEFORE))),
             ("branch", "GET", "ref/heads/" + BRANCH, None, answer(200, ref(PARENT)) if moves else answer(404))]
    return steps


def before(step: str, told: dict = PUSH):
    """`(state, request)`: the state of an honest push of `told` just before its request named `step`, and that
    request as `(method, rest, body, answer)`. Every request before it was permitted and its answer taken."""
    state = push.began(told)
    for name, method, rest, body, said in honest(told):
        if name == step:
            return state, (method, rest, body, said)
        assert push.permits(state, method, GIT + rest, body), name
        state = push.seen(state, method, GIT + rest, body, said)
        assert state is not None, name
    assert step is None, step
    return state, None


class Odd(str):
    """Text of another kind, that says it equals anything: what a port that went wrong might hand over."""
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    __hash__ = str.__hash__


def may(state, method: str, rest: str, body=None) -> bool:
    return push.permits(state, method, GIT + rest, body)


def then(state, method: str, rest: str, body, said):
    return push.seen(state, method, GIT + rest, body, said)


class Push(unittest.TestCase):
    def test_a_push_is_told_whole_or_begins_nothing(self):
        for told in (PUSH, MOVE, READING, dict(PUSH, branch="factory-work/issue-1-10")):
            self.assertEqual(push.began(told)["push"], told)
        self.assertEqual(push.began(PUSH), {
            "push": PUSH, "tree": None, "before": None, "branch_read": False, "made": {}, "new": None, "checked": False,
            "commit": None, "commit_back": False, "moved": False, "landed": False})
        less = {k: v for k, v in PUSH.items() if k != "message"}

        class Text(str):
            """Text of another kind, with the right characters: what `+` and `==` on it do is its own to say."""
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
                ("a work branch opened 0 times", dict(PUSH, branch="factory-work/issue-838-0")),
                ("a branch under a work branch", dict(PUSH, branch=BRANCH + "/x")),
                ("a branch that only ends as one", dict(PUSH, branch="x/" + BRANCH)),
                ("a work branch of an issue that is no number", dict(PUSH, branch="factory-work/issue-x-1")),
                ("a branch as long as a work branch's head", dict(PUSH, branch="x" * len("factory-work/issue-") + "838-1")),
                ("a parent that is a list of characters", dict(PUSH, parent=list(PARENT))),
                ("a parent of a character more", dict(PUSH, parent=PARENT + "a")),
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
                ("blobs that are a list", dict(PUSH, blobs=list(BLOBS))),
                ("a repo of another kind", dict(PUSH, repo=Text(REPO))), ("a branch of another kind", dict(PUSH, branch=Text(BRANCH))),
                ("a parent of another kind", dict(PUSH, parent=Text(PARENT))), ("a head of another kind", dict(MOVE, head=Text(PARENT))),
                ("a message of another kind", dict(PUSH, message=Text(PUSH["message"]))),
                ("a blob of another kind", dict(PUSH, blobs=dict(BLOBS, **{"docs/a.md": Text("QQo=")})))):
            self.assertIsNone(push.began(told), said)

    def test_a_pushs_changes_are_what_applied_gives_path_by_path(self):
        def told(**changed):
            changes = dict(WROTE, **changed)
            blobs = {path: "QQo=" for path in changes["written"]} if isinstance(changes.get("written"), dict) else {}
            return dict(PUSH, changes=changes, blobs=blobs)
        for good in (told(), told(removed=[]), told(written={}), told(read=["docs/a.md", "docs/z.md"]),
                     told(written={"a/b": (FILE, b"")}, removed=["a/c", "ab"])):
            self.assertIsNotNone(push.began(good), good["changes"])
            self.assertIsNotNone(push.touched(good["changes"]))
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
                ("a file written under a file removed", told(written={"a/b": (FILE, b"")}, removed=["a"])),
                ("a file removed under a file written", told(written={"a": (FILE, b"")}, removed=["a/b"])),
                ("a file written and removed", told(removed=["docs/a.md"])),
                ("a file removed twice", told(removed=["tests/t.py", "tests/t.py"])),
                ("a file read twice", told(read=["docs/a.md", "docs/a.md"])),
                ("a link written", told(written={"l": ("120000", b"x")})),
                ("a submodule written", told(written={"m": ("160000", b"x")})),
                ("a file of text", told(written={"docs/a.md": (FILE, "A\n")})),
                ("a file that is a list", told(written={"docs/a.md": [FILE, b"A\n"]})),
                ("a file with a thing more", told(written={"docs/a.md": (FILE, b"A\n", NEW_A)})),
                ("a file of bytes alone", told(written={"docs/a.md": (b"A\n",)})),
                ("removed as a tuple", told(removed=("tests/t.py",))), ("read as a tuple", told(read=())),
                ("written as a list", told(written=list(wrote))),
                ("a key more", dict(PUSH, changes=dict(WROTE, kept=[]))),
                ("no read", dict(PUSH, changes={"written": wrote, "removed": []})),
                ("no changes at all", dict(PUSH, changes=[], blobs={}))):
            self.assertIsNone(push.began(bad), said)
            self.assertIsNone(push.touched(bad["changes"]), said)
            self.assertIsNone(push.existing(bad["changes"], {}), said)

    def test_nothing_leaves_outside_this_repos_git_data(self):
        requests = [before(step, told) for told in (PUSH, MOVE) for step in ("commit", "tree", "branch")]
        requests.append((before(None)[0], ("GET", "blobs/" + BLOB_A, None, answer(200, {"sha": BLOB_A}))))
        self.assertEqual(sorted({request[0] for _, request in requests}), ["GET"])
        for state, (method, rest, body, said) in requests:
            self.assertTrue(push.permits(state, method, GIT + rest, body), rest)
            for root in ("/repos/combsmiht/software-factory/git/", "/repos/combsmith/software-fictory/git/",
                         "/repos/combsmith/other/git/", "/repos/other/software-factory/git/",
                         "/repos/%s-canary/git/" % REPO, "/repos/%s/" % REPO, "/repos/%s/pulls/" % REPO,
                         "/repos/%s/git" % REPO, "https://api.github.com" + GIT, GIT[1:], "/x" + GIT, GIT + "../git/",
                         GIT + "/"):
                self.assertFalse(push.permits(state, method, root + rest, body), (method, root + rest))
                self.assertIsNone(push.seen(state, method, root + rest, body, said), (method, root + rest))
            for other in ("DELETE", "PUT", method.lower(), None, [method], Odd("DELETE")):
                self.assertFalse(push.permits(state, other, GIT + rest, body), (other, rest))
            self.assertFalse(push.permits(state, method, None, body))
            self.assertFalse(push.permits(state, method, [GIT + rest], body))
        # A state that is none of `began`'s lets nothing leave: none, one of a key fewer or more, or of a push told wrongly.
        state, (method, rest, body, said) = requests[-1]
        less = {k: v for k, v in state.items() if k != "landed"}

        class Mapping(dict):
            """A mapping of another kind, holding what a state holds."""
        class Path(str):
            def startswith(self, *whatever):
                return True
        self.assertFalse(push.permits(state, method, Path("x" * len(GIT) + rest), body))
        self.assertTrue(push.permits(state, method, GIT + rest, body))
        for bad in (None, [state], dict(state, more=1), less, Mapping(state), dict(state, push=dict(PUSH, branch="main")),
                    dict(state, push=None), dict(state, tree="main"), dict(state, tree=5), dict(state, new=ROOT_TREE[1:]),
                    dict(state, new=5), dict(state, commit="main"), dict(state, commit=5),
                    dict(state, moved=None), dict(state, moved=1), dict(state, branch_read=1), dict(state, checked=0),
                    dict(state, commit_back="yes"), dict(state, landed=0),
                    dict(state, before={"a": [FILE, BLOB_A]}), dict(state, before={"a": (FILE, BLOB_A, 1)}),
                    dict(state, before={"a": (FILE, BLOB_A[1:])}), dict(state, before={"a": (FILE, NEW_A.upper())}),
                    dict(push.began(PUSH), new=MADE_TREE), dict(before(None, READING)[0], new=MADE_TREE),
                    dict(state, before={"a": (FILE, 5)}), dict(state, before=[1]), dict(state, before={"a": None}),
                    dict(state, before={"a": ()}), dict(state, made=None), dict(state, made=5),
                    dict(state, made=dict(state["made"], zz=NEW_A)), dict(state, made={"docs/a.md": "main"}),
                    dict(state, made={("docs/a.md",): NEW_A})):
            for request in ((method, rest, body), ("GET", "blobs/" + BLOB_A, None), ("GET", "commits/" + PARENT, None)):
                self.assertFalse(push.permits(bad, request[0], GIT + request[1], request[2]), bad)
            self.assertIsNone(push.seen(bad, method, GIT + rest, body, said))
        # A state of the right shape whose parts do not agree raises nothing either: it is refused, or takes its course.
        for askew in (dict(state, moved=True), dict(state, commit_back=True), dict(state, made={})):
            for name, method_o, rest_o, body_o, said_o in honest(PUSH):
                push.permits(askew, method_o, GIT + rest_o, body_o)
                push.seen(askew, method_o, GIT + rest_o, body_o, said_o)

    def test_a_push_reads_the_admitted_commit_and_its_own_branch(self):
        for told in (PUSH, MOVE, READING):
            state = push.began(told)
            # At first the commit and the branch alone: the tree is the one the commit names, the blobs that tree's.
            self.assertTrue(may(state, "GET", "commits/" + PARENT))
            self.assertTrue(may(state, "GET", "ref/heads/" + BRANCH))
            for rest in ("trees/" + ROOT_TREE + "?recursive=1", "blobs/" + BLOB_A, "commits/" + MADE):
                self.assertFalse(may(state, "GET", rest), rest)
            state, _ = before("tree", told)
            self.assertEqual(state["tree"], ROOT_TREE)
            self.assertTrue(may(state, "GET", "trees/" + ROOT_TREE + "?recursive=1"))
            self.assertFalse(may(state, "GET", "blobs/" + BLOB_A))
            state, _ = before("branch", told)
            self.assertEqual(state["before"], BEFORE)
            for name in (BLOB_A, BLOB_RUN, BLOB_T, BLOB_LINK):
                self.assertTrue(may(state, "GET", "blobs/" + name), name)
                said = {"sha": name, "size": 2, "content": "QQo=", "encoding": "base64"}
                self.assertIs(then(state, "GET", "blobs/" + name, None, answer(200, said)), state)
                # The blob asked for, in base64, or the push stops.
                for wrong in (answer(404), answer(200), answer(200, [said]), answer(200, dict(said, sha=NEW_A)),
                              answer(200, {k: v for k, v in said.items() if k != "sha"}), answer(200, dict(said, encoding="utf-8")),
                              answer(200, {k: v for k, v in said.items() if k != "encoding"}), answer(200, dict(said, content=None)),
                              answer(200, dict(said, content=b"QQo=")), answer(200, dict(said, content=Odd("QQo=")))):
                    self.assertIsNone(then(state, "GET", "blobs/" + name, None, wrong), (name, wrong))
            for rest in ("commits/" + PARENT, "trees/" + ROOT_TREE + "?recursive=1", "ref/heads/" + BRANCH,
                         "blobs/" + BLOB_A):
                self.assertTrue(may(state, "GET", rest), rest)
                self.assertFalse(may(state, "GET", rest, {}), rest)
                self.assertFalse(may(state, "DELETE", rest), rest)
            # A submodule's commit is no blob of this repo's; a directory's tree and any other name is none it listed.
            for rest in ("blobs/" + PINNED, "blobs/" + "9" * 40, "blobs/" + NEW_A, "blobs/", "blobs/main",
                         "blobs/" + BLOB_A + "/x", "blobs/" + BLOB_A[1:], "commits/" + PARENT[1:],
                         "commits/" + PARENT.upper(), "commits/" + PARENT + "/comments", "commits/" + ROOT_TREE,
                         "commits/" + MADE, "trees/" + ROOT_TREE, "trees/" + ROOT_TREE + "?recursive=1&x=1",
                         "trees/" + PARENT + "?recursive=1", "trees/" + MADE_TREE + "?recursive=1",
                         "trees/main?recursive=1", "ref/heads/main", "ref/heads/" + BRANCH + "0",
                         "ref/heads/" + BRANCH + "/x", "ref/tags/factory/v0.1.12", "refs/heads/" + BRANCH, "refs",
                         "matching-refs/heads/", "../pulls", "../contents/config/hooks.json", ""):
                self.assertFalse(may(state, "GET", rest), rest)

    def test_the_admitted_tree_is_read_whole_or_not_at_all(self):
        state, (method, rest, body, said) = before("commit")
        self.assertEqual(then(state, method, rest, body, said)["tree"], ROOT_TREE)
        # The answer is the status and the body, and nothing more or less.
        for wrong in (dict(said, headers={}), said["body"], {"body": said["body"]}, None):
            self.assertIsNone(then(state, method, rest, body, wrong), wrong)
        for body_said in (None, [], {"sha": MADE, "tree": {"sha": ROOT_TREE}}, {"tree": {"sha": ROOT_TREE}},
                          {"sha": PARENT}, {"sha": PARENT, "tree": ROOT_TREE}, {"sha": PARENT, "tree": {"sha": "main"}},
                          {"sha": PARENT, "tree": {"sha": None}}, {"sha": PARENT, "tree": {}}):
            self.assertIsNone(then(state, method, rest, body, answer(200, body_said)), body_said)
        for status in (201, 404, 500, 304):
            self.assertIsNone(then(state, method, rest, body, answer(status, said["body"])), status)
        # Read again, the commit names the same tree or the push stops.
        state, _ = before("branch")
        self.assertEqual(then(state, method, rest, body, said), state)
        self.assertIsNone(then(state, method, rest, body, answer(200, {"sha": PARENT, "tree": {"sha": MADE_TREE}})))
        state, (method, rest, body, said) = before("tree")
        self.assertEqual(then(state, method, rest, body, said)["before"], BEFORE)
        self.assertIsNone(then(state, method, rest, body, answer(201, said["body"])))
        entries = said["body"]["tree"]
        entry = lambda at, **changed: entries[:at] + [dict(entries[at], **changed)] + entries[at + 1:]
        self.assertEqual((entries[0]["path"], entries[2]["path"], entries[-1]["path"]), ("docs", "docs/a.md", "vendored"))
        for why, listing in (
                ("truncated", listed(ROOT_TREE, BEFORE, truncated=True)),
                ("not said to be whole", {k: v for k, v in listed(ROOT_TREE, BEFORE).items() if k != "truncated"}),
                ("whole by a word", listed(ROOT_TREE, BEFORE, truncated="false")),
                ("whole by nothing", listed(ROOT_TREE, BEFORE, truncated=None)),
                ("whole by a zero", listed(ROOT_TREE, BEFORE, truncated=0)),
                ("another tree's", listed(MADE_TREE, BEFORE)), ("no tree's", listed(None, BEFORE)),
                ("no entries", listed(ROOT_TREE, BEFORE, tree=None)), ("entries by path", listed(ROOT_TREE, BEFORE, tree=BEFORE)),
                ("an entry that is none", listed(ROOT_TREE, BEFORE, tree=entries + [None])),
                ("a path twice", listed(ROOT_TREE, BEFORE, tree=entries + [entries[2]])),
                ("a directory twice", listed(ROOT_TREE, BEFORE, tree=entries + [entries[0]])),
                ("a file where a directory is", listed(ROOT_TREE, BEFORE, tree=entries + [dict(entries[2], path="docs")])),
                ("a directory where a file is", listed(ROOT_TREE, BEFORE, tree=entries + [dict(entries[0], path="run.sh")])),
                ("a path that is no text", listed(ROOT_TREE, BEFORE, tree=entry(2, path=("docs", "a.md")))),
                ("a path that is none", listed(ROOT_TREE, BEFORE, tree=entry(2, path=None))),
                ("an empty path", listed(ROOT_TREE, BEFORE, tree=entry(2, path=""))),
                ("a path with an empty part", listed(ROOT_TREE, BEFORE, tree=entry(2, path="docs//a.md"))),
                ("a path through the directory above", listed(ROOT_TREE, BEFORE, tree=entry(2, path="x/../a.md"))),
                ("a path from here", listed(ROOT_TREE, BEFORE, tree=entry(2, path="./a.md"))),
                ("a directory that is a dot", listed(ROOT_TREE, BEFORE, tree=entry(0, path="docs/."))),
                ("a file above a file", listed(ROOT_TREE, BEFORE, tree=entries + [dict(entries[2], path="run.sh/x")])),
                ("a file above a directory", listed(ROOT_TREE, BEFORE, tree=entries + [dict(entries[0], path="link/d")])),
                ("an entry of no mode", listed(ROOT_TREE, BEFORE, tree=entry(2, mode=None))),
                ("an entry with no mode at all", listed(ROOT_TREE, BEFORE, tree=[{"path": "x", "type": "blob", "sha": BLOB_A}])),
                ("a mode git does not write", listed(ROOT_TREE, BEFORE, tree=entry(2, mode="100664"))),
                ("a file named a tree", listed(ROOT_TREE, BEFORE, tree=entry(2, type="tree"))),
                ("a file named a commit", listed(ROOT_TREE, BEFORE, tree=entry(2, type="commit"))),
                ("a directory named a blob", listed(ROOT_TREE, BEFORE, tree=entry(0, type="blob"))),
                ("a directory in a file's mode", listed(ROOT_TREE, BEFORE, tree=entry(0, mode=FILE))),
                ("a submodule named a blob", listed(ROOT_TREE, BEFORE, tree=entry(-1, type="blob"))),
                ("an entry of no name", listed(ROOT_TREE, BEFORE, tree=entry(2, sha=None))),
                ("a directory of no name", listed(ROOT_TREE, BEFORE, tree=entry(0, sha="main"))),
                ("a list", [listed(ROOT_TREE, BEFORE)]), ("nothing", None)):
            self.assertIsNone(then(state, method, rest, body, answer(200, listing)), why)
        # Read again, it is the same listing or the push stops.
        state, _ = before("branch")
        self.assertEqual(then(state, method, rest, body, said), state)
        fewer = {path: held for path, held in BEFORE.items() if path != "run.sh"}
        self.assertIsNone(then(state, method, rest, body, answer(200, listed(ROOT_TREE, fewer))))

    def test_the_branch_is_read_as_the_decision_admitted_it(self):
        # Absent where the Decision admitted none, and at the admitted head where it admitted one, or the push stops.
        state, (method, rest, body, said) = before("branch")
        self.assertTrue(then(state, method, rest, body, answer(404, {"message": "Not Found"}))["branch_read"])
        for other in (answer(200, ref(PARENT)), answer(200, ref(MADE)), answer(200), answer(403), answer(500), answer(201)):
            self.assertIsNone(then(state, method, rest, body, other), other)
        state, (method, rest, body, said) = before("branch", MOVE)
        self.assertTrue(then(state, method, rest, body, said)["branch_read"])
        for other in (answer(404), answer(200, ref(MADE)), answer(200, ref(ROOT_TREE)), answer(200),
                      answer(200, ref(PARENT, "main")), answer(200, {"ref": "refs/heads/" + BRANCH, "object": PARENT}),
                      answer(200, {"object": {"sha": PARENT}}), answer(200, [ref(PARENT)]), answer(201, ref(PARENT))):
            self.assertIsNone(then(state, method, rest, body, other), other)

    def test_the_paths_apply_is_asked_about_are_the_paths_that_land(self):
        changes = {"written": {"docs/b.md": (FILE, b"x\n"), "docs/a.md": (FILE, b"A\n"), "tests/new.py": (FILE, b"")},
                   "removed": ["tests/t.py", "config/x.json"], "read": ["tests/t.py", "docs/a.md"]}
        self.assertEqual(push.touched(changes), (["config/x.json", "docs/a.md", "docs/b.md", "tests/new.py", "tests/t.py"],
                                                 ["tests/t.py", "docs/a.md"]))
        tree = {"docs/a.md": FILE, "tests/t.py": FILE, "config/x.json": FILE, "run.sh": "100755"}
        self.assertEqual(push.existing(changes, tree), ["config/x.json", "docs/a.md", "tests/t.py"])
        self.assertEqual(push.existing(dict(changes, removed=[]), tree), ["docs/a.md"])
        self.assertEqual(push.existing(changes, {}), [])
        self.assertEqual(push.existing(changes, {"tests/t.py": FILE}), ["tests/t.py"])
        self.assertIsNone(push.existing(changes, list(tree)))
        self.assertIsNone(push.existing(changes, None))
        # What `applied` gave is what is asked about, as it gave it.
        got, reason = patch.applied(CHANGE + NEW + GONE + COPIED, TREE, HELD)
        self.assertIsNone(reason)
        self.assertEqual(push.touched(got), (["docs/a.md", "docs/c.md", "docs/n.md", "tests/t.py"], ["docs/a.md"]))
        self.assertEqual(push.existing(got, TREE), ["docs/a.md", "tests/t.py"])
        self.assertIsNotNone(push.began(dict(PUSH, changes=got, blobs={path: "" for path in got["written"]})))


if __name__ == "__main__":
    unittest.main()
