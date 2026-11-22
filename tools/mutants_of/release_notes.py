"""The mutants of `release/notes.py`: tools/mutants.py runs them."""

NOTES_TESTS = ("tests.test_release.Notes.test_the_notes_list_each_subject_once_under_its_area_in_the_order_merged",)

TARGETS = ("release/notes.py",)
MUTANTS = [
    # The Release's rules (#197, PR 1).
    ('no subject is notes of no change', 'release/notes.py', '    if not subjects:\n        raise ValueError', '    if False:\n        raise ValueError', NOTES_TESTS),
    ('a phrase glued to its issue is plain', 'release/notes.py', '(?:.*\\S)? \\(#[1-9]', '(?:.*\\S)? ?\\(#[1-9]', NOTES_TESTS),
    ("a subject's markup renders", 'release/notes.py', 'MENTION.sub("@\\u2060", MARKUP.sub(r"\\\\\\1", text))', 'MENTION.sub("@\\u2060", text)', NOTES_TESTS),
    ("a subject's mention notifies", 'release/notes.py', 'MENTION.sub("@\\u2060", MARKUP.sub(r"\\\\\\1", text))', 'MARKUP.sub(r"\\\\\\1", text)', NOTES_TESTS),
    ("a plain subject's markup renders", 'release/notes.py', '.append("%s (#%s)" % (literal(plain.group("change")), plain.group("pull")))', '.append("%s (#%s)" % (plain.group("change"), plain.group("pull")))', NOTES_TESTS),
    ("another subject's markup renders", 'release/notes.py', '            other.append(literal(subject.strip()))\n', '            other.append(subject.strip())\n', NOTES_TESTS),
    ('a carriage return is a line of its own', 'release/notes.py', 'BREAKS = ("\\r", ', 'BREAKS = (', NOTES_TESTS),
    ('stdin is split at every kind of break', 'release/notes.py', '.read().split("\\n")', '.read().splitlines()', NOTES_TESTS),
    ('a refusal is printed in the notes', 'release/notes.py', '        print("release notes: %s" % err, file=sys.stderr)\n', '        print("release notes: %s" % err)\n', NOTES_TESTS),
    ("the module's exit is not main's", 'release/notes.py', '    sys.exit(main())\n', '    main()\n', NOTES_TESTS),
    ('the count is of the plain subjects alone', 'release/notes.py', '    count = len(subjects)\n', '    count = sum(len(changes) for changes in areas.values())\n', NOTES_TESTS),
    ('a character reference renders', 'release/notes.py', 'MARKUP = re.compile(r"([\\\\`*_<>\\[\\]~|!&])")', 'MARKUP = re.compile(r"([\\\\`*_<>\\[\\]~|!])")', NOTES_TESTS),
    ("a subject's block opening renders", 'release/notes.py', 'return ORDERED.sub(r"\\1\\\\\\2", BLOCK.sub(r"\\1\\\\\\2", MENTION.sub(', 'return ORDERED.sub(r"\\1\\\\\\2", (MENTION.sub(', NOTES_TESTS),
    ("a numbered item's mark renders", 'release/notes.py', 'return ORDERED.sub(r"\\1\\\\\\2", BLOCK.sub(', 'return (BLOCK.sub(', NOTES_TESTS),
    ("a heading's mark renders at a subject's start", 'release/notes.py', 'BLOCK = re.compile(r"^([ \\t]*)([-+=>#])")', 'BLOCK = re.compile(r"^([ \\t]*)([-+=>])")', NOTES_TESTS),
    ("an area's heading renders", 'release/notes.py', '        lines += ["", "### %s" % literal(area), ""]', '        lines += ["", "### %s" % area, ""]', NOTES_TESTS),
    ("an issue's number is escaped as markup", 'release/notes.py', 'MARKUP = re.compile(r"([\\\\`*_<>\\[\\]~|!&])")', 'MARKUP = re.compile(r"([\\\\`*_<>\\[\\]~|!&#])")', NOTES_TESTS),
    ('a subject in the plain form is listed with the others', 'release/notes.py', '        if plain:\n', '        if False:\n', NOTES_TESTS),
    ('areas are listed in the order they came', 'release/notes.py', '    for area in sorted(areas):\n', '    for area in areas:\n', NOTES_TESTS),
    ('an area may start with a capital in the notes', 'release/notes.py', '(?P<area>[a-z0-9.][a-z0-9._/-]*)', '(?P<area>[A-Za-z0-9.][a-z0-9._/-]*)', NOTES_TESTS),
    ('a subject with no issue is listed under its area', 'release/notes.py', '(?P<change>\\S(?:.*\\S)? \\(#[1-9][0-9]*(?:, part [0-9]+ of [0-9]+)?\\))', '(?P<change>\\S(?:.*\\S)?)', NOTES_TESTS),
    ('a subject with no pull request is listed under its area', 'release/notes.py', 'r" \\(#(?P<pull>[1-9][0-9]*)\\)")', 'r"(?: \\(#(?P<pull>[1-9][0-9]*)\\))?")', NOTES_TESTS),
    ("the other changes' heading is printed with none", 'release/notes.py', '    if other:\n', '    if True:\n', NOTES_TESTS),
    ('one change is said as many', 'release/notes.py', '"" if count == 1 else "s"', '"s"', NOTES_TESTS),
    ('notes are made for a name that is no Release', 'release/notes.py', '    if not current.version(release) or not current.version(previous):\n', '    if False:\n', NOTES_TESTS),
    ('notes are made for the Release before alone', 'release/notes.py', '    if not current.version(release) or not current.version(previous):\n', '    if not current.version(previous):\n', NOTES_TESTS),
    ('a subject of two lines is read', 'release/notes.py', ' or any(b in subject for b in BREAKS):\n', ':\n', NOTES_TESTS),
    ('a blank subject is read', 'release/notes.py', ' or not subject.strip() or', ' or', NOTES_TESTS),
    ("a subject's surrounding spaces are kept", 'release/notes.py', 'PLAIN.fullmatch(subject.strip())', 'PLAIN.fullmatch(subject)', NOTES_TESTS),
    ('blank lines on stdin are subjects', 'release/notes.py', ' if line.strip()]\n', ']\n', NOTES_TESTS),
    ("the desk's command passes what it cannot make notes of", 'release/notes.py', '        return 1\n', '        return 0\n', NOTES_TESTS),
    ("the desk's command takes one name", 'release/notes.py', '    if len(args) != 2:\n', '    if len(args) < 1:\n', NOTES_TESTS),
]
