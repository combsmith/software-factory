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
    ("a head behind the admitted sha is an ancestor", BASE_PY, 'if body.get("status") == AHEAD and', 'if body.get("status") in (AHEAD,) + APART and', BASE_CASES),
    ("a head apart from the admitted sha is untold", BASE_PY, '    if body.get("status") in APART:\n        return NEITHER, head\n', '', BASE_CASES),
    ("the comparison is asked the other way round", BASE_PY, '% (repo, admitted, head)', '% (repo, head, admitted)', BASE_CASES),
    # What cannot be read is none of the three.
    ("a head ahead of another merge base is an ancestor", BASE_PY, ' and base.get("sha") == admitted', '', BASE_UNREAD),
    ("a comparison of another status than 200 is read", BASE_PY, ' and answer.get("status") == 200', '', BASE_UNREAD),
    ("a comparison not read is neither", BASE_PY, '        return NEITHER, head\n    return None, head\n', '        return NEITHER, head\n    return NEITHER, head\n', BASE_UNREAD),
    ("a comparison not answered is neither", BASE_PY, '    except Unanswered:\n        return None, head\n', '    except Unanswered:\n        return NEITHER, head\n', BASE_UNREAD),
    ("a merge base of another shape is read", BASE_PY, ' if isinstance(body.get("merge_base_commit"), dict) else {}', ' or {}', BASE_UNREAD),
    # A sha or a repo told wrongly asks nothing.
    ("an admitted sha told wrongly is asked", BASE_PY, 'if not (_repo(repo) and _sha(admitted)):', 'if not _repo(repo):', BASE_TOLD),
    ("a repo told wrongly is asked", BASE_PY, 'if not (_repo(repo) and _sha(admitted)):', 'if not _sha(admitted):', BASE_TOLD),
    ("an admitted sha of another kind is read", BASE_PY, 'return type(said) is str and SHA.fullmatch', 'return isinstance(said, str) and SHA.fullmatch', BASE_TOLD),
    ("a repo of another kind is read", BASE_PY, 'return type(said) is str and REPO.fullmatch', 'return isinstance(said, str) and REPO.fullmatch', BASE_TOLD),
    ("a repo of a parent's name is read", BASE_PY, ' and said.split("/")[1] not in (".", "..")', '', BASE_TOLD),
]
