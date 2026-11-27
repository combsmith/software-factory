"""The mutants of `adapters/opening.py`: tools/mutants.py runs them."""

# The opening port's tests (issue 838, decision 0238).
OPENING_BOUNDS = ('tests.test_adapters.Opening.test_a_drafts_text_is_held_to_githubs_bounds_in_bytes_of_utf_8',)
OPENING_TOKEN = ('tests.test_adapters.Opening.test_a_roles_token_opens_one_draft_from_its_branch_to_its_base_and_reads_it_alone',)
OPENING_ONCE = ('tests.test_adapters.Opening.test_a_draft_is_opened_once_and_claimed_only_when_read_back_by_its_number',)
OPENING_RECOVERED = ('tests.test_adapters.Opening.test_a_draft_its_app_already_opened_from_the_branch_is_recovered_and_none_is_opened',)
OPENING_BACK = ('tests.test_adapters.Opening.test_an_opening_not_read_back_whole_claims_nothing_and_says_why',)
OPENING_TOLD = ('tests.test_adapters.Opening.test_an_opening_told_wrongly_sends_nothing',)
OPENING_PY = 'adapters/opening.py'

TARGETS = (OPENING_PY,)
MUTANTS = [
    # The opening port (issue 838, decision 0238): its text held to GitHub's bounds in bytes, one draft from the work
    # branch to the base through the Role's narrowed token, recovered, and claimed only as read back by its number.
    ("a title's bound is counted in characters", OPENING_PY, 'len(title.encode("utf-8")) > TITLE_MOST', 'len(title) > TITLE_MOST', OPENING_BOUNDS),
    ("a body's bound is counted in characters", OPENING_PY, 'len(body.encode("utf-8")) > BODY_MOST', 'len(body) > BODY_MOST', OPENING_BOUNDS),
    ("a title may be one byte over its bound", OPENING_PY, 'len(title.encode("utf-8")) > TITLE_MOST', 'len(title.encode("utf-8")) > TITLE_MOST + 1', OPENING_BOUNDS),
    ("a body may be one byte over its bound", OPENING_PY, 'len(body.encode("utf-8")) > BODY_MOST', 'len(body.encode("utf-8")) > BODY_MOST + 1', OPENING_BOUNDS),
    ("a lone surrogate is text", OPENING_PY, r'not any("\ud800" <= c <= "\udfff" for c in value)', 'True', OPENING_BOUNDS),
    ("text of another kind is text", OPENING_PY, 'return type(value) is str', 'return isinstance(value, str)', OPENING_BOUNDS),
    ("a draft may be opened ready", OPENING_PY, ' and body["draft"] is True', '', OPENING_TOKEN),
    ("a draft may be opened from another branch", OPENING_PY, 'body["head"] == branch and ', '', OPENING_TOKEN),
    ("a draft may be opened to another base", OPENING_PY, ' and body["base"] == base', '', OPENING_TOKEN),
    ("a draft may name more than its title, body, branches and draft", OPENING_PY, 'set(body) == {"title", "body", "head", "base", "draft"}', 'set(body) >= {"title", "body", "head", "base", "draft"}', OPENING_TOKEN),
    ("a draft past GitHub's bounds may be sent", OPENING_PY, ' and refusal(body["title"], body["body"]) is None', '', OPENING_TOKEN),
    ("a pull request's read may name more after its number", OPENING_PY, '+ NUMBER.pattern)', '+ NUMBER.pattern + ".*")', OPENING_TOKEN),
    ("a pull request's number may lead with 0", OPENING_PY, 'NUMBER = re.compile(r"[1-9][0-9]{0,18}")', 'NUMBER = re.compile(r"[0-9][0-9]{0,18}")', OPENING_TOKEN),
    ("a base of two dots is a branch", OPENING_PY, ' and ".." not in base', '', OPENING_TOKEN),
    ("a base ending in .lock is a branch", OPENING_PY, '"/", ".", ".lock"', '"/", "."', OPENING_TOKEN),
    ("a repo named .. opens a draft", OPENING_PY, ' and repo.split("/")[1] not in (".", "..")', '', OPENING_TOKEN),
    ("the pull requests from the branch are listed open alone", OPENING_PY, '&state=all&', '&state=open&', OPENING_ONCE),
    ("a pull request anyone opened is the App's", OPENING_PY, 'isinstance(user, dict) and user.get("login") == login', 'isinstance(user, dict)', OPENING_RECOVERED),
    ("a pull request from another branch is the App's", OPENING_PY, 'head.get("ref") == branch and ', '', OPENING_RECOVERED),
    ("a pull request from another repo's branch is the App's", OPENING_PY, ' and isinstance(head.get("repo"), dict) and head["repo"].get("full_name") == repo', '', OPENING_BACK),
    ("an opening already made is made again", OPENING_PY, 'state, made = ("already_applied", mine[0]) if mine else ("applied", None)', 'state, made = ("applied", None)', OPENING_RECOVERED),
    ("two openings from the branch are one", OPENING_PY, 'if len(mine) > 1:', 'if len(mine) > 2:', OPENING_BACK),
    ("a list of 100 pull requests is read whole", OPENING_PY, 'len(listed) >= LISTED', 'len(listed) > LISTED', OPENING_BACK),
    ("an opening is claimed without its read-back", OPENING_PY, 'if not (_ours(back, repo, branch, login)', 'if False and (_ours(back, repo, branch, login)', OPENING_BACK),
    ("a read-back to another base is the opening", OPENING_PY, ' and base_read.get("ref") == base', '', OPENING_BACK),
    ("a new opening read back ready is claimed", OPENING_PY, '(state == "already_applied" or back.get("draft") is True)', 'True', OPENING_BACK),
    ("a 403 does not end the opening refused", OPENING_PY, 'in (401, 403)', 'in (401,)', OPENING_BACK),
    ("an opening told wrongly is sent", OPENING_PY, 'if not _told(repo, branch, base) or refusal(title, body) is not None or type(login) is not str or not login:', 'if False:', OPENING_TOLD),
]
