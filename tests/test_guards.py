"""The guards on a Role's own writes (issue 838). `guards/patch.py`: the sections of a Role's patch, read as git
writes them, or not at all."""
from __future__ import annotations

import unittest

from guards import patch

RENAMED = (b"diff --git a/docs/a.md b/docs/b.md\nsimilarity index 87%\nrename from docs/a.md\nrename to docs/b.md\n"
           b"index 1111111..2222222 100644\n")
COPIED = b"diff --git a/docs/a.md b/docs/c.md\nsimilarity index 100%\ncopy from docs/a.md\ncopy to docs/c.md\n"
MODE = b"diff --git a/docs/a.md b/docs/a.md\nold mode 100644\nnew mode 100755\n"
EMPTY = b"diff --git a/%s b/%s\nnew file mode 100644\nindex 0000000..e69de29\n"


def readable(data: bytes) -> list:
    """The sections of a patch `patch.read` reads: where it reads none an assertion fails, so a rule broken to refuse
    what git writes fails a test, and never raises in one."""
    said = patch.read(data)
    assert said is not None, data
    return said


class Patch(unittest.TestCase):
    def test_a_patch_is_read_section_by_section_as_git_writes_it(self):
        self.assertEqual(patch.read(RENAMED), [{"kind": "rename", "old": "docs/a.md", "new": "docs/b.md", "hunks": [],
                                                "index_mode": "100644", "old_mode": None, "new_mode": None}])
        # Each section in its order: a copy, a change of mode, a file moved, and an empty file made and one removed.
        empty = b"diff --git a/docs/e b/docs/e\nnew file mode 100755\nindex 0000000..e69de29\n"
        gone = b"diff --git a/docs/g b/docs/g\ndeleted file mode 100644\nindex e69de29..0000000\n"
        said = [(s["kind"], s["old"], s["new"], s["old_mode"], s["new_mode"], s["index_mode"])
                for s in readable(COPIED + MODE + RENAMED + empty + gone)]
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
                                ("change", "docs/a.md", "docs/a.md", "100644", "100755", None),
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
        names = (b'"docs/a\\303\\251.md"', b"docs/a b.md", b"docs/caf\xc3\xa9.md", b"docs/a\\b.md", b'docs/a"b.md',
                 b"docs/../x", b"./x", b"docs//x", b"/x", b"x/", b".git/config", b"docs/.GIT/x", b"docs/a\tb", b"",
                 b"docs/..", b"docs/.", b"..", b"docs/a\x7f.md", b"C:.git/note", b"C:/note", b"a:b")
        for name in names:
            with self.subTest(name=name):
                data = good.replace(b"docs/a.md", name)
                self.assertIsNone(patch.read(data))
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
                     moved.replace(b"similarity index 100%", b"similarity index x%"),
                     b"diff --git a/docs/a.md b/run.sh\nold mode 100644\nnew mode 100755\n",     # two names and no rename
                     moved + b"copy from docs/a.md\ncopy to docs/b.md\n"):
            with self.subTest(data=data):
                self.assertIsNone(patch.read(data))

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
        # A file removed and a directory made in its place, as git writes it, is read.
        gone = EMPTY.replace(b"new", b"deleted").replace(b"0000000..e69de29", b"e69de29..0000000")
        self.assertEqual(len(readable(gone % ((b"e",) * 2) + EMPTY % ((b"e/x",) * 2))), 2)
        # How alike two files are is asked its length before its value, which is never built of a count too long.
        said, number = [], patch._number
        patch._number = lambda digits: said.append(digits) or number(digits)
        try:
            self.assertIsNone(patch.read(RENAMED.replace(b"87", b"9" * 4000)))
        finally:
            patch._number = number
        self.assertEqual(said, [])
        # Two files wholly alike and wholly unlike are read.
        self.assertEqual([len(readable(RENAMED.replace(b"index 87%", said))) for said in (b"index 100%", b"index 0%")], [1, 1])
        # What is bytes of a subclass is not read: its own methods would be read in place of the built-in ones.

        class Said(bytes):
            def split(self, sep=None, maxsplit=-1):
                return MODE.split(b"\n")
        self.assertIsNone(patch.read(Said(b"x")))
        # No hunk is read yet: a section with its sides and a hunk under it is not one this reads, and no line is dropped.
        self.assertIsNone(patch.read(MODE + b"index 1111111..2222222\n--- a/docs/a.md\n+++ b/docs/a.md\n@@ -1 +1 @@\n-a\n+A\n"))


if __name__ == "__main__":
    unittest.main()
