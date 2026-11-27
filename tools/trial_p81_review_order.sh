#!/bin/sh
# Trial P-81, issue 1219: where the issue timeline adapters/seen.py reads puts a review started, left pending past an
# issue comment and submitted a minute later, and what submitted_at it carries.
#
#   tools/trial_p81_review_order.sh OUT PR_REVIEW_KEY REPO PULL_REQUEST FILE
#
# The Maintainer runs it at his own terminal; no session runs it, since it mints a credential. OUT is a new directory
# outside this repo. PR_REVIEW_KEY is the pr-review App's private key file, which only openssl reads. REPO is the canary,
# which config/apps.json installs that App on. PULL_REQUEST is an open pull request in it with no review, whose diff adds
# FILE from its first line, as tools/trial_as_app.sh open makes one. Needs curl, openssl and python3.
#
# The pass, written before the run, is the trial's page, docs/architecture/trials/P-81.md.
#
# One token for the App's installation that P-39 found, on REPO alone, narrowed to issues: read and pull_requests: write,
# makes each call in turn and is revoked. After each write it reads the timeline and the reviews list: 1. as it is;
# 2. a review started with one line comment on FILE, left pending; 3. twenty seconds on, an issue comment; 4. a minute
# on, the review submitted as a comment; 5. twenty seconds on, another comment; 6. the timeline two a page, and the
# review's comments. The token lives in a shell variable and reaches curl on its standard input. Each answer is redacted
# by tools/redact_trial.py in a scratch directory outside the repo; OUT gets the clean answers (clean-N), what the
# redaction removed (redacted-N), the bodies sent (sent-NAME), each call with the time before it (requests.json) and
# ran_at. A refused mint, a failed call, a reviews list not read as none before the first write, a review not started
# pending, a later write refused or a revocation not answered 204 stops the run; a token that may be live is told.
set -eu
# Nothing of the shell's environment steers it: no assignment is exported unasked, and no cd looks along CDPATH
# (issue 1215).
set +a
unset CDPATH
set +x

if [ "$#" -ne 5 ]; then
    echo "usage: tools/trial_p81_review_order.sh OUT PR_REVIEW_KEY REPO PULL_REQUEST FILE" >&2
    exit 2
fi
root=$(CDPATH= cd -P -- "$(dirname -- "$0")/.." && pwd -P)
if [ -e "$1" ] || [ -L "$1" ]; then
    echo "trial_p81_review_order: $1 exists; name a new directory" >&2
    exit 2
fi
# OUT is read as the file system resolves it, every link and .. followed, before it is held to be outside the repo.
if ! parent=$(CDPATH= cd "$(dirname -- "$1")" 2>/dev/null && pwd -P); then
    echo "trial_p81_review_order: the directory that would hold $1 does not exist; make it first" >&2
    exit 2
fi
out=$parent/$(basename -- "$1")
case "$out/" in "$root"/*)
    echo "trial_p81_review_order: $out is inside the repo; name a directory outside it" >&2
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
        echo "trial_p81_review_order: $above is another user's, or can be written by other users and is not sticky, or an ACL may let them; name a directory" \
            "under one only you can write to" >&2
        exit 2
    fi
    [ "$above" = / ] && break
    above=$(dirname -- "$above")
done
key=$2
if [ ! -r "$key" ]; then
    echo "trial_p81_review_order: cannot read the key file $key" >&2
    exit 2
fi
repo=$3 number=$4 file=$5
# A repo and a number are one word of the shapes GitHub allows, so neither reaches the URL as anything else; FILE
# reaches only a body, as JSON.
case "$repo" in
    */*/*|/*|*/|-*|*[!A-Za-z0-9._/-]*) echo "trial_p81_review_order: $repo is not owner/name" >&2; exit 2 ;;
    */*) ;;
    *) echo "trial_p81_review_order: $repo is not owner/name" >&2; exit 2 ;;
esac
case "$number" in
    ""|0*|*[!0-9]*) echo "trial_p81_review_order: $number is not a pull request's number" >&2; exit 2 ;;
esac
case "$file" in
    ""|/*|*/|-*|*..*|*//*|*[!A-Za-z0-9._/-]*) echo "trial_p81_review_order: $file is not a path in the repo" >&2; exit 2 ;;
esac

API=https://api.github.com
VERSION="X-GitHub-Api-Version: 2022-11-28"
ACCEPT="Accept: application/vnd.github+json"
# The raw answers are kept outside the repo, as OUT is: a TMPDIR inside it, or a link into it, is refused.
# The template names TMPDIR itself: macOS's mktemp -d alone does not always read it.
# Its own line: inside the cd, a failed mktemp would be read as the directory this stands in, which the clean-up removes.
made=$(mktemp -d "${TMPDIR:-/tmp}/trial-p81.XXXXXX")
scratch=$(cd "$made" && pwd -P)
case "$scratch/" in "$root"/*)
    rm -rf "$scratch"
    echo "trial_p81_review_order: the scratch directory $scratch is inside the repo; set TMPDIR outside it" >&2
    exit 2 ;;
esac
# No credential's name is taken from the environment, where one exported would reach every child and a mint answer
# would be revoked by the exit trap though this run never minted it; and curl is told of no file to write its TLS
# keys to (issue 1215).
unset SSLKEYLOGFILE token jwt signature minted minting
token=""

revoke() {
    printf 'Authorization: Bearer %s\n' "$token" | curl -q --max-time 30 -sS -o /dev/null -w '%{http_code}' -X DELETE -H @- \
        -H "$ACCEPT" -H "$VERSION" "$API/installation/token"
}

unrevoked() {
    echo "trial_p81_review_order: $1: revoking its token returned $2, not 204. The token may be live for up to an hour;" \
        "the Maintainer must revoke it by hand." >&2
}

# A token in an answer that may be cut short: the first "token" field's value, found without parsing the whole.
# It is read as bytes, so an answer cut inside a character still gives up its token (issue 502).
token_in() {
    printf '%s\n' "$1" | python3 -I -c '
import re, sys
found = re.search(r"\"token\"\s*:\s*\"([^\"]+)\"", sys.stdin.buffer.read().decode("utf-8", "replace"))
print(found.group(1) if found else "")' 2>/dev/null || true
}

finish() {
    # Deaf from here on: a second signal, as a closed terminal sends, must not cut the revocation short, nor a reader
    # of its output gone, nor a write that fails stop what is left (issue 1215).
    trap '' HUP INT TERM QUIT PIPE
    set +e
    if [ -z "$token" ] && [ -n "${minted:-}" ]; then
        token=$(token_in "$minted")
        minted=""
    fi
    if [ -n "$token" ]; then
        last=$(revoke || true)
        echo "trial_p81_review_order: stopped with a token live; revoking it returned $last" >&2
        [ "$last" = 204 ] || unrevoked "the token live when the script stopped" "$last"
        token=""
    elif [ -n "${minting:-}" ]; then
        # Stopped while the mint was asked: its answer never came back here, and GitHub may have minted one.
        echo "trial_p81_review_order: stopped while a token was being minted; GitHub may have minted one, live for up to" \
            "an hour; no one holds it to revoke, so to end it sooner the Maintainer suspends the App's installation." >&2
    fi
    rm -rf "$scratch"
}
trap finish EXIT
trap "trap '' HUP INT TERM QUIT PIPE; exit 1" HUP INT TERM QUIT PIPE

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# The pr-review App's name, id and installation, as the data and P-39's first reads give them; REPO must be one the data
# installs it on, and the Factory's own repo is not asked. Checked once the exit trap stands: python3 may write to
# TMPDIR as it starts.
ids=$(cd "$root" && python3 -I -c '
import json, sys
app = json.load(open("config/apps.json", encoding="utf-8"))["apps"]["pr-review"]
if sys.argv[1] not in app["installed_on"] or sys.argv[1] == "combsmith/software-factory":
    sys.exit("trial_p81_review_order: %s is not the canary the pr-review App is installed on" % sys.argv[1])
fixture = json.load(open("trials/P-39.grants.json", encoding="utf-8"))
read = [e for e in fixture["exchanges"] if e["request"]["call"] == "GET /orgs/combsmith/installations"]
found = {i["app_id"]: i["id"] for i in read[0]["response"]["body"]["installations"]}
print(app["name"], app["app_id"], found[app["app_id"]], sys.argv[1].split("/")[1])
' "$repo")
# shellcheck disable=SC2086  # the four words are split on purpose
set -- $ids
slug=$1 app_id=$2 installation=$3 name=$4

# OUT is made here, by this script alone and for its user alone: one made since it was found absent is refused,
# never written into, since what is in it may be a link to a file this run would overwrite.
if ! mkdir -m 700 "$out"; then
    echo "trial_p81_review_order: $out could not be made new by this run (made since, or refused); name a new directory" >&2
    exit 2
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"
asked=""
n=0

# One call with the live token: its redacted answer to OUT as clean-N, what was asked and the time before it to
# requests.json. A body is OUT's sent-BODY.
ask() {   # METHOD PATH [BODY]
    n=$((n + 1))
    call_ok=1
    at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    # curl is the last command of the pipeline, so its exit is the pipeline's; nothing after it hides a failure.
    # shellcheck disable=SC2086  # the body's two words stand only when there is a body
    printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -i -X "$1" -H @- -H "$ACCEPT" -H "$VERSION" \
        ${3:+-d} ${3:+"@$out/sent-$3"} "$API/$2" > "$scratch/crlf-$n" || call_ok=0
    tr -d '\r' < "$scratch/crlf-$n" > "$scratch/raw-$n"
    rm -f "$scratch/crlf-$n"
    # The last head's status: a proxy's block, or an interim answer, comes first and is no answer to this call.
    status=$(awk 'BEGIN { head = 1 } { sub(/\r$/, "") } head && $0 != "" { if (/^HTTP\/[0-9.]+ [0-9]+/) found = $2; else exit } { head = ($0 == "") } END { print found }' "$scratch/raw-$n")
    if [ "$call_ok" = 0 ] || [ -z "$status" ]; then
        rm -f "$scratch/raw-$n"
        echo "trial_p81_review_order: $1 /$2: curl failed; nothing of it is kept" >&2
        exit 1
    fi
    # Three digits, as requests.json and the terminal take it unquoted (the security read).
    case "$status" in
        [1-5][0-9][0-9]) ;;
        *) rm -f "$scratch/raw-$n"
           echo "trial_p81_review_order: $1 /$2: answered no status of three digits; nothing of it is kept" >&2
           exit 1 ;;
    esac
    (cd "$root" && python3 -m tools.redact_trial < "$scratch/raw-$n" > "$out/clean-$n") 2> "$out/redacted-$n"
    rm -f "$scratch/raw-$n"
    asked="$asked{\"n\": $n, \"as\": \"${slug}[bot]\", \"call\": \"$1 /$2\", \"body\": \"${3:-}\", \"at\": \"$at\","
    asked="$asked \"status\": $status},"
    echo "$1 /$2: $status"
    last_write="$1 /$2"
}

# The last write was answered STATUS, or the run stops: what follows a refused one could not answer the question.
wrote() {   # STATUS
    [ "$status" = "$1" ] && return 0
    echo "trial_p81_review_order: $last_write: GitHub answered $status, not $1; nothing after it is asked" >&2
    exit 1
}

# The timeline as the port reads it, one page of a hundred, and the reviews list.
reads() {
    ask GET "repos/$repo/issues/$number/timeline?per_page=100"
    ask GET "repos/$repo/pulls/$number/reviews?per_page=100"
}

# The body of call N's clean answer, as JSON, read past every head; nothing where it cannot be read.
body_of() {   # N
    python3 -I -c '
import json, sys
text = open(sys.argv[1], encoding="utf-8").read()
while text.startswith("HTTP/"):    # each head, a proxy'"'"'s block among them, comes before the answer
    text = text.partition("\n\n")[2]
print(json.dumps(json.loads(text)))' "$out/clean-$1" 2>/dev/null || true
}

# Whether the clean answer of call N names a next page: its link header, which the redaction keeps, says so.
names_next() {   # N
    python3 -I -c '
import re, sys
sys.exit(0 if re.search(r"(?im)^link:.*rel=\"next\"", open(sys.argv[1], encoding="utf-8").read()) else 1)' "$out/clean-$1"
}

# The bodies, OUT's sent-NAME, trial text only, written once a token is minted.
bodies() {
    python3 -I - "$out" "$file" <<'BODIES'
import json, os, sys
out, path = sys.argv[1:]
said = {"start": {"body": "Trial P-81: a review started now and submitted later.",
                  "comments": [{"path": path, "line": 1, "side": "RIGHT", "body": "Trial P-81: a line comment drafted now."}]},
        "pending": {"body": "Trial P-81: an issue comment while the review is pending."},
        "submit": {"event": "COMMENT", "body": "Trial P-81: a review started now and submitted later."},
        "after": {"body": "Trial P-81: an issue comment after the review was submitted."}}
for name, body in said.items():
    with open(os.path.join(out, "sent-" + name), "w") as held:
        json.dump(body, held)
BODIES
}

# The token, its mint and each call of the run in order, then its revocation.
with_token() {   # NARROWED PERMISSIONS
    now=$(date +%s)
    header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
    claims=$(printf '{"iat":%d,"exp":%d,"iss":%d}' $((now - 60)) $((now + 540)) "$app_id" | b64url)
    signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
    jwt="$header.$claims.$signature"
    # GitHub's answer and its status are held in a variable, never a file, since a minted token is in the answer.
    # curl's own exit code comes last: a transfer that failed is never trusted, however whole its answer reads.
    minting=1
    minted=$(printf 'Authorization: Bearer %s\n' "$jwt" | curl -q -sS -w '\n%{http_code}' -X POST -H @- -H "$ACCEPT" \
        -H "$VERSION" -d "{\"repositories\":[\"$name\"],\"permissions\":{$2}}" \
        "$API/app/installations/$installation/access_tokens" && printf '\n0' || printf '\n%s' "$?")
    jwt="" signature="" minting=""
    minted_exit=$(printf '%s\n' "$minted" | tail -n 1)
    minted=$(printf '%s\n' "$minted" | sed '$d')
    minted_status=$(printf '%s\n' "$minted" | tail -n 1)
    token=$(printf '%s\n' "$minted" | sed '$d' | python3 -I -c '
import json, sys
answer = json.load(sys.stdin)
print(answer.get("token") or "" if isinstance(answer, dict) else "")' 2>/dev/null || true)
    if [ "$minted_status" = 201 ] && { [ -z "$token" ] || [ "$minted_exit" != 0 ]; }; then
        # GitHub minted a token and its answer could not be read whole, or curl said the transfer failed: the token
        # may be live. It is revoked if it can be found in what came back, and the Maintainer is told either way;
        # nothing of the answer is kept.
        token=$(token_in "$minted")
        minted=""
        if [ -n "$token" ]; then
            revoked=$(revoke || true)
            token=""
            [ "$revoked" = 204 ] || unrevoked "a token narrowed to $1 whose answer was cut short" "$revoked"
        else
            echo "trial_p81_review_order: $slug: GitHub minted a token narrowed to $1 and its answer was cut short; the" \
                "token may be live for up to an hour, and the Maintainer must revoke it by hand." >&2
        fi
        echo "trial_p81_review_order: $slug: nothing read, and nothing of the answer kept." >&2
        exit 1
    fi
    if [ "$minted_status" != 201 ] && [ -z "$token" ]; then
        token=$(token_in "$minted")    # a refusal cut short may hold one all the same; the trap revokes it
    fi
    if [ "$minted_status" != 201 ] && [ -n "$token" ]; then
        # A token the refusal carried all the same is left set, for the exit trap to revoke; its answer is not shown.
        minted=""
        echo "trial_p81_review_order: $slug: the mint answered ${minted_status:-none} and held a token all the same;" \
            "nothing read, and the token is revoked as the script stops." >&2
        exit 1
    fi
    if [ "$minted_status" != 201 ]; then
        # No token was minted, so the answer is GitHub's error: it is redacted before it is shown, and never written
        # to a file.
        echo "trial_p81_review_order: $slug: no token narrowed to $1 was minted (status ${minted_status:-none});" \
            "GitHub answered, redacted:" >&2
        if shown=$(printf '%s\n' "$minted" | sed '$d' | (cd "$root" && python3 -m tools.redact_trial) 2>/dev/null); then
            printf '%s\n' "$shown" >&2
        else
            echo "(an answer the redaction could not read, so it is not shown)" >&2
        fi
        minted=""
        exit 1
    fi
    minted=""
    bodies
    reads
    # The pull request holds no review, so the run's is the only one.
    if [ "$status" != 200 ] || [ "$(body_of "$n")" != "[]" ]; then
        echo "trial_p81_review_order: the pull request's reviews were not read as none, status $status; nothing is written" >&2
        exit 1
    fi
    ask POST "repos/$repo/pulls/$number/reviews" start
    # The review's id, if GitHub left it pending: every later step needs it.
    review=$(body_of "$n" | python3 -I -c '
import json, sys
held = json.load(sys.stdin)
print(held["id"] if isinstance(held, dict) and held.get("state") == "PENDING" else "")' 2>/dev/null || true)
    [ "$status" = 200 ] || review=""
    case "$review" in
        ""|0*|*[!0-9]*)
            echo "trial_p81_review_order: the review's start gave no pending review's id, status $status; nothing else is" \
                "asked" >&2
            exit 1 ;;
    esac
    reads
    # Twenty seconds between acts, so that no two share a second; a minute more while the review is pending.
    sleep 20
    ask POST "repos/$repo/issues/$number/comments" pending
    wrote 201
    reads
    sleep 60
    ask POST "repos/$repo/pulls/$number/reviews/$review/events" submit
    wrote 200
    reads
    sleep 20
    ask POST "repos/$repo/issues/$number/comments" after
    wrote 201
    reads
    # The timeline two a page, as the port asks for each, until one names no next page or the bound is met.
    page=1
    while :; do
        if [ "$page" = 1 ]; then
            ask GET "repos/$repo/issues/$number/timeline?per_page=2"
        else
            ask GET "repos/$repo/issues/$number/timeline?per_page=2&page=$page"
        fi
        names_next "$n" || break
        if [ "$page" -ge "$PAGES" ]; then
            echo "trial_p81_review_order: page $page of two still names a next page; the rest is not read" >&2
            break
        fi
        page=$((page + 1))
    done
    ask GET "repos/$repo/pulls/$number/reviews/$review/comments?per_page=100"
    revoked=$(revoke || true)
    if [ "$revoked" != 204 ]; then
        # The token stays set, so the exit trap tries once more to revoke it.
        unrevoked "$slug, narrowed to $1" "$revoked"
        exit 1
    fi
    token=""
    asked="$asked{\"revoked\": \"$1\", \"status\": $revoked},"
    echo "$slug, narrowed to $1: its token revoked with status $revoked"
}

PAGES=30
with_token "issues: read and pull_requests: write" '"issues":"read","pull_requests":"write"'
printf '[%s]\n' "${asked%,}" > "$out/requests.json"
echo "Done. Hand $out to a session; it holds no credential. The token was revoked with status 204."
