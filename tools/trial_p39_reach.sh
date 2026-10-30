#!/bin/sh
# Trial P-39, its third read: which repos each Factory App's installation reaches (issue 26, decision 0035).
#
#   tools/trial_p39_reach.sh OUT CONTROLLER_KEY PR_REVIEW_KEY READER_KEY QUEUE_KEY
#
# The Maintainer runs it at his own terminal, from anywhere; no session runs it, since it mints a credential.
# OUT is a directory that does not exist yet, outside this repo. Each KEY is the path of that App's private key
# file, which only openssl reads. Needs curl, openssl and python3; no gh login is used.
#
# For each App, in the order controller, pr-review, reader, queue: sign a JWT with the App's key; mint a token for the
# installation P-39 found (trials/P-39.grants.json), narrowed to metadata: read; read GET /installation/repositories
# with it once; revoke it, and record the revocation's status. A token or a JWT is held in a shell variable only,
# reaches curl on its standard input, and is never printed, logged or written to a file. Each response is captured
# in a scratch directory outside the repo, redacted there by tools/redact_trial.py, and deleted; OUT receives only
# the redacted response (clean-N), what was asked (requests.json) and when the run started (ran_at). A session then
# builds trials/P-39.reach.json from OUT alone.
#
# A mint, or a read, that curl fails or GitHub refuses, or a revocation that does not return 204, stops the script
# with a non-zero exit: what was read is not kept, a refused mint shows its status and GitHub's answer, redacted,
# and a token that may be live is told to the Maintainer. A mint GitHub answered 201 whose token cannot be read is
# written nowhere, not even to scratch: its token is revoked if it can be found in the answer, and the Maintainer is
# told it may be live if not; no reach is recorded for that App.
set -eu
set +x

if [ "$#" -ne 5 ]; then
    echo "usage: tools/trial_p39_reach.sh OUT CONTROLLER_KEY PR_REVIEW_KEY READER_KEY QUEUE_KEY" >&2
    exit 2
fi
root=$(cd "$(dirname "$0")/.." && pwd -P)
if [ -e "$1" ] || [ -L "$1" ]; then
    echo "trial_p39_reach: $1 exists; name a new directory" >&2
    exit 2
fi
# OUT is read as the file system resolves it, every link and .. followed, before it is held to be outside the repo.
if ! parent=$(CDPATH= cd "$(dirname -- "$1")" 2>/dev/null && pwd -P); then
    echo "trial_p39_reach: the directory that would hold $1 does not exist; make it first" >&2
    exit 2
fi
out=$parent/$(basename -- "$1")
case "$out/" in "$root"/*)
    echo "trial_p39_reach: $out is inside the repo; name a directory outside it" >&2
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
    if [ -n "$found" ]; then
        echo "trial_p39_reach: $above is another user's, or can be written by other users and is not sticky; name a directory" \
            "under one only you can write to" >&2
        exit 2
    fi
    [ "$above" = / ] && break
    above=$(dirname -- "$above")
done
for key in "$2" "$3" "$4" "$5"; do
    if [ ! -r "$key" ]; then
        echo "trial_p39_reach: cannot read the key file $key" >&2
        exit 2
    fi
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

# A token in an answer that may be cut short: the first "token" field's value, found without parsing the whole.
token_in() {
    printf '%s\n' "$1" | python3 -I -c '
import re, sys
found = re.search(r"\"token\"\s*:\s*\"([^\"]+)\"", sys.stdin.read())
print(found.group(1) if found else "")' 2>/dev/null || true
}

unrevoked() {
    echo "trial_p39_reach: $1: revoking its token returned $2, not 204. The token may be live for up to an hour;" \
        "the Maintainer must revoke it by hand." >&2
}

finish() {
    if [ -z "$token" ] && [ -n "${minted:-}" ]; then
        token=$(token_in "$minted")
        minted=""
    fi
    if [ -n "$token" ]; then
        last=$(revoke || true)
        echo "trial_p39_reach: stopped with a token live; revoking it returned $last" >&2
        [ "$last" = 204 ] || unrevoked "the token live when the script stopped" "$last"
        token=""
    fi
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# Each App's name, id and installation, as P-39's first reads give them: the installation GitHub listed for the App's
# name, so an App the data does not name yet is read too.
ids=$(cd "$root" && python3 -I -c '
import json
fixture = json.load(open("trials/P-39.grants.json"))
read = [e for e in fixture["exchanges"] if e["request"]["call"] == "GET /orgs/combsmith/installations"]
found = {i["app_slug"]: i for i in read[0]["response"]["body"]["installations"]}
for app in ("controller", "pr-review", "reader", "queue"):
    installation = found["combsmith-sf-" + app]
    print(app, installation["app_slug"], installation["app_id"], installation["id"])
')

# OUT is made here, by this script alone and for its user alone: one made since it was found absent is refused,
# never written into, since what is in it may be a link to a file this run would overwrite.
if ! mkdir -m 700 "$out"; then
    echo "trial_p39_reach: $out could not be made new by this run (made since, or refused); name a new directory" >&2
    exit 2
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"
asked=""

reach() {
    n=$1 app=$2 key=$3
    # shellcheck disable=SC2046  # the four words are split on purpose
    set -- $(printf '%s\n' "$ids" | grep "^$app ")
    slug=$2 app_id=$3 installation=$4
    now=$(date +%s)
    header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
    claims=$(printf '{"iat":%d,"exp":%d,"iss":%d}' $((now - 60)) $((now + 540)) "$app_id" | b64url)
    signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
    jwt="$header.$claims.$signature"
    # GitHub's answer and its status are held in a variable, never a file, since a minted token is in the answer.
    minted=$(printf 'Authorization: Bearer %s\n' "$jwt" | curl -sS -w '\n%{http_code}' -X POST -H @- -H "$ACCEPT" \
        -H "$VERSION" -d '{"permissions":{"metadata":"read"}}' \
        "$API/app/installations/$installation/access_tokens" || true)
    jwt=""
    minted_status=$(printf '%s\n' "$minted" | tail -n 1)
    minted=$(printf '%s\n' "$minted" | sed '$d')
    token=$(printf '%s\n' "$minted" | python3 -I -c '
import json, sys
answer = json.load(sys.stdin)
print(answer.get("token") or "" if isinstance(answer, dict) else "")' 2>/dev/null || true)
    if [ "$minted_status" = 201 ] && [ -z "$token" ]; then
        # GitHub minted a token and its answer could not be read: the token may be live, and the answer is written
        # nowhere. The token is revoked if it can be found in the answer, and the Maintainer is told either way.
        token=$(token_in "$minted")
        minted=""
        if [ -n "$token" ]; then
            revoked=$(revoke || true)
            token=""
            [ "$revoked" = 204 ] || unrevoked "$slug, whose mint answered 201 and could not be read," "$revoked"
        else
            echo "trial_p39_reach: $slug: GitHub minted a token for installation $installation and its answer could not" \
                "be read; the token may be live for up to an hour, and the Maintainer must revoke it by hand." >&2
        fi
        echo "trial_p39_reach: $slug: nothing read, and nothing of the answer kept." >&2
        exit 1
    fi
    if [ "$minted_status" != 201 ] && [ -z "$token" ]; then
        token=$(token_in "$minted")    # a refusal cut short may hold one all the same; the trap revokes it
    fi
    if [ "$minted_status" != 201 ]; then
        if [ -n "$token" ]; then
            # A token the refusal carried all the same is left set, for the exit trap to revoke; its answer is not shown.
            minted=""
            echo "trial_p39_reach: $slug: the mint answered ${minted_status:-none} and held a token all the same;" \
                "nothing read, and the token is revoked as the script stops." >&2
            exit 1
        fi
        # No token was minted, so the answer is GitHub's error: it is redacted before it is shown, and never written
        # to a file.
        echo "trial_p39_reach: $slug: no token was minted for installation $installation (status ${minted_status:-none});" \
            "nothing read. GitHub answered, redacted:" >&2
        if shown=$(printf '%s\n' "$minted" | (cd "$root" && python3 -m tools.redact_trial) 2>/dev/null); then
            printf '%s\n' "$shown" >&2
        else
            echo "(an answer the redaction could not read, so it is not shown)" >&2
        fi
        minted=""
        exit 1
    fi
    minted=""
    # curl is the last command of the pipeline, so its exit is the pipeline's; nothing after it hides a failure.
    read_ok=1
    printf 'Authorization: Bearer %s\n' "$token" | curl -sS -i -H @- -H "$ACCEPT" -H "$VERSION" \
        "$API/installation/repositories?per_page=100" > "$scratch/crlf-$n" || read_ok=0
    tr -d '\r' < "$scratch/crlf-$n" > "$scratch/raw-$n"
    rm -f "$scratch/crlf-$n"
    status=$(sed -n '1s/^HTTP\/[0-9.]* \([0-9][0-9]*\).*/\1/p' "$scratch/raw-$n")
    revoked=$(revoke || true)
    if [ "$revoked" != 204 ]; then
        # The token stays set, so the exit trap tries once more to revoke it.
        unrevoked "$slug" "$revoked"
        exit 1
    fi
    token=""
    if [ "$read_ok" = 0 ] || [ "$status" != 200 ]; then
        rm -f "$scratch/raw-$n"
        echo "trial_p39_reach: $slug: GET /installation/repositories failed (curl ok: $read_ok, status: ${status:-none});" \
            "its token is revoked, and nothing of it is kept. Run the trial again." >&2
        exit 1
    fi
    (cd "$root" && python3 -m tools.redact_trial < "$scratch/raw-$n" > "$out/clean-$n") 2> "$out/redacted-$n"
    rm -f "$scratch/raw-$n"
    asked="$asked{\"n\": $n, \"app\": \"$app\", \"as\": \"$slug\", \"app_id\": $app_id, \"installation\": $installation,"
    asked="$asked \"call\": \"GET /installation/repositories?per_page=100\", \"revoked\": \"$revoked\"},"
    echo "$slug: read, and its token revoked with status $revoked"
}

reach 1 controller "$2"
reach 2 pr-review "$3"
reach 3 reader "$4"
reach 4 queue "$5"
printf '[%s]\n' "${asked%,}" > "$out/requests.json"
echo "Done. Hand $out to a session; it holds no credential. Each token was revoked with status 204."
