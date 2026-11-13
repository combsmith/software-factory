"""The guards on a Role's own writes (issue 838): `guards/patch.py`, a patch read as git writes it or not at all."""
from __future__ import annotations

import unittest

from guards import patch

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


def section(name: str, hunks: bytes, old: str = None, extended: bytes = b"index 1111111..2222222 100644\n") -> bytes:
    """One section that changes `name`, or `old` into `name`, as git writes it."""
    was = (old or name).encode()
    return b"diff --git a/%s b/%s\n%s--- a/%s\n+++ b/%s\n%s" % (was, name.encode(), extended, was, name.encode(), hunks)


def new_file(hunks: bytes) -> bytes:
    return b"diff --git a/n b/n\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n+++ b/n\n" + hunks


def gone_file(hunks: bytes) -> bytes:
    return b"diff --git a/f b/f\ndeleted file mode 100644\nindex 1111111..0000000\n--- a/f\n+++ /dev/null\n" + hunks


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

    def test_a_name_is_read_one_way_or_not_at_all(self):
        good = section("docs/a.md", b"@@ -1 +1 @@\n-a\n+A\n")
        self.assertEqual(len(patch.read(good)), 1)
        names = (b'"docs/a\\303\\251.md"', b"docs/a b.md", b"docs/caf\xc3\xa9.md", b"docs/a\\b.md", b'docs/a"b.md',
                 b"docs/../x", b"./x", b"docs//x", b"/x", b"x/", b".git/config", b"docs/.GIT/x", b"docs/a\tb", b"")
        for name in names:
            with self.subTest(name=name):
                data = good.replace(b"docs/a.md", name)
                self.assertIsNone(patch.read(data))
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


if __name__ == "__main__":
    unittest.main()
