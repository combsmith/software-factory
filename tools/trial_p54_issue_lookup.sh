#!/bin/sh
# Trial P-54, issue 342's box: whether the Controller App reads the issue a pull request is bound to, GET
# /repos/{repo}/issues/{n} as adapters/acceptance.py's labelled() reads it, under the grant it holds (decisions 0035,
# 0068).
#
#   tools/trial_p54_issue_lookup.sh OUT CONTROLLER_KEY REPO ISSUE
#
# The Maintainer runs it at his own terminal, from anywhere; no session runs it, since it mints a credential.
# OUT is a directory that does not exist yet, outside this repo. CONTROLLER_KEY is the path of the Controller App's
# private key file, which only openssl reads. REPO is the canary, owner/name, which the Controller must be installed
# on (config/apps.json); ISSUE is the number of an issue in it, not a pull request. Needs curl, openssl and python3,
# and no other login.
#
# The pass condition, written before the run:
#   pass: a token for the Controller's installation narrowed to issues: read, on REPO alone, reads GET
#   /repos/{REPO}/issues/{ISSUE} with 200, and the body is that issue: its number is ISSUE, it holds no pull_request,
#   and its labels are a list of objects each with a name, which is what labelled() reads.
#   fail otherwise.
#   Recorded, deciding nothing: what a token narrowed to metadata: read alone is answered for the same read. REPO is
#   public, so GitHub may answer it as it would anyone (decision 0068); a private repo is not asked here.
#
# Twice, once with a token narrowed to issues: read and once with one narrowed to metadata: read: sign a JWT with the
# key; mint a token for the Controller's installation that P-39 found (trials/P-39.grants.json), on REPO alone; read
# GET /repos/{REPO}/issues/{ISSUE}; and revoke the token, recording the revocation's status. A token or a JWT is held
# in a shell variable only, reaches curl on its standard input, and is never printed, logged or written to a file.
# Each response is captured in a scratch directory outside the repo, redacted there by tools/redact_trial.py, and
# deleted; OUT receives only the redacted response (clean-N), what was asked (requests.json) and when the run started
# (ran_at). A read GitHub refuses is kept with its status: which of the two tokens can make it is what the trial asks.
# A session then builds the fixture from OUT alone.
#
# A mint that curl fails or GitHub refuses, or a revocation that does not return 204, stops the script with a
# non-zero exit; a refused mint shows its status and GitHub's answer, redacted, and a token that may be live is told
# to the Maintainer.
set -eu
set +x

if [ "$#" -ne 4 ]; then
    echo "usage: tools/trial_p54_issue_lookup.sh OUT CONTROLLER_KEY REPO ISSUE" >&2
    exit 2
fi
root=$(cd "$(dirname "$0")/.." && pwd -P)
if [ -e "$1" ] || [ -L "$1" ]; then
    echo "trial_p54_issue_lookup: $1 exists; name a new directory" >&2
    exit 2
fi
# OUT is read as the file system resolves it, every link and .. followed, before it is held to be outside the repo.
if ! parent=$(CDPATH= cd "$(dirname -- "$1")" 2>/dev/null && pwd -P); then
    echo "trial_p54_issue_lookup: the directory that would hold $1 does not exist; make it first" >&2
    exit 2
fi
out=$parent/$(basename -- "$1")
case "$out/" in "$root"/*)
    echo "trial_p54_issue_lookup: $out is inside the repo; name a directory outside it" >&2
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
        echo "trial_p54_issue_lookup: $above is another user's, or can be written by other users and is not sticky; name a directory" \
            "under one only you can write to" >&2
        exit 2
    fi
    [ "$above" = / ] && break
    above=$(dirname -- "$above")
done
key=$2
if [ ! -r "$key" ]; then
    echo "trial_p54_issue_lookup: cannot read the key file $key" >&2
    exit 2
fi
repo=$3 issue=$4
# A repo and an issue are each one word of the shapes GitHub allows, so neither reaches the URL as anything else.
case "$repo" in
    */*/*|/*|*/|-*|*[!A-Za-z0-9._/-]*) echo "trial_p54_issue_lookup: $repo is not owner/name" >&2; exit 2 ;;
    */*) ;;
    *) echo "trial_p54_issue_lookup: $repo is not owner/name" >&2; exit 2 ;;
esac
case "$issue" in
    ""|0*|*[!0-9]*) echo "trial_p54_issue_lookup: $issue is not an issue's number" >&2; exit 2 ;;
esac

API=https://api.github.com
VERSION="X-GitHub-Api-Version: 2022-11-28"
ACCEPT="Accept: application/vnd.github+json"
# The raw answers are kept outside the repo, as OUT is: a TMPDIR inside it, or a link into it, is refused.
# The template names TMPDIR itself: macOS's mktemp -d alone does not always read it.
scratch=$(cd "$(mktemp -d "${TMPDIR:-/tmp}/trial-p54.XXXXXX")" && pwd -P)
case "$scratch/" in "$root"/*)
    rm -rf "$scratch"
    echo "trial_p54_issue_lookup: the scratch directory $scratch is inside the repo; set TMPDIR outside it" >&2
    exit 2 ;;
esac
token=""

revoke() {
    printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -o /dev/null -w '%{http_code}' -X DELETE -H @- \
        -H "$ACCEPT" -H "$VERSION" "$API/installation/token"
}

unrevoked() {
    echo "trial_p54_issue_lookup: $1: revoking its token returned $2, not 204. The token may be live for up to an hour;" \
        "the Maintainer must revoke it by hand." >&2
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
        echo "trial_p54_issue_lookup: stopped with a token live; revoking it returned $last" >&2
        [ "$last" = 204 ] || unrevoked "the token live when the script stopped" "$last"
        token=""
    fi
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# The Controller's name, id and installation, as the data and P-39's first reads give them; REPO must be one the data
# installs the Controller on, and the Factory's own repo is not asked.
ids=$(cd "$root" && python3 -I -c '
import json, sys
app = json.load(open("config/apps.json"))["apps"]["controller"]
if sys.argv[1] not in app["installed_on"] or sys.argv[1] == "combsmith/software-factory":
    sys.exit("trial_p54_issue_lookup: %s is not the canary the Controller is installed on" % sys.argv[1])
fixture = json.load(open("trials/P-39.grants.json"))
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
    echo "trial_p54_issue_lookup: $out could not be made new by this run (made since, or refused); name a new directory" >&2
    exit 2
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"
asked=""
n=0

# One read with the live token: the redacted answer goes to OUT as clean-N, and what was asked to requests.json.
read_one() {   # NARROWED PATH
    n=$((n + 1))
    read_ok=1
    # curl is the last command of the pipeline, so its exit is the pipeline's; nothing after it hides a failure.
    printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -i -H @- -H "$ACCEPT" -H "$VERSION" \
        "$API/$2" > "$scratch/crlf-$n" || read_ok=0
    tr -d '\r' < "$scratch/crlf-$n" > "$scratch/raw-$n"
    rm -f "$scratch/crlf-$n"
    status=$(sed -n '1s/^HTTP\/[0-9.]* \([0-9][0-9]*\).*/\1/p' "$scratch/raw-$n")
    if [ "$read_ok" = 0 ] || [ -z "$status" ]; then
        rm -f "$scratch/raw-$n"
        echo "trial_p54_issue_lookup: GET /$2 with a token narrowed to $1: curl failed; nothing of it is kept" >&2
        exit 1
    fi
    (cd "$root" && python3 -m tools.redact_trial < "$scratch/raw-$n" > "$out/clean-$n") 2> "$out/redacted-$n"
    rm -f "$scratch/raw-$n"
    asked="$asked{\"n\": $n, \"as\": \"${slug}[bot]\", \"narrowed_to\": \"$1: read\", \"call\": \"GET /$2\","
    asked="$asked \"status\": $status},"
    echo "GET /$2, narrowed to $1: $status"
}

# A token for the Controller's installation narrowed to PERMISSION: read, each read made with it, then revoked.
with_token() {   # PERMISSION
    now=$(date +%s)
    header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
    claims=$(printf '{"iat":%d,"exp":%d,"iss":%d}' $((now - 60)) $((now + 540)) "$app_id" | b64url)
    signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
    jwt="$header.$claims.$signature"
    # GitHub's answer and its status are held in a variable, never a file, since a minted token is in the answer.
    # curl's own exit code comes last: a transfer that failed is never trusted, however whole its answer reads.
    minted=$(printf 'Authorization: Bearer %s\n' "$jwt" | curl -q -sS -w '\n%{http_code}' -X POST -H @- -H "$ACCEPT" \
        -H "$VERSION" -d "{\"repositories\":[\"$name\"],\"permissions\":{\"$1\":\"read\"}}" \
        "$API/app/installations/$installation/access_tokens" && printf '\n0' || printf '\n%s' "$?")
    jwt=""
    minted_exit=$(printf '%s\n' "$minted" | tail -n 1)
    minted=$(printf '%s\n' "$minted" | sed '$d')
    minted_status=$(printf '%s\n' "$minted" | tail -n 1)
    token=$(printf '%s\n' "$minted" | sed '$d' | python3 -I -c '
import json, sys
answer = json.load(sys.stdin)
print(answer.get("token") or "" if isinstance(answer, dict) else "")' 2>/dev/null || true)
    if [ "$minted_status" = 201 ] && { [ -z "$token" ] || [ "$minted_exit" != 0 ]; }; then
        # GitHub minted a token and its answer could not be read whole, or curl said the transfer failed: the token
        # may be live. It is revoked if it
        # can be found in what came back, and the Maintainer is told either way; nothing of the answer is kept.
        token=$(token_in "$minted")
        minted=""
        if [ -n "$token" ]; then
            revoked=$(revoke || true)
            token=""
            [ "$revoked" = 204 ] || unrevoked "a token narrowed to $1 whose answer was cut short" "$revoked"
        else
            echo "trial_p54_issue_lookup: $slug: GitHub minted a token narrowed to $1 and its answer was cut short; the" \
                "token may be live for up to an hour, and the Maintainer must revoke it by hand." >&2
        fi
        echo "trial_p54_issue_lookup: $slug: nothing read, and nothing of the answer kept." >&2
        exit 1
    fi
    if [ "$minted_status" != 201 ] && [ -z "$token" ]; then
        token=$(token_in "$minted")    # a refusal cut short may hold one all the same; the trap revokes it
    fi
    if [ "$minted_status" != 201 ] && [ -n "$token" ]; then
        # A token the refusal carried all the same is left set, for the exit trap to revoke; its answer is not shown.
        minted=""
        echo "trial_p54_issue_lookup: $slug: the mint answered ${minted_status:-none} and held a token all the same;" \
            "nothing read, and the token is revoked as the script stops." >&2
        exit 1
    fi
    if [ "$minted_status" != 201 ]; then
        # No token was minted, so the answer is GitHub's error: it is redacted before it is shown, and never written
        # to a file.
        echo "trial_p54_issue_lookup: $slug: no token narrowed to $1 was minted (status ${minted_status:-none});" \
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
    read_one "$1" "repos/$repo/issues/$issue"
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

with_token issues
with_token metadata
printf '[%s]\n' "${asked%,}" > "$out/requests.json"
echo "Done. Hand $out to a session; it holds no credential. Each token was revoked with status 204."
