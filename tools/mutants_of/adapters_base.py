"""The mutants of `adapters/base.py`: tools/mutants.py runs them."""

# Where an opening admission's commit stands on the default branch at the push (issue 838, decision 0242).
BASE_CASES = ('tests.test_adapters.Base.test_the_admitted_sha_is_the_head_an_ancestor_of_it_or_neither',)
BASE_UNREAD = ('tests.test_adapters.Base.test_a_comparison_that_cannot_be_read_is_none_of_the_three',)
BASE_TOLD = ('tests.test_adapters.Base.test_a_head_or_a_sha_that_cannot_be_read_is_none_of_the_three_and_nothing_is_compared',)
BASE_PY = 'adapters/base.py'

TARGETS = (BASE_PY,)
MUTANTS = [
    # The three cases, told apart by the default branch's head and GitHub's comparison of the admitted sha with it.
    ("the default head is read as an ancestor", BASE_PY, '        return HEAD, head\n', '        return ANCESTOR, head\n', BASE_CASES),
    ("a third case goes on", BASE_PY, 'GOES_ON = (HEAD, ANCESTOR)', 'GOES_ON = (HEAD, ANCESTOR, NEITHER)', BASE_CASES),
    ("a head behind the admitted sha is untold", BASE_PY, 'status == BEHIND and base.get("sha") == head', 'False', BASE_CASES),
    ("a head apart from the admitted sha is untold", BASE_PY, 'status == APART and _sha(base.get("sha"))', 'False', BASE_CASES),
    ("the comparison is asked the other way round", BASE_PY, '% (repo, admitted, head)', '% (repo, head, admitted)', BASE_CASES),
    # What cannot be read is none of the three.
    ("a head ahead of another merge base is an ancestor", BASE_PY, ' and base.get("sha") == admitted', '', BASE_UNREAD),
    ("a comparison of another status than 200 is read", BASE_PY, ' and answer.get("status") == 200', '', BASE_UNREAD),
    ("a comparison not read is neither", BASE_PY, '        return NEITHER, head\n    return None, head\n', '        return NEITHER, head\n    return NEITHER, head\n', BASE_UNREAD),
    ("a comparison not answered is neither", BASE_PY, '    except Unanswered:\n        return None, head\n', '    except Unanswered:\n        return NEITHER, head\n', BASE_UNREAD),
    ("a head behind another merge base is neither", BASE_PY, ' and base.get("sha") == head and counts', ' and counts', BASE_UNREAD),
    ("a head apart from the admitted sha's own history is neither", BASE_PY, ' and base.get("sha") not in (admitted, head) \\\n', ' \\\n', BASE_UNREAD),
    ("a merge base of no sha beside a head apart is neither", BASE_PY, ' and _sha(base.get("sha")) and base', ' and base', BASE_UNREAD),
    ("an unread head is compared", BASE_PY, '    if not _sha(head):\n        return None, None\n', '', BASE_TOLD),
    ("an ancestor is read whatever its counts", BASE_PY, ' and base.get("sha") == admitted and counts == (True, False):', ' and base.get("sha") == admitted:', BASE_UNREAD),
    ("a head behind is read whatever its counts", BASE_PY, ' and base.get("sha") == head and counts == (False, True) \\\n', ' and base.get("sha") == head \\\n', BASE_UNREAD),
    ("a head apart is read whatever its counts", BASE_PY, '            and counts == (True, True):\n', '            and True:\n', BASE_UNREAD),
    ("a count of a bool is read", BASE_PY, 'return said > 0 if type(said) is int and', 'return said > 0 if isinstance(said, int) and', BASE_UNREAD),
    ("a count below none is read", BASE_PY, ' and said >= 0 else None', ' else None', BASE_UNREAD),
    ("an admitted sha of any letters is read", BASE_PY, 'SHA = re.compile(r"[0-9a-f]{40}")', 'SHA = re.compile(r"[0-9a-z]{40}")', BASE_TOLD),
    ("a head that shares a prefix is the head", BASE_PY, '    if head == admitted:\n', '    if head[:7] == admitted[:7]:\n', BASE_CASES),
    ("a merge base of another shape is read", BASE_PY, ' if isinstance(body.get("merge_base_commit"), dict) else {}', ' or {}', BASE_UNREAD),
    # A sha or a repo told wrongly asks nothing.
    ("an admitted sha told wrongly is asked", BASE_PY, 'if not (_repo(repo) and _sha(admitted)):', 'if not _repo(repo):', BASE_TOLD),
    ("a repo told wrongly is asked", BASE_PY, 'if not (_repo(repo) and _sha(admitted)):', 'if not _sha(admitted):', BASE_TOLD),
    ("an admitted sha of another kind is read", BASE_PY, 'return type(said) is str and SHA.fullmatch', 'return isinstance(said, str) and SHA.fullmatch', BASE_TOLD),
    ("a repo of another kind is read", BASE_PY, 'return type(said) is str and REPO.fullmatch', 'return isinstance(said, str) and REPO.fullmatch', BASE_TOLD),
    ("a repo of a parent's name is read", BASE_PY, ' and said.split("/")[1] not in (".", "..")', '', BASE_TOLD),
    ("a repo named for its own folder is read", BASE_PY, 'not in (".", "..")', 'not in ("..",)', BASE_TOLD),
]
