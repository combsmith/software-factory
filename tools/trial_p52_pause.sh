#!/bin/sh
# Trial P-52: can the controller's installation token, with the Variables permission at repository read alone, read
# FACTORY_PAUSED on a repo it acts in, and the org's FACTORY_PAUSED shared with that repo, and by which route? (#193's
# PR 2 ruling, section 3, read:pass.pause; L-58: the pass reads the repo's pause and the org's.)
#
# The pass condition, written before the run:
#   pass: the token's permissions name the Variables permission at read and nothing at the org; the repo read answers
#   200 with the repo's FACTORY_PAUSED; and the org's FACTORY_PAUSED is read with that token by at least one route, the
#   org endpoint or the repo's list of org variables, answering 200 with its name and value.
#   fail otherwise; then the fixture says which read was refused and with what status, and the controller needs the
#   organization's Variables permission at read, or the pass reads the org's pause another way, before
#   read:pass.pause is written in config/apps.json.
#
#   tools/trial_p52_pause.sh OUT CONTROLLER_KEY
#
# The Maintainer runs it at his own terminal, as tools/trial_p39_reach.sh, after granting the controller Variables at
# repository read; no session runs it, since it mints a credential. OUT is a directory that does not exist yet,
# outside this repo; CONTROLLER_KEY is the path of the controller's private key file, which only openssl reads. Needs
# curl, openssl and python3; no gh login is used. FACTORY_PAUSED is set beforehand, to false, on the repo the
# controller is installed on besides this one, and on the org, shared with that repo alone.
#
# It signs a JWT with the key, mints a token for the controller's installation (P-39 found it, trials/P-39.grants.json),
# makes the three reads with it once each, and revokes it. A token or a JWT is held in a shell variable only, reaches
# curl on its standard input, and is never printed, logged or written to a file. Of the mint's answer it keeps the
# token's permissions and repository selection alone. Each read is captured in a scratch directory outside the repo,
# redacted there by tools/redact_trial.py, and deleted; OUT receives only the redacted answers (clean-N), the token's
# permissions (token.json), what was asked (requests.json) and when the run started (ran_at). A read GitHub refuses is
# kept as it was answered: the refusal is the record. A mint that fails, or a revocation that does not return 204,
# stops the script with a non-zero exit, and a token that may be live is told to the Maintainer. A mint GitHub answered
# 201 whose token cannot be read is written nowhere: its token is revoked if it can be found in the answer, and the
# Maintainer is told it may be live if not.
set -eu
set +x

if [ "$#" -ne 2 ]; then
    echo "usage: tools/trial_p52_pause.sh OUT CONTROLLER_KEY" >&2
    exit 2
fi
root=$(cd "$(dirname "$0")/.." && pwd -P)
if [ -e "$1" ] || [ -L "$1" ]; then
    echo "trial_p52_pause: $1 exists; name a new directory" >&2
    exit 2
fi
if ! parent=$(CDPATH= cd "$(dirname -- "$1")" 2>/dev/null && pwd -P); then
    echo "trial_p52_pause: the directory that would hold $1 does not exist; make it first" >&2
    exit 2
fi
out=$parent/$(basename -- "$1")
case "$out/" in "$root"/*)
    echo "trial_p52_pause: $out is inside the repo; name a directory outside it" >&2
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
        echo "trial_p52_pause: $above is another user's, or can be written by other users and is not sticky; name a directory" \
            "under one only you can write to" >&2
        exit 2
    fi
    [ "$above" = / ] && break
    above=$(dirname -- "$above")
done
if [ ! -r "$2" ]; then
    echo "trial_p52_pause: cannot read the key file $2" >&2
    exit 2
fi
key=$2

API=https://api.github.com
VERSION="X-GitHub-Api-Version: 2022-11-28"
ACCEPT="Accept: application/vnd.github+json"
NAME=FACTORY_PAUSED
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

finish() {
    if [ -z "$token" ] && [ -n "${minted:-}" ]; then
        token=$(token_in "$minted")
        minted=""
    fi
    if [ -n "$token" ]; then
        last=$(revoke || true)
        echo "trial_p52_pause: stopped with a token live; revoking it returned $last" >&2
        if [ "$last" != 204 ]; then
            echo "trial_p52_pause: the token may be live for up to an hour; the Maintainer must revoke it by hand." >&2
        fi
        token=""
    fi
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# The controller's id and installation, from the data and P-39's first read; the repo it acts in besides this one, and
# the org, from where config/apps.json says it is installed.
said=$(cd "$root" && python3 -I -c '
import json
app = json.load(open("config/apps.json"))["apps"]["controller"]
fixture = json.load(open("trials/P-39.grants.json"))
read = [e for e in fixture["exchanges"] if e["request"]["call"] == "GET /orgs/combsmith/installations"]
found = {i["app_id"]: i["id"] for i in read[0]["response"]["body"]["installations"]}
others = [r for r in app["installed_on"] if r != "combsmith/software-factory"]
assert len(others) == 1, "the controller is installed on one repo besides this one"
print(app["name"], app["app_id"], found[app["app_id"]], others[0], others[0].split("/")[0])
')
# shellcheck disable=SC2086  # the five words are split on purpose
set -- $said
slug=$1 app_id=$2 installation=$3 repo=$4 org=$5

# OUT is made here, by this script alone and for its user alone: one made since it was found absent is refused,
# never written into, since what is in it may be a link to a file this run would overwrite.
if ! mkdir -m 700 "$out"; then
    echo "trial_p52_pause: $out could not be made new by this run (made since, or refused); name a new directory" >&2
    exit 2
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"

now=$(date +%s)
header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
claims=$(printf '{"iat":%d,"exp":%d,"iss":%d}' $((now - 60)) $((now + 540)) "$app_id" | b64url)
signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
jwt="$header.$claims.$signature"
# The answer is held in a variable, never a file, since the token is in it. Nothing narrows the token, so its
# permissions are what the App was granted.
minted=$(printf 'Authorization: Bearer %s\n' "$jwt" | curl -sS -w '\n%{http_code}' -X POST -H @- -H "$ACCEPT" \
    -H "$VERSION" "$API/app/installations/$installation/access_tokens" || true)
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
        [ "$revoked" = 204 ] || echo "trial_p52_pause: revoking it returned $revoked, not 204; the token may be" \
            "live for up to an hour, and the Maintainer must revoke it by hand." >&2
    else
        echo "trial_p52_pause: $slug: GitHub minted a token for installation $installation and its answer could not" \
            "be read; the token may be live for up to an hour, and the Maintainer must revoke it by hand." >&2
    fi
    echo "trial_p52_pause: $slug: nothing read, and nothing of the answer kept." >&2
    exit 1
fi
if [ "$minted_status" != 201 ] && [ -z "$token" ]; then
    token=$(token_in "$minted")    # a refusal cut short may hold one all the same; the trap revokes it
fi
if [ "$minted_status" != 201 ] && [ -n "$token" ]; then
    # A token the refusal carried all the same is left set, for the exit trap to revoke; its answer is not shown.
    minted=""
    echo "trial_p52_pause: $slug: the mint answered ${minted_status:-none} and held a token all the same;" \
        "nothing read, and the token is revoked as the script stops." >&2
    exit 1
fi
if [ "$minted_status" != 201 ]; then
    minted=""
    echo "trial_p52_pause: $slug: the mint was refused for installation $installation (status ${minted_status:-none});" \
        "nothing read" >&2
    exit 1
fi
printf '%s\n' "$minted" | python3 -I -c '
import json, sys
answer = json.load(sys.stdin)
json.dump({"permissions": answer.get("permissions"), "repository_selection": answer.get("repository_selection")},
          open(sys.argv[1], "w"), indent=2)' "$out/token.json"
minted=""

asked=""
n=0
for path in "repos/$repo/actions/variables/$NAME" "orgs/$org/actions/variables/$NAME" \
        "repos/$repo/actions/organization-variables?per_page=100"; do
    n=$((n + 1))
    read_ok=1
    printf 'Authorization: Bearer %s\n' "$token" | curl -sS -i -H @- -H "$ACCEPT" -H "$VERSION" "$API/$path" \
        > "$scratch/crlf-$n" || read_ok=0
    tr -d '\r' < "$scratch/crlf-$n" > "$scratch/raw-$n"
    rm -f "$scratch/crlf-$n"
    status=$(sed -n '1s/^HTTP\/[0-9.]* \([0-9][0-9]*\).*/\1/p' "$scratch/raw-$n")
    (cd "$root" && python3 -m tools.redact_trial < "$scratch/raw-$n" > "$out/clean-$n") 2> "$out/redacted-$n"
    rm -f "$scratch/raw-$n"
    asked="$asked{\"n\": $n, \"as\": \"$slug\", \"app_id\": $app_id, \"installation\": $installation,"
    asked="$asked \"call\": \"GET /$path\", \"curl_ok\": $read_ok, \"status\": \"${status:-none}\"},"
    echo "$slug: GET /$path answered ${status:-nothing}"
done

revoked=$(revoke || true)
if [ "$revoked" != 204 ]; then
    echo "trial_p52_pause: revoking the token returned $revoked, not 204" >&2
    exit 1
fi
token=""
printf '{"reads": [%s], "revoked": "%s"}\n' "${asked%,}" "$revoked" > "$out/requests.json"
echo "Done. Hand $out to a session; it holds no credential. The token was revoked with status 204."
