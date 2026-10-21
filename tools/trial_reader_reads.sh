#!/bin/sh
# Trial P-47, with #231's question: what the reader App reads of a login's permission and of a branch's activity,
# and the least permission each read needs (issues 222 and 231, decision 0035).
#
#   tools/trial_reader_reads.sh OUT READER_KEY REPO BRANCH LOGIN...
#
# The Maintainer runs it at his own terminal, from anywhere; no session runs it, since it mints a credential.
# OUT is a directory that does not exist yet, outside this repo. READER_KEY is the path of the reader App's private key
# file, which only openssl reads. REPO is the canary, owner/name, which the reader must be installed on
# (config/apps.json); BRANCH is a branch of it whose activity is read. Each LOGIN is an account whose permission on
# REPO is read: the trial asks for an owner, a collaborator with write, one with triage and an outsider. Needs curl,
# openssl and python3, and no other login.
#
# Twice, once with a token narrowed to metadata: read and once with one narrowed to contents: read: sign a JWT with
# the key; mint a token for the reader's installation that P-39 found (trials/P-39.grants.json), on REPO alone; read
# GET /repos/{REPO}/collaborators/{login}/permission for each LOGIN, and GET /repos/{REPO}/activity for BRANCH; and
# revoke the token, recording the revocation's status. A token or a JWT is held in a shell variable only, reaches curl
# on its standard input, and is never printed, logged or written to a file. Each response is captured in a scratch
# directory outside the repo, redacted there by tools/redact_trial.py, and deleted; OUT receives only the redacted
# response (clean-N), what was asked (requests.json) and when the run started (ran_at). A read GitHub refuses is kept
# with its status: which of the two tokens can make it is what the trial asks. A session then builds the fixture from
# OUT alone.
#
# A mint that curl fails or GitHub refuses, or a revocation that does not return 204, stops the script with a
# non-zero exit; a refused mint shows its status and GitHub's answer, redacted, and a token that may be live is told
# to the Maintainer.
set -eu

if [ "$#" -lt 5 ]; then
    echo "usage: tools/trial_reader_reads.sh OUT READER_KEY REPO BRANCH LOGIN..." >&2
    exit 2
fi
root=$(cd "$(dirname "$0")/.." && pwd -P)
if [ -e "$1" ] || [ -L "$1" ]; then
    echo "trial_reader_reads: $1 exists; name a new directory" >&2
    exit 2
fi
# OUT is read as the file system resolves it, every link and .. followed, before it is held to be outside the repo.
if ! parent=$(cd "$(dirname -- "$1")" 2>/dev/null && pwd -P); then
    echo "trial_reader_reads: the directory that would hold $1 does not exist; make it first" >&2
    exit 2
fi
out=$parent/$(basename -- "$1")
case "$out/" in "$root"/*)
    echo "trial_reader_reads: $out is inside the repo; name a directory outside it" >&2
    exit 2 ;;
esac
key=$2
if [ ! -r "$key" ]; then
    echo "trial_reader_reads: cannot read the key file $key" >&2
    exit 2
fi
repo=$3 branch=$4
shift 4
# A repo, a branch and a login are each one word of the shapes GitHub allows, so none reaches the URL as anything else.
case "$repo" in
    */*/*|/*|*/|-*|*[!A-Za-z0-9._/-]*) echo "trial_reader_reads: $repo is not owner/name" >&2; exit 2 ;;
    */*) ;;
    *) echo "trial_reader_reads: $repo is not owner/name" >&2; exit 2 ;;
esac
case "$branch" in
    ""|-*|*..*|*[!A-Za-z0-9._/-]*) echo "trial_reader_reads: $branch is not a branch name this script reads" >&2; exit 2 ;;
esac
for login in "$@"; do
    case "$login" in
        ""|-*|*[!A-Za-z0-9-]*) echo "trial_reader_reads: $login is not a login" >&2; exit 2 ;;
    esac
done

API=https://api.github.com
VERSION="X-GitHub-Api-Version: 2022-11-28"
ACCEPT="Accept: application/vnd.github+json"
scratch=$(mktemp -d)
token=""

revoke() {
    printf 'Authorization: Bearer %s\n' "$token" | curl -sS -o /dev/null -w '%{http_code}' -X DELETE -H @- \
        -H "$ACCEPT" -H "$VERSION" "$API/installation/token"
}

unrevoked() {
    echo "trial_reader_reads: $1: revoking its token returned $2, not 204. The token may be live for up to an hour;" \
        "the Maintainer must revoke it by hand." >&2
}

finish() {
    if [ -n "$token" ]; then
        last=$(revoke || true)
        echo "trial_reader_reads: stopped with a token live; revoking it returned $last" >&2
        [ "$last" = 204 ] || unrevoked "the token live when the script stopped" "$last"
        token=""
    fi
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# The reader's name, id and installation, as the data and P-39's first reads give them; REPO must be one the data
# installs the reader on, and the Factory's own repo is not asked.
logins="$*"
ids=$(cd "$root" && python3 -I -c '
import json, sys
app = json.load(open("config/apps.json"))["apps"]["reader"]
if sys.argv[1] not in app["installed_on"] or sys.argv[1] == "combsmith/software-factory":
    sys.exit("trial_reader_reads: %s is not the canary the reader is installed on" % sys.argv[1])
fixture = json.load(open("trials/P-39.grants.json"))
read = [e for e in fixture["exchanges"] if e["request"]["call"] == "GET /orgs/combsmith/installations"]
found = {i["app_id"]: i["id"] for i in read[0]["response"]["body"]["installations"]}
print(app["name"], app["app_id"], found[app["app_id"]], sys.argv[1].split("/")[1])
' "$repo")
# shellcheck disable=SC2086  # the four words are split on purpose
set -- $ids
slug=$1 app_id=$2 installation=$3 name=$4

mkdir -p "$out"
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"
asked=""
n=0

# One read with the live token: the redacted answer goes to OUT as clean-N, and what was asked to requests.json.
read_one() {   # NARROWED PATH
    n=$((n + 1))
    read_ok=1
    # curl is the last command of the pipeline, so its exit is the pipeline's; nothing after it hides a failure.
    printf 'Authorization: Bearer %s\n' "$token" | curl -sS -i -H @- -H "$ACCEPT" -H "$VERSION" \
        "$API/$2" > "$scratch/crlf-$n" || read_ok=0
    tr -d '\r' < "$scratch/crlf-$n" > "$scratch/raw-$n"
    rm -f "$scratch/crlf-$n"
    status=$(sed -n '1s/^HTTP\/[0-9.]* \([0-9][0-9]*\).*/\1/p' "$scratch/raw-$n")
    if [ "$read_ok" = 0 ] || [ -z "$status" ]; then
        rm -f "$scratch/raw-$n"
        echo "trial_reader_reads: GET /$2 with a token narrowed to $1: curl failed; nothing of it is kept" >&2
        exit 1
    fi
    (cd "$root" && python3 -m tools.redact_trial < "$scratch/raw-$n" > "$out/clean-$n") 2> "$out/redacted-$n"
    rm -f "$scratch/raw-$n"
    asked="$asked{\"n\": $n, \"as\": \"${slug}[bot]\", \"narrowed_to\": \"$1: read\", \"call\": \"GET /$2\","
    asked="$asked \"status\": $status},"
    echo "GET /$2, narrowed to $1: $status"
}

# A token for the reader's installation narrowed to PERMISSION: read, each read made with it, then revoked.
with_token() {   # PERMISSION
    now=$(date +%s)
    header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
    claims=$(printf '{"iat":%d,"exp":%d,"iss":%d}' $((now - 60)) $((now + 540)) "$app_id" | b64url)
    signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
    jwt="$header.$claims.$signature"
    # GitHub's answer and its status are held in a variable, never a file, since a minted token is in the answer.
    minted=$(printf 'Authorization: Bearer %s\n' "$jwt" | curl -sS -w '\n%{http_code}' -X POST -H @- -H "$ACCEPT" \
        -H "$VERSION" -d "{\"repositories\":[\"$name\"],\"permissions\":{\"$1\":\"read\"}}" \
        "$API/app/installations/$installation/access_tokens" || true)
    jwt=""
    minted_status=$(printf '%s\n' "$minted" | tail -n 1)
    token=$(printf '%s\n' "$minted" | sed '$d' | python3 -I -c '
import json, sys
answer = json.load(sys.stdin)
print(answer.get("token") or "" if isinstance(answer, dict) else "")' 2>/dev/null || true)
    if [ "$minted_status" != 201 ] || [ -z "$token" ]; then
        # No token was minted, so the answer is GitHub's error; it is still redacted before it is shown.
        token=""
        printf '%s\n' "$minted" | sed '$d' > "$scratch/mint"
        minted=""
        echo "trial_reader_reads: $slug: no token narrowed to $1 was minted (status ${minted_status:-none});" \
            "GitHub answered, redacted:" >&2
        if (cd "$root" && python3 -m tools.redact_trial < "$scratch/mint" > "$scratch/mint.clean") 2>/dev/null; then
            cat "$scratch/mint.clean" >&2
        else
            echo "(an answer the redaction could not read, so it is not shown)" >&2
        fi
        rm -f "$scratch/mint" "$scratch/mint.clean"
        exit 1
    fi
    minted=""
    for login in $logins; do
        read_one "$1" "repos/$repo/collaborators/$login/permission"
    done
    read_one "$1" "repos/$repo/activity?ref=refs/heads/$branch&per_page=5"
    revoked=$(revoke || true)
    if [ "$revoked" != 204 ]; then
        # The token stays set, so the exit trap tries once more to revoke it.
        unrevoked "$slug, narrowed to $1" "$revoked"
        exit 1
    fi
    token=""
    asked="$asked{\"revoked\": \"$1: read\", \"status\": $revoked},"
    echo "$slug, narrowed to $1: its token revoked with status $revoked"
}

with_token metadata
with_token contents
printf '[%s]\n' "${asked%,}" > "$out/requests.json"
echo "Done. Hand $out to a session; it holds no credential. Each token was revoked with status 204."
