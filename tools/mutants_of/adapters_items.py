"""The mutants of `adapters/items.py`: tools/mutants.py runs them."""

from tools.mutants_of.common import S3_ENTRY, S3_LINKED

S3_LIST = ("tests.test_adapters.Items.test_open_issues_are_listed_from_served_from_by_the_same_pages_and_none_with_no_date",)

TARGETS = ("adapters/items.py",)
MUTANTS = [
    # #196 PR 2a: the pass's entry, its reads and the pass record's bound.
    ('a count that moved is whole', 'adapters/items.py',
     '        whole = whole and total == count\n',
     '', ('tests.test_adapters.Items.test_open_pull_requests_are_whole_only_if_each_was_read',)),
    ('a pull request read twice is whole', 'adapters/items.py',
     ' and len(set(numbers)) == len(numbers)',
     '', ('tests.test_adapters.Items.test_open_pull_requests_are_whole_only_if_each_was_read',)),
    ('fewer read than counted is whole', 'adapters/items.py',
     '    return numbers, whole and len(numbers) == count and',
     '    return numbers, whole and', ('tests.test_adapters.Items.test_open_pull_requests_are_whole_only_if_each_was_read',)),
    ('a page past the most read is whole', 'adapters/items.py',
     '    else:\n        return numbers, False\n    return numbers, whole',
     '    return numbers, whole', ('tests.test_adapters.Items.test_open_pull_requests_are_whole_only_if_each_was_read',)),
    ('a next page with no cursor is whole', 'adapters/items.py',
     '        if not isinstance(after, str) or not after:\n            return numbers, False\n',
     '', ('tests.test_adapters.Items.test_open_pull_requests_are_whole_only_if_each_was_read',)),
    ('a number that is no number is read', 'adapters/items.py',
     '            if type(number) is not int or number < 1:\n                return numbers, False\n',
     '', ('tests.test_adapters.Items.test_open_pull_requests_are_whole_only_if_each_was_read',)),
    ("another repo's pull requests are read", 'adapters/items.py',
     ' or found.get("nameWithOwner") != repo',
     '', ('tests.test_adapters.Items.test_open_pull_requests_of_another_repo_or_with_errors_are_refused',)),
    ('an answer with errors is read', 'adapters/items.py',
     ' and "errors" not in body',
     '', ('tests.test_adapters.Items.test_open_pull_requests_of_another_repo_or_with_errors_are_refused',)),
    # S3: the open issues are listed from `issues.served_from` and each read by the issues port, whose facts reach the
    # Kernel through the pass; an App is named by the id the configuration holds (the Factory Builder's ruling A).
    ('open issues are listed whatever their last update', 'adapters/items.py',
     'filterBy: {since: $since}, ',
     '', S3_LIST),
    ('open issues are listed with no date asked', 'adapters/items.py',
     '"after": after, "since": asked}',
     '"after": after}', S3_LIST),
    ('with no date, open issues are asked for', 'adapters/items.py',
     '    if since is None:\n        return [], True\n',
     '', S3_LIST + S3_ENTRY),
    ('open issues are asked from served_from itself', 'adapters/items.py',
     ' - datetime.timedelta(seconds=1)',
     '', S3_LIST),
    ('a served_from that is no time is asked', 'adapters/items.py',
     '    except (TypeError, ValueError, OverflowError):\n        raise Unanswered("issues.served_from is no time")',
     '    except ZeroDivisionError:\n        raise Unanswered("issues.served_from is no time")', S3_LIST),
    ('a served_from a second past the first time is asked', 'adapters/items.py',
     '    except (TypeError, ValueError, OverflowError):\n',
     '    except (TypeError, ValueError):\n', S3_LIST),
    # Issues 963 and 965, the reader audits of #918 and #912: each issue's read dated by its own answer, the issues'
    # configuration left as written and its Apps named plain, and every account held to the names an App's id holds.
    ('a served_from that is no text crashes the pass', 'adapters/items.py',
     '    except (TypeError, ValueError, OverflowError):\n        raise Unanswered("issues.served_from',
     '    except (ValueError, OverflowError):\n        raise Unanswered("issues.served_from', S3_LIST),
    ('a served_from that is false or zero lists no issue', 'adapters/items.py',
     '    if since is None:\n        return [], True\n',
     '    if not since:\n        return [], True\n', S3_LIST),
    # Decision 0235: an issue a pass served that has left is read with its close, and one read short is owed (issue 916).
    # An issue that left is read first by its state: open needs no close, 404 or 410 ends it where its repo was read.
    ('the tracking issue is listed as an open issue', 'adapters/items.py',
     'return [number for number in numbers if number not in apart], whole',
     'return numbers, whole', S3_LIST + S3_LINKED),
    ("only the first tracking issue's number is left out of the listing", 'adapters/items.py',
     'if number not in apart]', 'if number not in apart[:1]]', S3_LIST),
]
