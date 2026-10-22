#!/usr/bin/env bash
# What the Factory's Apps write for the second machine-user window's trials (design, section 6: P-2, P-5, P-23, P-25,
# P-41, P-42; issues 185 and 250), at the Maintainer's own terminal and nowhere else. No session and no workflow runs
# this. Each action is one App's, and no App runs another's:
#
#   bash tools/trial_window2.sh trial-author comments KEY REPO PR FILE COUNT   # one review, COUNT threads on FILE's line 1
#   bash tools/trial_window2.sh pr-review enqueue KEY REPO PR                  # enqueuePullRequest
#   bash tools/trial_window2.sh pr-review automerge KEY REPO PR                # enablePullRequestAutoMerge, squash
#   bash tools/trial_window2.sh pr-review dequeue KEY REPO PR PERMISSIONS      # dequeuePullRequest, the token narrowed
#   bash tools/trial_window2.sh pr-review resolve KEY REPO PR                  # every open thread another opened
#   bash tools/trial_window2.sh pr-review burst KEY REPO PR                     # every open thread the trial-author opened,
#                                                                               # one after another, as fast as answered
#   bash tools/trial_window2.sh pr-review dismiss KEY REPO PR REVIEW           # a review, dismissed
#   bash tools/trial_window2.sh pr-review check KEY REPO SHA NAME              # a check run, completed and successful
#   bash tools/trial_window2.sh controller queue KEY REPO PR PERMISSIONS       # the queue read, and the pull request's
#                                                                               # issue and review comments (#306), narrowed
#   bash tools/trial_window2.sh controller label KEY REPO PR LABEL             # a label added, then removed
#   bash tools/trial_window2.sh controller issue-comments KEY REPO N PERMISSIONS # an issue's comments since a time (#306)
#
# PERMISSIONS narrows the token to exactly those, as name=level separated by commas (pull_requests=write,metadata=read),
# so that a trial names the least permission a call needs. KEY is the path of that App's private key: only openssl
# opens it, to sign. One installation token is minted for REPO's installation; no command line ever holds it; it is
# revoked before the script exits, on a failure too. OUT, a new scratch directory outside this repo, keeps only what
# tools/redact_trial.py let through, and exchanges.json; the script prints it. A refusal by GitHub is an answer, kept
# as it came: only a failure to ask, or to revoke, fails the run.
set -euo pipefail
set +x
unset GH_DEBUG DEBUG CURL_HOME
export GH_HOST=github.com GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1

API=https://api.github.com
VERSION=2022-11-28
ACCEPT=application/vnd.github+json

usage() {
    sed -n '7,16p' "${BASH_SOURCE[0]}" | sed 's/^#  //' >&2
    exit 2
}
[ "$#" -ge 5 ] || usage
who=$1 action=$2 key=$3 repo=$4 target=$5
shift 5
case "$who/$action/$#" in
    trial-author/comments/2|pr-review/enqueue/0|pr-review/automerge/0|pr-review/dequeue/1|pr-review/resolve/0) ;;
    pr-review/burst/0|pr-review/dismiss/1|pr-review/check/1|controller/queue/1|controller/label/1|controller/issue-comments/1) ;;
    *) usage ;;
esac
case "$repo" in */*/*|/*|*/) usage ;; */*) ;; *) usage ;; esac
if [ "$action" = check ]; then
    case "$target" in [0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;; *) usage ;; esac
    case "$target" in *[!0-9a-f]*) usage ;; esac
    [ "${#target}" -eq 40 ] || usage
else
    case "$target" in ""|*[!0-9]*) usage ;; esac
fi
narrow=""
case "$action" in
    comments) file=$1 count=$2
        case "$file" in ""|/*|*..*|*" "*) echo "FILE is a path in the pull request's head" >&2; exit 2 ;; esac
        case "$count" in ""|*[!0-9]*) usage ;; esac
        [ "$count" -ge 1 ] && [ "$count" -le 50 ] || { echo "COUNT is 1 to 50" >&2; exit 2; } ;;
    dequeue|queue|issue-comments) narrow=$1
        case "$narrow" in ""|*[!a-z_=,]*) usage ;; esac ;;
    dismiss) review=$1
        case "$review" in ""|*[!0-9]*) usage ;; esac ;;
    check) name=$1
        case "$name" in ""|*[!A-Za-z0-9\ /_.:-]*) echo "NAME is a check's name: letters, digits, space, / _ . : -" >&2; exit 2 ;; esac ;;
    label) label=$1
        case "$label" in ""|*[!A-Za-z0-9:_.-]*) echo "LABEL is letters, digits and : _ . -" >&2; exit 2 ;; esac ;;
esac
[ -f "$key" ] && [ -r "$key" ] || { echo "no readable file at the key's path" >&2; exit 2; }
for tool in curl openssl gh python3; do
    command -v "$tool" >/dev/null || { echo "$tool is needed" >&2; exit 2; }
done

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[ -f "$root/tools/redact_trial.py" ] || { echo "run the copy of this script in a checkout of software-factory" >&2; exit 2; }
# The App's name and id: the trial-author App's are its own; the Factory's Apps' are config/apps.json's.
if [ "$who" = trial-author ]; then
    APP=combsmith-sf-trial-author APP_ID=5363178
else
    said=$(cd "$root" && python3 -I -c '
import json, sys
app = json.load(open("config/apps.json"))["apps"][sys.argv[1]]
print(app["name"], app["app_id"])' "$who")
    APP=${said% *} APP_ID=${said#* }
fi
out=$(cd "$(mktemp -d)" && pwd -P)
case "$out/" in "$root"/*) echo "the scratch directory is inside the repo" >&2; exit 2 ;; esac

jwt="" token="" n=0 id="" raw=""

# The value at a dotted path of the JSON body of a redacted capture.
value() {
    python3 -I -c '
import json, sys
text = open(sys.argv[1]).read()
head, gap, body = text.partition("\n\n")
data = json.loads(body if gap else text)
for key in sys.argv[2].split("."):
    data = data[int(key)] if isinstance(data, list) else data[key]
print(data)' "$1" "$2"
}

# The next exchange: what was asked, written down here, never the credential that asked it.
record() {   # CALL WHO BODY [VIA]
    n=$((n + 1))
    id=$(printf '%02d' "$n")
    raw="$out/$id.raw"
    python3 -I -c '
import json, sys
call, who, body, version, accept, path, via = sys.argv[1:8]
json.dump({"as": {"kind": "app", "name": who}, "via": via, "call": call,
           "headers": {"accept": accept, "x-github-api-version": version, "authorization": "not recorded"},
           "body": json.loads(body) if body else None}, open(path, "w"), indent=2)' \
        "$1" "$2" "$3" "$VERSION" "$ACCEPT" "$out/$id.request.json" "${4:-rest}"
}

# A raw capture, redacted beside it and then deleted; a capture whose redaction fails is deleted unread.
redact() {   # RAW
    local failed=0
    (cd "$root" && python3 -m tools.redact_trial < "$1" 2>&1 > "${1%.raw}.clean") | sed "s|^|$(basename "${1%.raw}"): |" ||
        failed=1
    rm -f "$1"
    if [[ "$failed" -ne 0 ]]; then
        rm -f "${1%.raw}.clean"
        echo "trial_window2: the redaction of $(basename "${1%.raw}") failed; its capture is deleted unread" >&2
        return 1
    fi
}

# The status line of the last answer.
answered() { sed -n 1p "$out/$id.clean" 2>/dev/null | cut -d' ' -f2; }

# As the App itself, by its JWT: the header goes to curl on its standard input, never as an argument.
as_app() {   # METHOD PATH
    record "$1 /$2" "$APP, by its JWT" ""
    printf 'Authorization: Bearer %s\n' "$jwt" |
        curl -q -sS -i --fail-with-body -X "$1" -H @- -H "Accept: $ACCEPT" \
            -H "X-GitHub-Api-Version: $VERSION" "$API/$2" | tr -d '\r' > "$raw"
    redact "$raw"
}

# As the App's installation: gh reads the token from its environment, never from an argument. A refusal is kept.
as_installation() {   # METHOD PATH [BODY]
    record "$1 /$2" "${APP}[bot], by an installation token" "${3:-}"
    if [ -n "${3:-}" ]; then
        printf '%s' "$3" | GH_TOKEN="$token" gh api --include -X "$1" -H "Accept: $ACCEPT" \
            -H "X-GitHub-Api-Version: $VERSION" "$2" --input - 2>/dev/null | tr -d '\r' > "$raw" || true
    else
        GH_TOKEN="$token" gh api --include -X "$1" -H "Accept: $ACCEPT" \
            -H "X-GitHub-Api-Version: $VERSION" "$2" 2>/dev/null | tr -d '\r' > "$raw" || true
    fi
    redact "$raw"
}

# A GraphQL call as the installation, its variables passed apart from the query and recorded with it. WHAT says what it
# is: a read, or which write. A refusal is kept.
as_graphql() {   # WHAT QUERY NAME=VALUE...
    local what=$1 query=$2
    shift 2
    local -a args=()
    local pair
    for pair in "$@"; do
        case "${pair#*=}" in *[!0-9]*|"") args+=(-f "$pair") ;; *) args+=(-F "$pair") ;; esac
    done
    record "POST /graphql (gh api graphql): $what" "${APP}[bot], by an installation token" \
        "$(python3 -I -c '
import json, sys
variables = {}
for pair in sys.argv[2:]:
    name, value = pair.split("=", 1)
    variables[name] = int(value) if value.isdigit() else value
print(json.dumps({"query": sys.argv[1], "variables": variables}))' "$query" "$@")" graphql
    GH_TOKEN="$token" gh api graphql --include -f query="$query" "${args[@]}" 2>/dev/null | tr -d '\r' > "$raw" || true
    redact "$raw"
}

# Revoke the token first, whatever happened; then redact what is left and gather the exchanges.
finish() {
    status=$?
    trap - EXIT INT TERM
    set +e
    if [ -n "$token" ]; then
        as_installation DELETE installation/token
        [ "$(answered)" = 204 ] ||
            { echo "THE TOKEN WAS NOT REVOKED: it lapses within the hour; say so to the session" >&2; status=1; }
    fi
    token="" jwt=""
    unset token jwt
    for left in "$out"/*.raw; do
        [[ -e "$left" ]] && { redact "$left" || status=1; }
    done
    python3 -I -c '
import json, pathlib, sys
out, exchanges = pathlib.Path(sys.argv[1]), []
for asked in sorted(p for p in out.iterdir() if p.name.endswith(".request.json")):
    clean = out / asked.name.replace(".request.json", ".clean")
    text = clean.read_text() if clean.exists() else ""
    head, gap, body = text.partition("\n\n")
    lines = head.splitlines() if gap else []
    body = body if gap else text
    status = lines[0].split()[1] if lines and len(lines[0].split()) > 1 else None
    headers = {}
    for line in lines[1:]:
        name, _, said = line.partition(":")
        headers[name.strip().lower()] = said.strip()
    try:
        body = json.loads(body) if body.strip() else None
    except ValueError:
        pass
    exchanges.append({"request": json.load(open(str(asked))),
                      "response": {"status": int(status) if status and status.isdigit() else status,
                                   "headers": headers, "body": body}})
json.dump({"exchanges": exchanges}, open(str(out / "exchanges.unchecked.json"), "w"), indent=2)' "$out"
    (cd "$root" && python3 -m tools.redact_trial < "$out/exchanges.unchecked.json" > "$out/exchanges.json") 2> /dev/null ||
        { echo "trial_window2: the redaction of the exchanges failed" >&2; exit 1; }
    rm -f "$out/exchanges.unchecked.json"
    echo "Done, status $status. Give the session this directory; it reads only exchanges.json and the .clean files:"
    echo "  $out"
    exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '=\n'; }

now=$(date +%s)
header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
claims=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$((now - 60))" "$((now + 540))" "$APP_ID" | b64url)
signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
jwt="$header.$claims.$signature"
unset header claims signature

as_app GET "repos/$repo/installation"
installation=$(value "$out/$id.clean" id)

# The token, minted for REPO alone, narrowed to PERMISSIONS where an action gives them: python keeps it apart from what
# is written, and hands it to this shell alone.
mint=$(python3 -I -c '
import json, sys
body = {"repositories": [sys.argv[1].split("/", 1)[1]]}
if sys.argv[2]:
    body["permissions"] = dict(pair.split("=", 1) for pair in sys.argv[2].split(","))
print(json.dumps(body))' "$repo" "$narrow")
record "POST /app/installations/$installation/access_tokens" "$APP, by its JWT" "$mint"
token=$(printf 'Authorization: Bearer %s\n' "$jwt" |
    curl -q -sS -i -X POST -H @- -H "Accept: $ACCEPT" -H "X-GitHub-Api-Version: $VERSION" --data-binary "$mint" \
        "$API/app/installations/$installation/access_tokens" |
    python3 -I -c '
import json, sys
text = sys.stdin.read().replace("\r\n", "\n")
head, gap, body = text.rpartition("\n\n")
try:
    data = json.loads(body)
except ValueError:
    data = None
token = data.pop("token", "") if isinstance(data, dict) else ""
with open(sys.argv[1], "w") as kept:
    kept.write(head + "\n\n" + (json.dumps(data) if data is not None else body))
sys.stdout.write(token)' "$raw")
redact "$raw"
jwt=""
[ -n "$token" ] || { echo "no installation token was minted: GitHub's answer is in OUT" >&2; exit 1; }

owner=${repo%%/*} name=${repo#*/}
# The time #306's reconciliation reads comments since: before the canary existed, so every comment is listed.
SINCE=2026-01-01T00:00:00Z

# A pull request's node id, read by REST and held to GitHub's shape, so that nothing else is sent as one.
node_of() {   # PR
    as_installation GET "repos/$repo/pulls/$1"
    python3 -I -c '
import json, re, sys
text = open(sys.argv[1]).read()
head, gap, body = text.partition("\n\n")
said = str(json.loads(body if gap else text)["node_id"])
if not re.fullmatch(r"PR_[A-Za-z0-9_-]{1,100}", said):
    sys.exit("the node id of the pull request does not have the shape of one")
print(said)' "$out/$id.clean"
}

THREADS='query($owner: String!, $name: String!, $pr: Int!) { repository(owner: $owner, name: $name) { pullRequest(number: $pr) { reviewThreads(first: 100) { totalCount pageInfo { hasNextPage } nodes { id isResolved resolvedBy { login __typename } comments(first: 1) { nodes { databaseId author { login __typename } body } } } } } } }'
RESOLVE='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id isResolved resolvedBy { login __typename } } } }'

# The node ids of the open threads on PR whose first comment's author is, or is not, AUTHOR, in the read FILE, each
# held to GitHub's shape.
open_threads() {   # FILE AUTHOR is|not
    python3 -I -c '
import json, re, sys
text = open(sys.argv[1]).read()
head, gap, body = text.partition("\n\n")
threads = json.loads(body if gap else text)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
for node in threads:
    first = (node["comments"]["nodes"] or [{}])[0]
    login = (first.get("author") or {}).get("login")
    mine = login == sys.argv[2]
    if node["isResolved"] or mine != (sys.argv[3] == "is"):
        continue
    if not re.fullmatch(r"PRRT_[A-Za-z0-9_-]{1,100}", str(node["id"])):
        sys.exit("a thread id does not have the shape of one")
    print(node["id"])' "$1" "$2" "$3"
}

case "$action" in
comments)
    as_installation GET "repos/$repo/pulls/$target"
    [ "$(value "$out/$id.clean" state)" = open ] || { echo "pull request $target is not open" >&2; exit 1; }
    as_installation POST "repos/$repo/pulls/$target/reviews" "$(python3 -I -c '
import json, sys
path, count, pr = sys.argv[1], int(sys.argv[2]), sys.argv[3]
print(json.dumps({"event": "COMMENT", "body": "A platform trial: %d review threads, opened by the trial-author App." % count,
                  "comments": [{"path": path, "line": 1, "side": "RIGHT",
                                "body": "Trial thread %d of %d, pull request %s." % (n, count, pr)}
                               for n in range(1, count + 1)]}))' "$file" "$count" "$target")"
    echo "pull request $target: review answered $(answered)" ;;
enqueue)
    node=$(node_of "$target")
    as_graphql "enqueuePullRequest, the App's write, on $repo's pull request $target" \
        'mutation($id: ID!) { enqueuePullRequest(input: {pullRequestId: $id}) { mergeQueueEntry { id state position } } }' "id=$node"
    echo "pull request $target: enqueue answered $(answered)" ;;
automerge)
    node=$(node_of "$target")
    as_graphql "enablePullRequestAutoMerge, the App's write, on $repo's pull request $target" \
        'mutation($id: ID!) { enablePullRequestAutoMerge(input: {pullRequestId: $id, mergeMethod: SQUASH}) { pullRequest { number autoMergeRequest { enabledBy { login __typename } mergeMethod } } } }' "id=$node"
    echo "pull request $target: auto-merge answered $(answered)" ;;
dequeue)
    node=$(node_of "$target")
    as_graphql "dequeuePullRequest, the App's write, on $repo's pull request $target, the token narrowed to $narrow" \
        'mutation($id: ID!) { dequeuePullRequest(input: {id: $id}) { mergeQueueEntry { id state } } }' "id=$node"
    echo "pull request $target: dequeue answered $(answered)" ;;
queue)
    as_graphql "the merge queue of $repo's main and pull request $target's place in it, the token narrowed to $narrow" \
        'query($owner: String!, $name: String!, $pr: Int!) { repository(owner: $owner, name: $name) { mergeQueue(branch: "main") { entries(first: 20) { totalCount nodes { position state pullRequest { number } } } } pullRequest(number: $pr) { isInMergeQueue mergeQueueEntry { position state } } } }' \
        "owner=$owner" "name=$name" "pr=$target"
    echo "pull request $target: queue read answered $(answered)"
    # Issue 306's reads, under the same narrowed token: the pull request's issue comments and its review comments.
    as_installation GET "repos/$repo/issues/$target/comments?since=$SINCE&per_page=100"
    echo "pull request $target: issue comments answered $(answered)"
    as_installation GET "repos/$repo/pulls/$target/comments?per_page=100"
    echo "pull request $target: review comments answered $(answered)" ;;
resolve|burst)
    as_graphql "the review threads of $repo's pull request $target" "$THREADS" "owner=$owner" "name=$name" "pr=$target"
    if [ "$action" = resolve ]; then
        threads=$(open_threads "$out/$id.clean" "${APP}" not)
    else
        threads=$(open_threads "$out/$id.clean" combsmith-sf-trial-author is)
    fi
    count=0
    for thread in $threads; do
        count=$((count + 1))
        as_graphql "resolveReviewThread, the App's write, on a thread of $repo's pull request $target" "$RESOLVE" "id=$thread"
        echo "thread $count: answered $(answered)"
    done
    as_graphql "the review threads of $repo's pull request $target" "$THREADS" "owner=$owner" "name=$name" "pr=$target"
    echo "pull request $target: $count threads asked to be resolved" ;;
dismiss)
    as_installation PUT "repos/$repo/pulls/$target/reviews/$review/dismissals" \
        "$(python3 -I -c 'import json; print(json.dumps({"message": "A platform trial: the pr-review App dismisses this review."}))')"
    echo "pull request $target: dismissal answered $(answered)"
    as_installation GET "repos/$repo/pulls/$target/reviews/$review" ;;
check)
    as_installation POST "repos/$repo/check-runs" "$(python3 -I -c '
import json, sys
print(json.dumps({"name": sys.argv[1], "head_sha": sys.argv[2], "status": "completed", "conclusion": "success",
                  "output": {"title": "A platform trial", "summary": "Posted by the pr-review App under this name."}}))' "$name" "$target")"
    echo "check run $name on $target: answered $(answered)" ;;
issue-comments)
    as_installation GET "repos/$repo/issues/$target/comments?since=$SINCE&per_page=100"
    echo "issue $target: its comments since $SINCE answered $(answered)" ;;
label)
    as_installation POST "repos/$repo/issues/$target/labels" "$(python3 -I -c 'import json, sys; print(json.dumps({"labels": [sys.argv[1]]}))' "$label")"
    echo "label $label on $target: added, answered $(answered)"
    as_installation DELETE "repos/$repo/issues/$target/labels/$label"
    echo "label $label on $target: removed, answered $(answered)" ;;
esac

as_installation DELETE installation/token
[ "$(answered)" = 204 ] || { echo "the revocation did not answer 204" >&2; exit 1; }
token=""
