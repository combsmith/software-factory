"""The guards on a Role's own writes (issue 838). `guards/patch.py`: a Role's patch, read as git writes it and applied
byte for byte, or not at all."""
from __future__ import annotations

import unittest

from guards import patch

FILE = "100644"
OLD = b"a\nb\nc\nd\ne\nf\ng\nh\n"
CHANGE = (b"diff --git a/docs/a.md b/docs/a.md\nindex 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/a.md\n"
          b"@@ -2,3 +2,3 @@\n b\n-c\n+C\n d\n")
NEW = (b"diff --git a/docs/n.md b/docs/n.md\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n"
       b"+++ b/docs/n.md\n@@ -0,0 +1,2 @@\n+x\n+y\n")
GONE = (b"diff --git a/tests/t.py b/tests/t.py\ndeleted file mode 100644\nindex 1111111..0000000\n"
        b"--- a/tests/t.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
RENAMED = (b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 87%\nrename from docs/a.md\nrename to docs/b.md\n"
           b"index 1111111..2222222 100644\n")
MOVED = RENAMED + b"--- a/docs/a.md\n+++ b/docs/b.md\n@@ -1,2 +1,2 @@\n-a\n+A\n b\n"
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


def after(old: bytes, hunks: bytes):
    """What a file of `old` holds once `hunks`, as a patch writes them, are applied; None where they are not its."""
    return patch.content(old, patch.read(section("docs/a.md", hunks))[0]["hunks"])


def landed(data, tree=None, held=None):
    return patch.applied(data, TREE if tree is None else tree, HELD if held is None else held)


class Patch(unittest.TestCase):
    def test_a_patch_is_read_section_by_section_as_git_writes_it(self):
        self.assertEqual(patch.read(RENAMED), [{"kind": "rename", "old": "docs/a.md", "new": "docs/b.md", "hunks": [],
                                                "index_mode": "100644", "old_mode": None, "new_mode": None}])
        # Each section in its order: a copy, a change of mode, a file moved, and an empty file made and one removed.
        empty = b"diff --git a/docs/e b/docs/e\nnew file mode 100755\nindex 0000000..e69de29\n"
        gone = b"diff --git a/docs/g b/docs/g\ndeleted file mode 100644\nindex e69de29..0000000\n"
        said = [(s["kind"], s["old"], s["new"], s["old_mode"], s["new_mode"], s["index_mode"])
                for s in patch.read(COPIED + MODE + RENAMED + empty + gone)]
        # A link's mode and a submodule's are modes git writes, and are read: what applies a patch refuses them, by
        # its own code. An index line gives a mode only where the section has no line of its own for one.
        other = b"diff --git a/l b/l\nnew file mode 120000\ndiff --git a/m b/m\ndeleted file mode 160000\n"
        self.assertEqual([(s["old_mode"], s["new_mode"]) for s in patch.read(other)], [(None, "120000"), ("160000", None)])
        self.assertIsNone(patch.read(MODE + b"index 1111111..2222222\n")[0]["index_mode"])
        self.assertEqual(said, [("copy", "docs/a.md", "docs/c.md", None, None, None),
                                ("change", "docs/a.md", "docs/a.md", "100644", "100755", None),
                                ("rename", "docs/a.md", "docs/b.md", None, None, "100644"),
                                ("new", "docs/e", "docs/e", None, "100755", None),
                                ("deleted", "docs/g", "docs/g", "100644", None, None)])

    def test_a_name_is_read_one_way_or_not_at_all(self):
        good = MODE
        self.assertEqual(len(patch.read(good)), 1)
        self.assertEqual(landed(good)[1], None)
        names = (b'"docs/a\\303\\251.md"', b"docs/a b.md", b"docs/caf\xc3\xa9.md", b"docs/a\\b.md", b'docs/a"b.md',
                 b"docs/../x", b"./x", b"docs//x", b"/x", b"x/", b".git/config", b"docs/.GIT/x", b"docs/a\tb", b"",
                 b"docs/..", b"docs/.", b"..", b"docs/a\x7f.md")
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
        # A name is read alike as text, for a caller that holds a path and no patch; and what is no text is no name.
        self.assertIs(patch.named("docs/a.md"), True)
        for name in ("", "docs/a b.md", "docs/../x", "docs//x", ".git/config", "docs/caf\u00e9.md", b"docs/a.md", None, ["docs/a.md"],
                     "docs/a.md\n", "docs/a\r", "a\x00b", "a\x7f"):
            self.assertIs(patch.named(name), False, name)
        # A name has no more parts than the bound, which git does not have and no path of this repo's is near.
        deep = "/".join(["d"] * len(patch.DEEPEST))
        self.assertEqual((len(patch.DEEPEST), patch.named(deep), patch.named(deep + "/x")), (32, True, False))
        self.assertEqual(patch.read(good.replace(b"docs/a.md", deep.encode()))[0]["new"], deep)
        self.assertIsNone(patch.read(good.replace(b"docs/a.md", deep.encode() + b"/x")))
        # Every line that names a file names what the header names: a rename's line, a copy's.
        moved = b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 100%\nrename from docs/a.md\nrename to docs/b.md\n"
        self.assertEqual([said["kind"] for said in patch.read(moved + COPIED)], ["rename", "copy"])
        for data in (moved.replace(b"rename from docs/a.md", b"rename from run.sh"),
                     moved.replace(b"rename to docs/b.md", b"rename to run.sh"),
                     moved.replace(b"rename to docs/b.md\n", b""), moved.replace(b"similarity index 100%\n", b""),
                     moved.replace(b"rename", b"copy", 1), moved.replace(b"b/docs/b.md", b"b/docs/a.md"),
                     moved.replace(b"docs/b.md", b"docs/a.md"),      # a file renamed to itself
                     COPIED.replace(b"docs/c.md", b"docs/a.md"),     # and one copied to itself
                     # a rename and a copy are held name by name: a name that is none, on one side alone
                     moved.replace(b"docs/b.md", b".git/config"), moved.replace(b"docs/a.md", b".git/config"),
                     COPIED.replace(b"docs/c.md", b"docs/c d.md"), COPIED.replace(b"docs/a.md", b"docs/.."),
                     # a copy whose own lines name another file than its header does, on either side
                     COPIED.replace(b"copy from docs/a.md", b"copy from run.sh"), COPIED.replace(b"copy to docs/c.md", b"copy to run.sh"),
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
            RENAMED.replace(b"1111111..2222222", b"1111111.2222222"), RENAMED.replace(b"1111111..2222222", b"111111g..2222222"),
            RENAMED.replace(b"1111111..2222222", b"..2222222"), RENAMED.replace(b"1111111..2222222", b"1111111.."),
            RENAMED.replace(b"2222222 100644", b"2222222 file"),
            b"diff --git a/x.bin b/x.bin\nindex 1111111..2222222 100644\nGIT binary patch\nliteral 2\nJcmZQ%0000\n\n",
            b"diff --git a/x.bin b/x.bin\nindex 1111111..2222222 100644\nBinary files a/x.bin and b/x.bin differ\n",
            b"diff --git a/docs/a.md b/docs/a.md\nindex 1111111..2222222 100644\n",           # a section that changes nothing
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\n",
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode rwx\n",
            b"diff --git a/n b/n\nnew file mode 100644\ndeleted file mode 100644\n",
            b"diff --git a/n b/n\nnew file mode 100644\nold mode 100644\nnew mode 100755\n",
            # A mode git does not write; a change of mode to the same mode; a second mode on the index line.
            b"diff --git a/f b/f\nold mode 100644\nnew mode 999\n", b"diff --git a/f b/f\nold mode 1\nnew mode 100644\n",
            b"diff --git a/n b/n\nnew file mode 7\n", b"diff --git a/f b/f\ndeleted file mode 0100644\n",
            b"diff --git a/f b/f\nold mode 100644\nnew mode 100644\n",
            b"diff --git a/n b/n\nnew file mode 100644\nindex 0000000..2222222 100755\n",
            b"diff --git a/f b/f\ndeleted file mode 100644\nindex 1111111..0000000 100644\n",
            b"diff --git a/f b/f\nindex 1111111..2222222 120000\nold mode 100644\nnew mode 100755\n",
            MODE + b"index 1111111..2222222 100755\n",
            # What only a rename or a copy has, on a section that is neither.
            b"diff --git a/a b/b\nnew file mode 100644\nsimilarity index 100%\nrename from a\nrename to b\n",
            b"diff --git a/f b/f\nsimilarity index 100%\nold mode 100644\nnew mode 100755\n",
            b"diff --git a/a b/b\ndeleted file mode 100644\nsimilarity index 100%\nrename from a\nrename to b\n",
            b"diff --git a/f b/f\ndeleted file mode 100644\nold mode 100644\nnew mode 100755\n",
            # How alike two files are is a whole number of percent, 100 at most.
            RENAMED.replace(b"index 87%", b"index 87"), RENAMED.replace(b"index 87%", b"index 101%"),
            RENAMED.replace(b"index 87%", b"index 1000%"), RENAMED.replace(b"index 87%", b"index 087%"),
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertIsNone(patch.read(data))
                self.assertIsNone(patch.sources(data))
                self.assertEqual(landed(data), (None, patch.UNREADABLE))
        # Two files wholly alike and wholly unlike are read.
        self.assertEqual([len(patch.read(RENAMED.replace(b"index 87%", said))) for said in (b"index 100%", b"index 0%")], [1, 1])

    def test_a_sections_hunks_are_read_as_their_headers_count_them(self):
        line = lambda sign, text: {"sign": sign, "text": text, "bare": False}
        hunk = {"old_start": 2, "old_count": 3, "new_start": 2, "new_count": 3,
                "lines": [line(b" ", b"b"), line(b"-", b"c"), line(b"+", b"C"), line(b" ", b"d")]}
        self.assertEqual(patch.read(CHANGE), [{"kind": "change", "old": "docs/a.md", "new": "docs/a.md", "hunks": [hunk],
                                               "index_mode": "100644", "old_mode": None, "new_mode": None}])
        said = [(s["kind"], s["old"], s["new"], len(s["hunks"])) for s in patch.read(NEW + GONE + MOVED + COPIED + MODE)]
        self.assertEqual(said, [("new", "docs/n.md", "docs/n.md", 1), ("deleted", "tests/t.py", "tests/t.py", 1),
                                ("rename", "docs/a.md", "docs/b.md", 1), ("copy", "docs/a.md", "docs/c.md", 0),
                                ("change", "docs/a.md", "docs/a.md", 0)])
        # After a header's second `@@` git writes nothing, or a space and the line the hunk stands under. A line's
        # bytes are its own to the last: a space, a tab or a carriage return at its end is read.
        under = patch.read(section("docs/a.md", b"@@ -2,3 +2,3 @@ def f():\n b\n-c \r\n+C\t\r\n d\n"))[0]["hunks"][0]
        self.assertEqual([said["text"] for said in under["lines"]], [b"b", b"c \r", b"C\t\r", b"d"])
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

    def test_a_hunk_or_a_side_git_does_not_write_is_unreadable(self):
        marker = b"\\ No newline at end of file\n"
        good = section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\n")
        self.assertEqual(len(patch.read(good)), 1)
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
            CHANGE.replace(b"@@ -2,3 +2,3 @@", b"@@ -1000000000,3 +2,3 @@"),
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
            # The one hunk of either stands at line 1 of the side that has lines, and at line 0 of the other.
            new_file(b"@@ -7,0 +1 @@\n+x\n"), new_file(b"@@ -0,0 +2 @@\n+x\n"), new_file(b"@@ -0,1 +1,2 @@\n a\n+b\n"),
            gone_file(b"@@ -1 +7,0 @@\n-a\n"), gone_file(b"@@ -2 +0,0 @@\n-a\n"), gone_file(b"@@ -1,2 +0,1 @@\n-a\n b\n"),
            # A hunk after one that holds git's marker: the file ended there, on one side or on both.
            section("f", b"@@ -1 +1 @@\n-a\n" + marker + b"+A\n" + marker + b"@@ -3 +3 @@\n-b\n+B\n"),
            section("f", b"@@ -1 +1 @@\n-a\n+A\n" + marker + b"@@ -3 +3 @@\n-c\n+C\n"),
            section("f", b"@@ -1 +1 @@\n-a\n" + marker + b"+A\n@@ -3,0 +4 @@\n+c\n"),
            # git's marker on a line that is not the last of its side, which git would join to the next.
            section("f", b"@@ -1 +1,2 @@\n-a\n+A\n" + marker + b"+B\n"), section("f", b"@@ -1,2 +1 @@\n-a\n" + marker + b"-b\n+A\n"),
            section("f", b"@@ -1,2 +1,2 @@\n a\n" + marker + b"-b\n+B\n"), section("f", b"@@ -1,2 +1,2 @@\n-a\n+A\n" + marker + b" b\n"),
            section("f", b"@@ -1 +1 @@\n-a\n+A\n" + marker + marker),
            # A side git's marker ended stays ended, whatever the marker says of the other side after it.
            section("f", b"@@ -1,2 +1 @@\n-a\n" + marker + b"+A\n" + marker + b"-b\n"),
            section("f", b"@@ -1 +1,2 @@\n+A\n" + marker + b"-a\n" + marker + b"+B\n"),
            # git's marker on an empty line, in a hunk or after its last: a line of no byte and no newline is no line.
            section("f", b"@@ -1 +1,2 @@\n a\n+\n" + marker), section("f", b"@@ -1 +1 @@\n-\n" + marker + b"+A\n"),
            # A NUL in a line is a binary change written as text.
            section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\x00\n"), section("docs/a.md", b"@@ -1 +1 @@\n-a\x00\n+A\n"),
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertIsNone(patch.read(data))
                self.assertIsNone(patch.sources(data))
                self.assertEqual(landed(data), (None, patch.UNREADABLE))

    def test_sources_names_each_file_a_patch_reads_once_and_no_new_file(self):
        self.assertEqual(patch.sources(CHANGE), ["docs/a.md"])
        self.assertEqual(patch.sources(NEW), [])
        self.assertEqual(patch.sources(MOVED), ["docs/a.md"])
        # A file read with no hunk is read all the same: a copy, a rename and a change of mode, each alone.
        whole = b"diff --git a/run.sh b/bin/run.sh\nsimilarity index 100%\nrename from run.sh\nrename to bin/run.sh\n"
        self.assertEqual([patch.sources(data) for data in (COPIED, whole, MODE)], [["docs/a.md"], ["run.sh"], ["docs/a.md"]])
        self.assertEqual(patch.sources(CHANGE + COPIED + GONE), ["docs/a.md", "tests/t.py"])
        # A new file reads none, and the files after it are named all the same.
        self.assertEqual(patch.sources(NEW + CHANGE + NEW.replace(b"n.md", b"m.md") + GONE), ["docs/a.md", "tests/t.py"])

    def test_a_hunk_stands_where_its_header_says_and_nowhere_else(self):
        # Two hunks of one file, each where its header says; a line added at the top, one taken from the end.
        self.assertEqual(after(OLD, b"@@ -1,2 +1,3 @@\n+z\n a\n b\n@@ -7,2 +8 @@\n g\n-h\n"), b"z\na\nb\nc\nd\ne\nf\ng\n")
        # A hunk of no context: lines put in after line 3, and lines taken out with nothing put back.
        self.assertEqual(after(OLD, b"@@ -3,0 +4,2 @@\n+x\n+y\n"), b"a\nb\nc\nx\ny\nd\ne\nf\ng\nh\n")
        self.assertEqual(after(OLD, b"@@ -2,2 +1,0 @@\n-b\n-c\n"), b"a\nd\ne\nf\ng\nh\n")
        # A carriage return is a byte of its line, and stays one: at a line's end, or in the middle of it.
        self.assertEqual(after(b"a\r\nb\r\n", b"@@ -1,2 +1,2 @@\n-a\r\n+A\r\n b\r\n"), b"A\r\nb\r\n")
        self.assertEqual(after(b"a\rb\nc\x0cd\n", b"@@ -1 +1 @@\n-a\rb\n+A\rb\n"), b"A\rb\nc\x0cd\n")
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
                      b"@@ -5,2 +4,2 @@\n b\n-c\n+C\n",          # the new side said to begin a line early
                      b"@@ -5 +0 @@\n-b\n+B\n",                 # or at no line, though it holds one
                      b"@@ -5,2 +1,0 @@\n-b\n-c\n",              # lines taken out, the new side said to stand at the top
                      b"@@ -7,2 +7,2 @@\n d\n-e\n+E\n",          # a hunk past the file's end
                      b"@@ -8,0 +8 @@\n+x\n", b"@@ -8,0 +9 @@\n+x\n",        # a line put in a line past the file's end
                      b"@@ -5,2 +5,2 @@\n b\n-c\n+C\n@@ -2,1 +2,1 @@\n-b\n+B\n",     # a hunk before the one before it
                      b"@@ -5,2 +5,2 @@\n b\n-c\n+C\n@@ -6,1 +6,1 @@\n-c\n+X\n",     # a hunk over the one before it
                      b"@@ -0,2 +1,2 @@\n a\n-b\n+B\n",          # a hunk of two lines said to stand before the first
                      # a hunk that takes a line the hunk before it took, its new side where that leaves it
                      b"@@ -5,2 +5 @@\n-b\n-c\n+B\n@@ -6 +6 @@\n-c\n+X\n",
                      # two hunks with no line between them, which git writes as one and reads in another order
                      b"@@ -5 +5 @@\n-b\n+B\n@@ -6 +6 @@\n-c\n+C\n", b"@@ -0,0 +1 @@\n+x\n@@ -0,0 +2 @@\n+z\n",
                      b"@@ -5 +5 @@\n-b\n+B\n@@ -5,0 +6 @@\n+x\n"):
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
        gains = patch.read(section("docs/a.md", b"@@ -0,0 +1 @@\n+x\n"))[0]["hunks"]
        self.assertEqual(patch.content(b"", gains), b"x\n")
        for old in (None, "", 0, [], {}, "a\n", [b"a"]):
            self.assertIsNone(patch.content(old, gains), old)

    def test_a_patch_lands_the_bytes_it_says_and_no_others(self):
        changes, why = landed(CHANGE)
        self.assertEqual((changes, why), ({"written": {"docs/a.md": (FILE, b"a\nb\nC\nd\ne\nf\ng\nh\n")}, "removed": [],
                                           "read": []}, None))
        self.assertEqual(patch.sources(CHANGE), ["docs/a.md"])
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
            MOVED.replace(b"2222222 100644", b"2222222 100755"),
            b"diff --git a/docs/a.md b/docs/b.md\nold mode 100755\nnew mode 100644\nsimilarity index 100%\n"
            b"rename from docs/a.md\nrename to docs/b.md\n",
            b"diff --git a/docs/a.md b/docs/c.md\nold mode 100755\nnew mode 100644\nsimilarity index 100%\n"
            b"copy from docs/a.md\ncopy to docs/c.md\n",                       # and of a copy
            section("docs/a.md", b"@@ -2,3 +2,3 @@\n b\n-x\n+C\n d\n"),      # a hunk that is not the file's
            # a copy is held as a change is: the mode its index line gives, and its hunks
            copied % ((b"docs/c.md",) * 2) + b"index 1111111..2222222 100755\n--- a/docs/a.md\n+++ b/docs/c.md\n@@ -1 +1 @@\n-a\n+A\n",
            copied % ((b"docs/c.md",) * 2) + b"index 1111111..2222222 100644\n--- a/docs/a.md\n+++ b/docs/c.md\n@@ -1 +1 @@\n-x\n+A\n",
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
            b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 120000\n",    # a file turned into a link
            b"diff --git a/link b/link\nold mode 120000\nnew mode 100644\n",              # a link turned into a file
            new % (b"link/x", b"link/x", b"100644", b"link/x"),                # a file under a link
            new % (b"run.sh/x", b"run.sh/x", b"100644", b"run.sh/x"),          # a file under a file
            new % (b"docs", b"docs", b"100644", b"docs"),                      # a file where a directory stands
            new % (b"n", b"n", b"100644", b"n") + new % (b"n/x", b"n/x", b"100644", b"n/x"),    # one of its own under another
            b"diff --git a/link b/l2\nsimilarity index 100%\nrename from link\nrename to l2\n",    # a link moved
            b"diff --git a/link b/l2\nsimilarity index 100%\ncopy from link\ncopy to l2\n",        # a link copied
            b"diff --git a/link b/l2\nold mode 120000\nnew mode 100644\nsimilarity index 100%\ncopy from link\ncopy to l2\n",
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
            new % (b"n/x", b"n/x", b"100644", b"n/x") + new % (b"n", b"n", b"100644", b"n"),    # the same, the other way about
            # Nor under a file that stands further up than its own directory, in the tree or in the patch.
            new % (b"run.sh/sub/x", b"run.sh/sub/x", b"100644", b"run.sh/sub/x"),
            new % (b"n", b"n", b"100644", b"n") + new % (b"n/sub/x", b"n/sub/x", b"100644", b"n/sub/x"),
            b"diff --git a/docs/a.md b/link/sub/x\nsimilarity index 100%\ncopy from docs/a.md\ncopy to link/sub/x\n",
            # Nor under a file that itself stands in a directory, in the tree or in the patch.
            new % (b"docs/a.md/x", b"docs/a.md/x", b"100644", b"docs/a.md/x"),
            new % (b"d/n", b"d/n", b"100644", b"d/n") + new % (b"d/n/x", b"d/n/x", b"100644", b"d/n/x"),
        )
        for data in cases:
            with self.subTest(data=data):
                self.assertEqual(landed(data), (None, patch.NOT_A_FILE))
        # A rename and a copy may change the mode to a file's two alone.
        for mode in (b"120000", b"160000"):
            for verb in (b"rename", b"copy"):
                data = (b"diff --git a/docs/a.md b/l\nold mode 100644\nnew mode %s\nsimilarity index 100%%\n%s from docs/a.md\n"
                        b"%s to l\n" % (mode, verb, verb))
                self.assertEqual(landed(data), (None, patch.NOT_A_FILE), data)
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
                           (TREE, {**HELD, b"other": b""}), (TREE, {**HELD, "other": None}), (TREE, {**HELD, "other": "text"})):
            self.assertEqual(patch.applied(CHANGE, tree, held), (None, patch.TREE_UNREAD))
            self.assertEqual(patch.applied(b"no patch\n", tree, held), (None, patch.TREE_UNREAD))
        # So is a file the tree holds whose bytes were not handed over, or are no bytes: with hunks or with none, it is
        # not guessed at. What is no patch is the Role's all the same, and so is a file the tree does not hold.
        moved = b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 100%\nrename from docs/a.md\nrename to docs/b.md\n"
        for data in (CHANGE, moved, COPIED, MODE):
            for held in ({}, {"docs/a.md": OLD.decode()}, {"docs/a.md": None}):
                self.assertEqual(landed(data, held=held), (None, patch.TREE_UNREAD), (data, held))
        for data in (GONE, GONE[:GONE.index(b"--- ")]):      # a file removed, by its hunk or with none
            self.assertEqual(landed(data, held={}), (None, patch.TREE_UNREAD), data)
        self.assertEqual(landed(b"no patch\n", held={}), (None, patch.UNREADABLE))
        self.assertEqual(landed(section("docs/none.md", b"@@ -1 +1 @@\n-a\n+b\n"), held={}), (None, patch.NOT_APPLIED))
        # A link and a submodule are refused before any bytes of one are asked for.
        for name in ("link", "vendored"):
            self.assertEqual(landed(section(name, b"@@ -1 +1 @@\n-a\n+b\n", extended=b""), held={}), (None, patch.NOT_A_FILE), name)


if __name__ == "__main__":
    unittest.main()
