#!/bin/sh
# Trial P-61 (issue 551): whether an issue's timeline gives each change of its type, and each link of a pull request by
# hand and its unlinking, as an event of its own with its time to the second and who made it; and whether the merge of
# a pull request linked by hand closes the issue, naming it the closer.
#
#   tools/trial_p61_timeline.sh OUT REPO ISSUE PULL_REQUEST
#
# The Maintainer runs it at his own terminal, through his own gh login; it mints nothing. OUT is a directory that does
# not exist yet, outside this repo. REPO is the canary, owner/name. ISSUE is an open issue in it with no type;
# PULL_REQUEST is an open pull request in it, to the default branch, ready, whose description names no issue. The
# script reads the issue's timeline, then asks the Maintainer to make one change by hand in GitHub's page, waits for
# Enter, and reads it again, step by step:
#   1. as it is;            2. a type set;          3. the type changed;     4. the type removed;
#   5. the pull request linked by hand, in the issue's Development box;      6. unlinked;
#   7. linked again;        8. the pull request merged, once the issue shows closed;   9. a minute later.
# Needs gh, logged in as the Maintainer, and python3.
#
# The pass condition, written before the run:
#   pass: each change of steps 2 to 7 appears on the issue's timeline, at the read after it, as one event of its own:
#   IssueTypeAddedEvent, IssueTypeChangedEvent, IssueTypeRemovedEvent, ConnectedEvent, DisconnectedEvent and
#   ConnectedEvent, each with a createdAt to the second, no earlier than the read before it and no later than the read
#   after, its actor's login and type, and the type or the pull request it names; the timeline is read whole at each
#   step; and by step 9 the issue is closed, its ClosedEvent's closer the pull request.
#   fail otherwise, and row 1 does not read a type or a link by hand at the merge until a trial shows what does.
#
# Each answer is captured in a scratch directory outside the repo, redacted there by tools/redact_trial.py, and deleted;
# OUT receives only the redacted answers (clean-N), where the redaction removed something (redacted-N), what was asked
# (query.json, with its variables, and steps), and when the run started (ran_at). A read that is not GitHub's 200 with
# data and no errors is said, with gh's complaint redacted, and offered again before anything changes; a bad query
# stops the run at step 1. A session builds trials/P-61.json from OUT alone.
set -euf
set +x

if [ "$#" -ne 4 ]; then
    echo "usage: tools/trial_p61_timeline.sh OUT REPO ISSUE PULL_REQUEST" >&2
    exit 2
fi
root=$(cd "$(dirname "$0")/.." && pwd -P)
# A repo and each number are one word of the shapes GitHub allows, so none reaches the query as anything else.
case "$2" in
    */*/*|/*|*/|-*|*[!A-Za-z0-9._/-]*) echo "trial_p61_timeline: $2 is not owner/name" >&2; exit 2 ;;
    combsmith/software-factory) echo "trial_p61_timeline: a trial runs in the canary, never in the Factory's own repo" >&2; exit 2 ;;
    */*) ;;
    *) echo "trial_p61_timeline: $2 is not owner/name" >&2; exit 2 ;;
esac
for number in "$3" "$4"; do
    case "$number" in
        ""|0*|*[!0-9]*) echo "trial_p61_timeline: $number is not an issue's or a pull request's number" >&2; exit 2 ;;
    esac
done
if [ -e "$1" ] || [ -L "$1" ]; then
    echo "trial_p61_timeline: $1 exists; name a new directory" >&2
    exit 2
fi
# OUT is read as the file system resolves it, every link and .. followed, before it is held to be outside the repo.
if ! parent=$(CDPATH= cd "$(dirname -- "$1")" 2>/dev/null && pwd -P); then
    echo "trial_p61_timeline: the directory that would hold $1 does not exist; make it first" >&2
    exit 2
fi
out=$parent/$(basename -- "$1")
case "$out/" in "$root"/*)
    echo "trial_p61_timeline: $out is inside the repo; name a directory outside it" >&2
    exit 2 ;;
esac
# OUT's parent, and each directory above it, is root's or this user's, and no other user can write to it unless it is
# sticky: in any other, another user could rename OUT once it is made and put a link where it was (issue 367). A find
# that fails says nothing, and is refused as such.
uid=$(id -u)
above=$parent
while :; do
    found=$(find "$above" -maxdepth 0 \( ! -user 0 ! -user "$uid" -o \( -perm -0020 -o -perm -0002 \) ! -perm -1000 \) -print) ||
        found="find failed"
    # find -perm does not see an ACL: ls -e on macOS says what one allows; elsewhere ls's + says one is there, unread.
    if listed=$(ls -lde "$above" 2>/dev/null); then
        if printf '%s\n' "$listed" | sed 1d | grep -Eq ' allow .*(add_file|add_subdirectory|delete|write|chown)'; then found="an ACL"; fi
    elif listed=$(ls -ld "$above"); then
        case "$listed" in ??????????+*) found="an ACL" ;; esac
    else
        found="ls failed"
    fi
    if [ -n "$found" ]; then
        echo "trial_p61_timeline: $above is another user's, or can be written by other users and is not sticky, or an ACL may let them; name a directory" \
            "under one only you can write to" >&2
        exit 2
    fi
    [ "$above" = / ] && break
    above=$(dirname -- "$above")
done
dir=$(mktemp -d "${TMPDIR:-/tmp}/trial-p61.XXXXXX")     # bare, macOS ignores TMPDIR
trap 'rm -rf "$dir"' EXIT
trap 'exit 1' HUP INT TERM
real=$(cd "$dir" && pwd -P)
case "$real/" in "$root"/*) echo "trial_p61_timeline: the scratch directory $real is inside the repo; set TMPDIR elsewhere" >&2; exit 2;; esac
umask 077
mkdir "$out"
owner=${2%%/*}
name=${2#*/}
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"
QUERY='query($owner:String!,$name:String!,$issue:Int!,$pr:Int!){repository(owner:$owner,name:$name){issue(number:$issue){state issueType{name} timelineItems(first:100,itemTypes:[ISSUE_TYPE_ADDED_EVENT,ISSUE_TYPE_CHANGED_EVENT,ISSUE_TYPE_REMOVED_EVENT,CONNECTED_EVENT,DISCONNECTED_EVENT,CLOSED_EVENT]){totalCount pageInfo{hasNextPage endCursor} nodes{__typename ... on IssueTypeAddedEvent{createdAt actor{__typename login} issueType{name}} ... on IssueTypeChangedEvent{createdAt actor{__typename login} issueType{name} prevIssueType{name}} ... on IssueTypeRemovedEvent{createdAt actor{__typename login} issueType{name}} ... on ConnectedEvent{createdAt actor{__typename login} source{__typename ... on Issue{number} ... on PullRequest{number}} subject{__typename ... on Issue{number} ... on PullRequest{number}}} ... on DisconnectedEvent{createdAt actor{__typename login} source{__typename ... on Issue{number} ... on PullRequest{number}} subject{__typename ... on Issue{number} ... on PullRequest{number}}} ... on ClosedEvent{createdAt actor{__typename login} closer{__typename ... on PullRequest{number}}}}}} pullRequest(number:$pr){state mergedAt closingIssuesReferences(first:10){totalCount nodes{number}}}}}'
# What is asked, word for word, with its variables, as the fixture's request keeps it.
python3 -I -c 'import json, sys; print(json.dumps({"query": sys.argv[1], "variables": {"owner": sys.argv[2], "name": sys.argv[3], "issue": int(sys.argv[4]), "pr": int(sys.argv[5])}}))' \
    "$QUERY" "$owner" "$name" "$3" "$4" > "$out/query.json"
: > "$out/steps"
step=0
# One read, kept redacted, with what the redaction removed beside it; good only if GitHub answered 200 with data and no
# errors. gh's own complaint, redacted, is shown where it is not.
read_step() {
    status=0
    gh api graphql --include -f query="$QUERY" -f owner="$owner" -f name="$name" -F issue="$3" -F pr="$4" \
        > "$dir/raw" 2> "$dir/err" || status=$?
    (cd "$root" && python3 -m tools.redact_trial < "$dir/raw" > "$out/clean-$step") 2> "$out/redacted-$step" ||
        { echo "trial_p61_timeline: the redaction of step $step failed" >&2; rm -f "$dir/raw" "$dir/err"; exit 1; }
    rm -f "$dir/raw"
    if [ "$status" -eq 0 ] && python3 -I -c '
import json, sys
text = open(sys.argv[1]).read().replace("\r\n", "\n")
head, _, body = text.partition("\n\n")
answer = json.loads(body)
sys.exit(0 if head.split(" ")[1:2] == ["200"] and not answer.get("errors") and answer.get("data") else 1)
' "$out/clean-$step" 2>/dev/null; then
        rm -f "$dir/err"
        return 0
    fi
    echo "trial_p61_timeline: step $step was not read whole; what gh said, redacted:" >&2
    (cd "$root" && python3 -m tools.redact_trial < "$dir/err") >&2 2>/dev/null || true
    rm -f "$dir/err"
    return 1
}
: > "$out/steps"
step=0
for asked in "as it is" \
             "set a type on the issue, any type the canary offers" \
             "change the issue's type to another" \
             "remove the issue's type" \
             "link the pull request to the issue by hand, in the issue's Development box" \
             "unlink it there" \
             "link it there again" \
             "merge the pull request, then wait until the issue shows closed" \
             "wait a minute more, changing nothing"; do
    step=$((step + 1))
    if [ "$step" -gt 1 ]; then
        printf 'Step %d: %s, in GitHub'"'"'s page; then press Enter here. ' "$step" "$asked" >&2
        read -r _ || { echo "trial_p61_timeline: no answer; stopped before step $step" >&2; exit 1; }
    fi
    printf '%d %s\n' "$step" "$asked" >> "$out/steps"
    # A read that fails is offered again, changing nothing: a bad query at step 1 stops the run before any change.
    until read_step "$@"; do
        printf 'Press Enter to read step %d again, or type q and Enter to stop. ' "$step" >&2
        read -r again || again=q
        [ "$again" = q ] && { echo "trial_p61_timeline: stopped at step $step" >&2; exit 1; }
    done
    echo "trial_p61_timeline: step $step read" >&2
done
echo "trial_p61_timeline: done; $out holds the redacted answers" >&2
