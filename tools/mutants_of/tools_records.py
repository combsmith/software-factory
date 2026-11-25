"""The mutants of `tools/records.py`: tools/mutants.py runs them."""

# Decision 0009: the index of the records is made from them alone, and printed.
INDEX = ("tests.test_tools.Context.test_the_records_index_is_made_from_the_records_alone",)

TARGETS = ("tools/records.py",)
MUTANTS = [
    ("a replaced record is shown live", "tools/records.py",
     '"replaced by " + _number(replaced) if replaced else "live"', '"live"', INDEX),
    ("a chain stops at the record that replaced the first", "tools/records.py",
     "        while head in records and records[head][1]", "        if head in records and records[head][1]", INDEX),
    ("the tests count toward an area", "tools/records.py", 'SKIPPED = {"tests"}', "SKIPPED = set()", INDEX),
    ("a name with no folder is an area", "tools/records.py", '            if "/" in name and check_context', "            if check_context", INDEX),
    ("a top that is no directory is an area", "tools/records.py",
     "                    and (root / top).is_dir() and not", "                    and not", INDEX),
    ("a pipe in a title breaks its row", "tools/records.py", '.replace("|", "\\\\|")', "", INDEX),
    ("a backslash in a title escapes the pipe after it", "tools/records.py",
     'cell = title.replace("\\\\", "\\\\\\\\")', "cell = title", INDEX),
    ("a linked record is read", "tools/records.py", "p.is_file() and not p.is_symlink()]", "p.is_file()]", INDEX),
    ("a linked folder of records is read", "tools/records.py", '.is_symlink() or folder.is_symlink()', ".is_symlink()", INDEX),
    ("a title keeps its number", "tools/records.py", 'title = first[len("# %s. " % digits):] if', 'title = first if', INDEX),
    ("a title with no number keeps its hashes", "tools/records.py", 'else first.lstrip("# ")', "else first", INDEX),
    ("records are ordered by their names", "tools/records.py", "sorted(kept, key=lambda pair: _order(pair[0]))", "sorted(kept)", INDEX),
    ("a linked folder is an area", "tools/records.py", " and not (root / top).is_symlink():", ":", INDEX),
    ("a path of any shape is an area", "tools/records.py", 'if "/" in name and check_context.PATHLIKE.match(name) and', 'if "/" in name and', INDEX),
    ("the folder above or this one is an area", "tools/records.py", 'and top not in (".", "..")', "", INDEX),
    ("the Boundary column names no area", "tools/records.py", 'findall(" ".join(cells + (check,)))', "findall(check)", INDEX),
    ("a record replaced by one not there is read as one", "tools/records.py",
     "        while head in records and records[head][1]", "        while records[head][1]", INDEX),
    ("a loop of records is followed past its start", "tools/records.py", "        head, seen = rel, {rel}\n", "        head, seen = rel, set()\n", INDEX),
    ("an unread Status is live", "tools/records.py", '"unread" if replaced is None else ', "", INDEX),
    ("a file not named by a number is a record", "tools/records.py", "            if check_context.RECORD_NUMBER.match(p.name) and p.is_file()", "            if p.is_file()", INDEX),
    ("a linked docs folder is read", "tools/records.py", '(root / "docs").is_symlink() or folder.is_symlink()', "folder.is_symlink()", INDEX),
    ("a record that replaced none has a chain", "tools/records.py", "        if head != rel:\n", "        if True:\n", INDEX),
    ("chains are ordered by their names", "tools/records.py",
     "for head, olds in sorted(heads.items(), key=lambda pair: _order(pair[0]))]", "for head, olds in sorted(heads.items())]", INDEX),
    ("an empty Chains section is printed", "tools/records.py",
     '(CHAINS + "".join(chains) if chains else "")', 'CHAINS + "".join(chains)', INDEX),
    ("the index is printed empty", "tools/records.py", "    sys.stdout.write(render(root))\n", '    sys.stdout.write("")\n', INDEX),
]
