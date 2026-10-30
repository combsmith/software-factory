#!/usr/bin/env bash
# What the trial-author App writes for a platform trial (design, section 6: P-1, P-7, P-24, P-28),
# at the Maintainer's own terminal and nowhere else. No session and no workflow runs this.
#
#   bash tools/trial_as_app.sh open KEY REPO BRANCH FILE   # a branch from the default branch, one commit, a pull request
#   bash tools/trial_as_app.sh push KEY REPO PR FILE       # one commit to the head of an open pull request
#   bash tools/trial_as_app.sh threads KEY REPO BRANCH FILE  # as open, then two review threads on FILE (issue 282):
#       the App opens one and resolves it, reading it as itself after; it opens a second, replies to it, deletes the
#       second's first comment, and reads the thread before and after. The Maintainer's own reads follow, in a session.
#
# KEY is the path of the App's private key. Only openssl opens it, to sign; this script never
# reads, prints or copies what it holds. FILE is a new file's path in REPO; the commit adds it.
# The script mints one installation token, which no command line ever holds, revokes it before it
# exits, on a failure too, and keeps in a new scratch directory outside this repo only what
# tools/redact_trial.py let through. It prints that directory, the pull request and its head.
# Run it from anywhere in a checkout of this repo, with bash 3.2 or later, curl, openssl, gh, python3.
set -euo pipefail
set +x
unset GH_DEBUG DEBUG CURL_HOME
# gh sends GH_TOKEN to the host GH_HOST names, or its configured default: pin it to the host the curl calls use.
export GH_HOST=github.com GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1

APP_ID=5363178
APP=combsmith-sf-trial-author
API=https://api.github.com
VERSION=2022-11-28
ACCEPT=application/vnd.github+json

usage() {
    echo "usage: bash tools/trial_as_app.sh open KEY OWNER/REPO BRANCH FILE" >&2
    echo "       bash tools/trial_as_app.sh push KEY OWNER/REPO PR FILE" >&2
    echo "       bash tools/trial_as_app.sh threads KEY OWNER/REPO BRANCH FILE" >&2
    exit 2
}
[ "$#" -eq 5 ] || usage
action=$1 key=$2 repo=$3 target=$4 file=$5
case "$action" in open|push|threads) ;; *) usage ;; esac
case "$repo" in */*/*|/*|*/) usage ;; */*) ;; *) usage ;; esac
case "$file" in ""|/*|*..*|*" "*) echo "FILE is a new path inside REPO, such as trial-notes/p-1.md" >&2; exit 2 ;; esac
if [ "$action" = push ]; then
    case "$target" in ""|*[!0-9]*) usage ;; esac
else
    case "$target" in ""|-*|*" "*|*..*) usage ;; esac
fi
[ -f "$key" ] && [ -r "$key" ] || { echo "no readable file at the key's path" >&2; exit 2; }
for tool in curl openssl gh python3; do
    command -v "$tool" >/dev/null || { echo "$tool is needed" >&2; exit 2; }
done

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[ -f "$root/tools/redact_trial.py" ] || { echo "run the copy of this script in a checkout of software-factory" >&2; exit 2; }
out=$(cd "$(mktemp -d)" && pwd -P)
case "$out/" in "$root"/*) echo "the scratch directory is inside the repo" >&2; exit 2 ;; esac

jwt="" token="" n=0 id="" raw="" pushed="" read_head=""

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

# A JSON object of the string arguments given as name=value.
object() {
    python3 -I -c '
import json, sys
print(json.dumps(dict(arg.split("=", 1) for arg in sys.argv[1:])))' "$@"
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

# A raw capture, redacted beside it and then deleted. Only the redaction's report is printed. A capture whose redaction
# fails is deleted unread all the same, since it lies in OUT, which a session reads; its partial clean file goes with it,
# and the failure is said and returned.
redact() {   # RAW
    local failed=0
    (cd "$root" && python3 -m tools.redact_trial < "$1" 2>&1 > "${1%.raw}.clean") | sed "s|^|$(basename "${1%.raw}"): |" ||
        failed=1
    rm -f "$1"
    if [[ "$failed" -ne 0 ]]; then
        rm -f "${1%.raw}.clean"
        echo "trial_as_app: the redaction of $(basename "${1%.raw}") failed; its capture is deleted unread" >&2
        return 1
    fi
}

# As the App itself, by its JWT: the header goes to curl on its standard input, never as an argument.
as_app() {   # METHOD PATH
    record "$1 /$2" "$APP, by its JWT" ""
    printf 'Authorization: Bearer %s\n' "$jwt" |
        curl -q -sS -i --fail-with-body -X "$1" -H @- -H "Accept: $ACCEPT" \
            -H "X-GitHub-Api-Version: $VERSION" "$API/$2" | tr -d '\r' > "$raw"
    redact "$raw"
}

# As the App's installation: gh reads the token from its environment, never from an argument.
as_installation() {   # METHOD PATH [BODY]
    record "$1 /$2" "${APP}[bot], by an installation token" "${3:-}"
    if [ -n "${3:-}" ]; then
        printf '%s' "$3" | GH_TOKEN="$token" gh api --include -X "$1" -H "Accept: $ACCEPT" \
            -H "X-GitHub-Api-Version: $VERSION" "$2" --input - | tr -d '\r' > "$raw"
    else
        GH_TOKEN="$token" gh api --include -X "$1" -H "Accept: $ACCEPT" \
            -H "X-GitHub-Api-Version: $VERSION" "$2" | tr -d '\r' > "$raw"
    fi
    redact "$raw"
}

# The review threads of pull request PR, read by GraphQL as the installation: one query naming the repo, so the check
# of the fixture reads which repo it asks of.
THREADS='query($owner: String!, $name: String!, $pr: Int!) { repository(owner: $owner, name: $name) { pullRequest(number: $pr) { reviewThreads(first: 10) { totalCount nodes { id isResolved resolvedBy { login __typename } comments(first: 10) { totalCount nodes { databaseId author { login __typename } body replyTo { databaseId } } } } } } } }'
read_threads() {   # PR
    local owner=${repo%%/*} name=${repo#*/}
    record "POST /graphql (gh api graphql): the review threads of $repo's pull request $1" "${APP}[bot], by an installation token" \
        "$(python3 -I -c 'import json, sys; print(json.dumps({"query": sys.argv[1], "variables": {"owner": sys.argv[2], "name": sys.argv[3], "pr": int(sys.argv[4])}}))' "$THREADS" "$owner" "$name" "$1")" graphql
    GH_TOKEN="$token" gh api graphql --include -f query="$THREADS" -f owner="$owner" -f name="$name" -F pr="$1" \
        | tr -d '\r' > "$raw"
    redact "$raw"
}
# Resolve one review thread by its node id: a GraphQL write, recorded as what it was. A fixture holds a GraphQL read
# alone, so the session that builds one from OUT says what this write sent and was answered, in its own analysis.
RESOLVE='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id isResolved resolvedBy { login __typename } } } }'
resolve_thread() {   # THREAD_ID PR
    record "POST /graphql (gh api graphql): resolveReviewThread, the App's write, on a thread of $repo's pull request $2" \
        "${APP}[bot], by an installation token" \
        "$(python3 -I -c 'import json, sys; print(json.dumps({"query": sys.argv[1], "variables": {"id": sys.argv[2]}}))' "$RESOLVE" "$1")" graphql
    GH_TOKEN="$token" gh api graphql --include -f query="$RESOLVE" -f id="$1" | tr -d '\r' > "$raw"
    redact "$raw"
}
# The node id of the one thread, or the database id of its first comment, whose first comment is the App's own, no
# reply, and starts with PREFIX, in the redacted read FILE; it fails unless exactly one thread is so, and unless the id
# has the shape GitHub gives one, so that nothing read from an answer is sent but an id of this App's own thread.
thread_of() {   # FILE PREFIX FIELD
    python3 -I -c '
import json, re, sys
text = open(sys.argv[1]).read()
head, gap, body = text.partition("\n\n")
data = json.loads(body if gap else text)
found = []
for node in data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]:
    first = node["comments"]["nodes"][0] if node["comments"]["nodes"] else {}
    author = first.get("author") or {}
    if (str(first.get("body", "")).startswith(sys.argv[2]) and first.get("replyTo") is None
            and author.get("login") == sys.argv[4] and author.get("__typename") == "Bot"):
        found.append(node["id"] if sys.argv[3] == "thread" else first["databaseId"])
if len(found) != 1:
    sys.exit("%d threads of the App start with %s; one was looked for" % (len(found), sys.argv[2]))
said = str(found[0])
shape = r"PRRT_[A-Za-z0-9_-]{1,100}" if sys.argv[3] == "thread" else r"[1-9][0-9]{0,18}"
if not re.fullmatch(shape, said):
    sys.exit("the id read does not have the shape of one")
print(said)' "$1" "$2" "$3" "$APP"
}

# Revoke the token first, whatever happened; then redact what is left and gather the exchanges.
finish() {
    status=$?
    trap - EXIT INT TERM
    set +e
    if [ -n "$token" ]; then
        as_installation DELETE installation/token
        [ "$(sed -n 1p "$out/$id.clean" 2>/dev/null | cut -d' ' -f2)" = 204 ] ||
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
    redact_json="$out/exchanges.unchecked.json"
    (cd "$root" && python3 -m tools.redact_trial < "$redact_json" > "$out/exchanges.json") 2> /dev/null ||
        { echo "trial_as_app: the redaction of the exchanges failed" >&2; exit 1; }
    rm -f "$redact_json"
    echo "Done, status $status. Give the session this directory; it reads only exchanges.json and the .clean files:"
    echo "  $out"
    exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '=\n'; }

# The App's JWT, ten minutes at most, signed by openssl from the key's path.
now=$(date +%s)
header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
claims=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$((now - 60))" "$((now + 540))" "$APP_ID" | b64url)
signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
jwt="$header.$claims.$signature"
unset header claims signature

as_app GET "repos/$repo/installation"
installation=$(value "$out/$id.clean" id)

# The token, minted: python keeps it apart from what is written, and hands it to this shell alone.
record "POST /app/installations/$installation/access_tokens" "$APP, by its JWT" ""
token=$(printf 'Authorization: Bearer %s\n' "$jwt" |
    curl -q -sS -i --fail-with-body -X POST -H @- -H "Accept: $ACCEPT" -H "X-GitHub-Api-Version: $VERSION" \
        "$API/app/installations/$installation/access_tokens" |
    python3 -I -c '
import json, re, sys
text = sys.stdin.read().replace("\r\n", "\n")
# The headers are the block of the last status line: a proxy prints its own "Connection established" block before
# the one from GitHub, and GitHub prints an empty list in its JSON across a blank line, so neither the first blank
# line nor the last ends the headers.
starts = [m.start(1) for m in re.finditer(r"(?:\A|\n\n)(HTTP/[0-9.]+ [0-9]{3})", text)]
cut = text.find("\n\n", starts[-1]) if starts else -1
head, body = (text[starts[-1]:cut], text[cut + 2:]) if cut >= 0 else (text, "")
data = None
if not starts:
    head = "(no status line)"   # what came back cannot be told from a head, so none of it is kept as one
else:
    try:
        data = json.loads(body)
    except ValueError:
        pass
token = data.pop("token", "") if isinstance(data, dict) else ""
if data is None:
    # An answer that is not JSON, one cut short or with no status line among them, is never written, since a token
    # may be in it. A token is found by its field alone and handed on, so the exit trap revokes it; the run stops.
    found = re.search(r"\"token\"\s*:\s*\"([^\"]+)\"", text)
    token = found.group(1) if found else ""
with open(sys.argv[1], "w") as kept:
    kept.write(head + "\n\n" + (json.dumps(data) if data is not None else "(an answer that is not JSON, not kept)"))
sys.stdout.write(token)
if data is None:
    sys.stderr.write("trial_as_app: the mint was answered with what is not JSON; " + (
        "the token found in it is revoked as the script stops\n" if token else
        "if a token was minted it was not revoked, and expires within an hour\n"))
    sys.exit(3)' "$raw")
redact "$raw"
jwt=""
[ -n "$token" ] || { echo "no installation token was read: if one was minted it was not revoked, and expires within an hour" >&2; exit 1; }

as_installation GET installation/repositories

content=$(printf 'A platform trial: this file was added by the trial-author App, through %s.\n' "$action" | openssl base64 -A)
if [ "$action" = open ] || [ "$action" = threads ]; then
    branch=$target
    as_installation GET "repos/$repo"
    base=$(value "$out/$id.clean" default_branch)
    as_installation GET "repos/$repo/git/ref/heads/$base"
    sha=$(value "$out/$id.clean" object.sha)
    as_installation POST "repos/$repo/git/refs" "$(object "ref=refs/heads/$branch" "sha=$sha")"
    as_installation PUT "repos/$repo/contents/$file" \
        "$(object "message=Trial: $file, added by the trial-author App" "content=$content" "branch=$branch")"
    pushed=$(value "$out/$id.clean" commit.sha)
    as_installation POST "repos/$repo/pulls" "$(object "title=Trial: $branch, opened by the trial-author App" \
        "head=$branch" "base=$base" "body=A platform trial. It is approved by the machine user alone, and read.")"
    pr=$(value "$out/$id.clean" number)
else
    pr=$target
    as_installation GET "repos/$repo/pulls/$pr"
    [ "$(value "$out/$id.clean" head.repo.full_name)" = "$repo" ] || { echo "the pull request's head is not in $repo" >&2; exit 1; }
    [ "$(value "$out/$id.clean" state)" = open ] || { echo "pull request $pr is not open" >&2; exit 1; }
    branch=$(value "$out/$id.clean" head.ref)
    as_installation PUT "repos/$repo/contents/$file" \
        "$(object "message=Trial: $file, pushed by the trial-author App" "content=$content" "branch=$branch")"
    pushed=$(value "$out/$id.clean" commit.sha)
fi
# GitHub moves a pull request's head after the push that moves it, so the head is read until it is the commit the
# push made, a few times, and said as it was last read.
for attempt in 1 2 3 4 5; do
    as_installation GET "repos/$repo/pulls/$pr"
    read_head=$(value "$out/$id.clean" head.sha)
    [[ "$read_head" = "$pushed" ]] && break
    if [[ "$attempt" -lt 5 ]]; then sleep 2; fi
done
echo "Pull request $pr, branch $branch, head $read_head"
[[ "$read_head" = "$pushed" ]] || echo "trial_as_app: the push made $pushed, and the pull request still read $read_head" >&2

if [ "$action" = threads ]; then
    # The first thread: the App opens it, resolves it, and reads it as itself.
    as_installation POST "repos/$repo/pulls/$pr/reviews" "$(python3 -I -c 'import json, sys; print(json.dumps({"event": "COMMENT", "body": "A platform trial (issue 282): the first review thread, which the App resolves.", "comments": [{"path": sys.argv[1], "line": 1, "side": "RIGHT", "body": "Trial thread 1: the App resolves it."}]}))' "$file")"
    read_threads "$pr"
    thread=$(thread_of "$out/$id.clean" "Trial thread 1" thread)
    resolve_thread "$thread" "$pr"
    read_threads "$pr"
    # The second thread: the App opens it and replies to it, then deletes its first comment, reading it before and after.
    as_installation POST "repos/$repo/pulls/$pr/reviews" "$(python3 -I -c 'import json, sys; print(json.dumps({"event": "COMMENT", "body": "A platform trial (issue 282): the second review thread, whose first comment is deleted.", "comments": [{"path": sys.argv[1], "line": 1, "side": "RIGHT", "body": "Trial thread 2: its first comment is deleted."}]}))' "$file")"
    read_threads "$pr"
    first=$(thread_of "$out/$id.clean" "Trial thread 2" comment)
    as_installation POST "repos/$repo/pulls/$pr/comments/$first/replies" "$(object "body=Trial thread 2: a reply, which should stay.")"
    read_threads "$pr"
    as_installation DELETE "repos/$repo/pulls/comments/$first"
    read_threads "$pr"
    echo "Two review threads on pull request $pr; the session reads them as the Maintainer, then closes it."
fi

as_installation DELETE installation/token
[ "$(sed -n 1p "$out/$id.clean" | cut -d' ' -f2)" = 204 ] || { echo "the revocation did not answer 204" >&2; exit 1; }
token=""
