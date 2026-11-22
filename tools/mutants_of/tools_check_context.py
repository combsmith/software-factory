"""The mutants of `tools/check_context.py`: tools/mutants.py runs them."""

from tools.mutants_of.common import NAMED_MUTANTS

BARE_TESTS = ("tests.test_tools.Context.test_a_check_names_a_test_never_a_file_of_tests",)

TARGETS = ("tools/check_context.py",)
MUTANTS = [
    # Issue 146: the install is held whole, its version and checksum to their shapes, and every checkout to CHECKOUT.
    ('a title that names nothing passes', 'tools/check_context.py', '    problems = [] if re.search(r"[a-z0-9]", _slug(title)) else ["docs/decisions/%s: the title names nothing" % name]\n', '    problems = []\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ("a title's trailing spaces are counted", 'tools/check_context.py', '[len("# %s. " % digits):].rstrip()\n', '[len("# %s. " % digits):]\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('a name keeps a trailing dash', 'tools/check_context.py', 'title.lower()).strip())', 'title.lower()))', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('a name keeps a leading dash', 'tools/check_context.py', 'title.lower()).strip())', 'title.lower()).rstrip())', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('a record padded with zeros is held to nothing', 'tools/check_context.py', 'FIRST_SHORT and text.startswith("# %s. " % named.group(1)):', 'FIRST_SHORT and text.startswith("# %04d. " % number):', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('a title of dashes names something', 'tools/check_context.py', 'if re.search(r"[a-z0-9]", _slug(title)) else', 'if _slug(title) else', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ("a title's leading spaces are not counted", 'tools/check_context.py', '[len("# %s. " % digits):].rstrip()\n', '[len("# %s. " % digits):].strip()\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('adjacent dashes in a title are folded', 'tools/check_context.py', 'return re.sub(r" +", "-",', 'return re.sub(r"[ -]+", "-",', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ("a new record's title may be of any length", 'tools/check_context.py', '    if len(title) > RECORD_TITLE:\n', '    if False:\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ("a new record's title of 72 characters refuses", 'tools/check_context.py', '    if len(title) > RECORD_TITLE:\n', '    if len(title) >= RECORD_TITLE:\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ("a new record's file may be named anything", 'tools/check_context.py', '    if name != "%s-%s.md" % (digits, _slug(title)):\n', '    if False:\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('a record before the first short one is held to it', 'tools/check_context.py', '        if named and number >= FIRST_SHORT and text.startswith("# %s. " % named.group(1)):\n', '        if named and number >= FIRST_SHORT - 1 and text.startswith("# %s. " % named.group(1)):\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('the first short record is held to nothing', 'tools/check_context.py', '        if named and number >= FIRST_SHORT and text.startswith("# %s. " % named.group(1)):\n', '        if named and number > FIRST_SHORT and text.startswith("# %s. " % named.group(1)):\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('a dropped character leaves a dash', 'tools/check_context.py', 're.sub(r"[^a-z0-9 -]", "", title.lower())', 're.sub(r"[^a-z0-9 -]", "-", title.lower())', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('a name may keep its capitals', 'tools/check_context.py', 're.sub(r"[^a-z0-9 -]", "", title.lower())', 're.sub(r"[^A-Za-z0-9 -]", "", title)', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('the file of a short title is named by the whole first line', 'tools/check_context.py', '    title = text.split("\\n", 1)[0][len("# %s. " % digits):].rstrip()\n', '    title = text.split("\\n", 1)[0].rstrip()\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ('the first short record is another', 'tools/check_context.py', 'FIRST_SHORT = 245\n', 'FIRST_SHORT = 246\n', ("tests.test_tools.Context.test_a_new_records_title_is_short_and_names_its_file",)),
    ("the workflow the standard copies counts toward its page", "tools/check_context.py",
     '        copied = COPIED.search(text) if name == "workflows" else None\n', "        copied = None\n",
     ("tests.test_tools.Context",)),
    ("a yaml block on any standard is not counted toward its page", "tools/check_context.py",
     'COPIED.search(text) if name == "workflows" else None', "COPIED.search(text)", ("tests.test_tools.Context",)),
    # Issue 191: the one transport, and the facts of a pull request its own reads give.
    ("a planned file's name keeps the sentence's stop", 'tools/check_context.py',
     '    words = (word.strip(".") for word in FILE_WORD.findall(found.group(1))) if found else ()\n',
     '    words = (word for word in FILE_WORD.findall(found.group(1))) if found else ()\n', ('tests.test_tools.Context',)),
    # Asked once the issues are listed, as a pass that read their Runs would: `listed` exists only after the records are read.
    ('a planned file never arrives', 'tools/check_context.py',
     '        return (root / path).exists()\n    return (root / top).exists()\n',
     '        return False\n    return (root / top).exists()\n', ('tests.test_tools.Context',)),
    ('a wait on any file in a built directory holds', 'tools/check_context.py',
     '    if rest and (root / top).is_dir() and rest in _planned_files(root, top):\n',
     '    if rest and (root / top).is_dir():\n', ('tests.test_tools.Context',)),
    ('a directory plans no file', 'tools/check_context.py',
     '    return {word for word in words if "." in word}\n',
     '    return set()\n', ('tests.test_tools.Context',)),
    # Issue 590: a check names a test, never a file of tests, and a row names the mutant its own tests kill.
    ('a file of tests holds a rule', 'tools/check_context.py',
     '        if not test:\n            problems.append(', '        if False:\n            problems.append(', BARE_TESTS),
    ('a test file written another way holds a rule', 'tools/check_context.py',
     '        if rel.parts[0] != "tests":\n', '        if token.split("/")[0] != "tests":\n', BARE_TESTS),
    ('an empty test name is a test', 'tools/check_context.py',
     '        if not test:\n', '        if "::" not in token:\n', BARE_TESTS),
    ('a helper is a test', 'tools/check_context.py',
     '        elif not test.split(".")[-1].startswith("test"):\n', '        elif False:\n', BARE_TESTS),
    ("a test of another class's name is read as pending", 'tools/check_context.py',
     '    for cls in classes:\n        found = re.search(', '    for cls in []:\n        found = re.search(', NAMED_MUTANTS),
    # Decision 1121: a decision record takes the number of the pull request that adds it, one at most; no two share one.
    ("two records may share a number", "tools/check_context.py", "        elif number in seen:\n", "        elif False:\n", ("tests.test_tools.Context.test_no_two_records_share_a_number",)),
    ("a record's number is read as written, not as a number", "tools/check_context.py",
     "        number = int(named.group(1)) if named else None\n", "        number = named.group(1) if named else None\n", ("tests.test_tools.Context.test_no_two_records_share_a_number",)),
    ("a record may be numbered in three digits", "tools/check_context.py",
     'RECORD_NUMBER = re.compile(r"^([0-9]{4,})-")', 'RECORD_NUMBER = re.compile(r"^([0-9]{3,})-")', ("tests.test_tools.Context.test_no_two_records_share_a_number",)),
    ("a record of five digits is refused", "tools/check_context.py",
     'RECORD_NUMBER = re.compile(r"^([0-9]{4,})-")', 'RECORD_NUMBER = re.compile(r"^([0-9]{4})-")', ("tests.test_tools.Context.test_no_two_records_share_a_number",)),
    ("a title need not open with its file's number", "tools/check_context.py",
     '        if named is None or not text.startswith("# %s. " % named.group(1)):\n', "        if named is None:\n", ("tests.test_tools.Context.test_no_two_records_share_a_number",)),
    # The security pass on #392: what a YAML reader reads otherwise than the lines do is not the narrow form.
    ("the copied block runs to the last fence", "tools/check_context.py",
     'COPIED = re.compile(r"```yaml\\n.*?```", re.S)', 'COPIED = re.compile(r"```yaml\\n.*```", re.S)',
     ("tests.test_tools.Context.test_a_standard_over_one_page_is_caught",)),
    # Issue 369: a title is looked for from the first opening quote of a run alone, so a line of them is read in time.
    ("every opening quote is tried for a title", "tools/check_context.py",
     'TITLE = re.compile(r"(?:\\"|(?:^|(?<=[”\\n]))[^\\"“”\\n]*“)[^\\"”\\n]{8,}[\\"”]")',
     'TITLE = re.compile(r"[\\"“][^\\"”\\n]{8,}[\\"”]")',
     ("tests.test_tools.Context.test_a_line_of_unclosed_quotes_is_read_in_time_and_a_title_is_found_as_before",)),
    ("a title after a new line is not looked for", "tools/check_context.py", '(?:^|(?<=[”\\n]))', '(?:^|(?<=[”]))',
     ("tests.test_tools.Context.test_a_line_of_unclosed_quotes_is_read_in_time_and_a_title_is_found_as_before",)),
]
