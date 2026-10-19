#!/bin/sh
# Trial P-39, its third read: which repos each Factory App's installation reaches (issue 26, decision 0036).
#
#   tools/trial_p39_reach.sh OUT CONTROLLER_KEY PR_REVIEW_KEY READER_KEY
#
# The Maintainer runs it at his own terminal, from anywhere; no session runs it, since it mints a credential.
# OUT is a directory that does not exist yet, outside this repo. Each KEY is the path of that App's private key
# file, which only openssl reads. Needs curl, openssl and python3; no gh login is used.
#
# For each App, in the order controller, pr-review, reader: sign a JWT with the App's key; mint a token for the
# installation P-39 found (trials/P-39.grants.json), narrowed to metadata: read; read GET /installation/repositories
# with it once; revoke it, and record the revocation's status. A token or a JWT is held in a shell variable only,
# reaches curl on its standard input, and is never printed, logged or written to a file. Each response is captured
# in a scratch directory outside the repo, redacted there by tools/redact_trial.py, and deleted; OUT receives only
# the redacted response (clean-N), what was asked (requests.json) and when the run started (ran_at). A session then
# builds trials/P-39.reach.json from OUT alone.
set -eu

if [ "$#" -ne 4 ]; then
    echo "usage: tools/trial_p39_reach.sh OUT CONTROLLER_KEY PR_REVIEW_KEY READER_KEY" >&2
    exit 2
fi
root=$(cd "$(dirname "$0")/.." && pwd -P)
case "$1" in /*) out=$1 ;; *) out=$(pwd -P)/$1 ;; esac
if [ -e "$out" ]; then
    echo "trial_p39_reach: $out exists; name a new directory" >&2
    exit 2
fi
case "$out/" in "$root"/*)
    echo "trial_p39_reach: $out is inside the repo; name a directory outside it" >&2
    exit 2 ;;
esac
for key in "$2" "$3" "$4"; do
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

finish() {
    if [ -n "$token" ]; then
        echo "trial_p39_reach: stopped with a token live; revoking it: $(revoke)" >&2
        token=""
    fi
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# Each App's name, id and installation, as the data and P-39's first reads give them.
ids=$(cd "$root" && python3 -I -c '
import json
apps = json.load(open("config/apps.json"))["apps"]
fixture = json.load(open("trials/P-39.grants.json"))
read = [e for e in fixture["exchanges"] if e["request"]["call"] == "GET /orgs/combsmith/installations"]
found = {i["app_id"]: i["id"] for i in read[0]["response"]["body"]["installations"]}
for app in ("controller", "pr-review", "reader"):
    print(app, apps[app]["name"], apps[app]["app_id"], found[apps[app]["app_id"]])
')

mkdir -p "$out"
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
    token=$(printf 'Authorization: Bearer %s\n' "$jwt" | curl -sS -X POST -H @- -H "$ACCEPT" -H "$VERSION" \
        -d '{"permissions":{"metadata":"read"}}' "$API/app/installations/$installation/access_tokens" |
        python3 -I -c 'import json, sys; print(json.load(sys.stdin).get("token") or "")')
    jwt=""
    if [ -z "$token" ]; then
        echo "trial_p39_reach: $slug: no token was minted for installation $installation; nothing read" >&2
        exit 1
    fi
    printf 'Authorization: Bearer %s\n' "$token" | curl -sS -i -H @- -H "$ACCEPT" -H "$VERSION" \
        "$API/installation/repositories?per_page=100" | tr -d '\r' > "$scratch/raw-$n"
    revoked=$(revoke)
    token=""
    (cd "$root" && python3 -m tools.redact_trial "$scratch/raw-$n" "$out/clean-$n") > "$out/redacted-$n"
    rm -f "$scratch/raw-$n"
    asked="$asked{\"n\": $n, \"app\": \"$app\", \"as\": \"$slug\", \"app_id\": $app_id, \"installation\": $installation,"
    asked="$asked \"call\": \"GET /installation/repositories?per_page=100\", \"revoked\": \"$revoked\"},"
    echo "$slug: read, and its token revoked with status $revoked"
}

reach 1 controller "$2"
reach 2 pr-review "$3"
reach 3 reader "$4"
printf '[%s]\n' "${asked%,}" > "$out/requests.json"
echo "Done. Hand $out to a session; it holds no credential. A revocation status other than 204 is told to the Maintainer."
