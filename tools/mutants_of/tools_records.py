"""The mutants of `tools/records.py`: tools/mutants.py runs them."""

# Decision 0009: the index of the records is made from them alone.
INDEX = ("tests.test_tools.Context.test_the_records_index_is_made_from_the_records_and_a_stale_one_fails",)

TARGETS = ("tools/records.py",)
MUTANTS = [
    ("a replaced record is shown live", "tools/records.py",
     'status = "replaced by " + _number(replaced) if replaced else "live"', 'status = "live"', INDEX),
    ("a chain stops at the record that replaced the first", "tools/records.py",
     "        while head in records and records[head][1]", "        if head in records and records[head][1]", INDEX),
    ("the tests count toward an area", "tools/records.py", 'SKIPPED = {"tests"}', "SKIPPED = set()", INDEX),
    ("a name with no folder is an area", "tools/records.py", '            if "/" in name:\n', "            if True:\n", INDEX),
    ("a pipe in a title breaks its row", "tools/records.py", '.replace("|", "\\\\|")', "", INDEX),
    ("a backslash in a title escapes the pipe after it", "tools/records.py", 'cell = title.replace("\\\\", "\\\\\\\\")', "cell = title", INDEX),
    ("a linked record is read", "tools/records.py", "for p in found if p.is_file() and not p.is_symlink()}", "for p in found if p.is_file()}", INDEX),
    ("a linked folder of records is read", "tools/records.py", "if folder.is_dir() and not folder.is_symlink() else", "if folder.is_dir() else", INDEX),
    ("a linked index is written through", "tools/records.py", "    if (root / INDEX).is_symlink():\n", "    if False:\n", INDEX),
    ("a title keeps its number", "tools/records.py",
     'title = first[len("# %s. " % digits):] if', 'title = first if', INDEX),
    ("a record that replaced none has a chain", "tools/records.py", "        if head != rel:\n", "        if True:\n", INDEX),
    ("the index is written empty", "tools/records.py",
     "    (root / INDEX).write_text(render(root), encoding=", '    (root / INDEX).write_text("", encoding=', INDEX),
]
