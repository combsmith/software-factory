"""The mutants of `release/current.py`: tools/mutants.py runs them."""

TARGETS = ("release/current.py",)
MUTANTS = [
    # The Release's rules (#197, PR 1).
    ('a commit two Releases name resolves to one', 'release/current.py',
     '    return found[0] if len(found) == 1 else None',
     '    return found[0] if found else None', ('tests.test_release.Current.test_a_commit_with_no_release_or_two_resolves_to_none',)),
    ('a commit that is none resolves to a Release named none', 'release/current.py',
     '    if not isinstance(commit, str):\n        return None\n',
     '', ('tests.test_release.Current.test_a_commit_with_no_release_or_two_resolves_to_none',)),
    ('a name of two parts is a Release', 'release/current.py',
     '    if len(parts) != 3 or not all(',
     '    if not all(', ('tests.test_release.Current.test_a_name_is_a_release_or_a_channel_and_never_both',)),
    ('a part with a leading zero is a number', 'release/current.py',
     ' and (part == "0" or not part.startswith("0"))',
     '', ('tests.test_release.Current.test_a_commit_with_no_release_or_two_resolves_to_none', 'tests.test_release.Current.test_a_name_is_a_release_or_a_channel_and_never_both')),
    ('a digit of another script is a number', 'release/current.py',
     ' and part.isascii() and',
     ' and', ('tests.test_release.Current.test_a_commit_with_no_release_or_two_resolves_to_none',)),
]
