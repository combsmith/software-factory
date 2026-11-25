#!/bin/sh
# Trial P-80, issue 1075: what the Controller App is answered, under a token narrower than the pass's and enough for
# them, for the two reads adapters/branches.py makes of a work branch: REST's pull request list filtered by head, which
# counts the pull requests the Factory opened for an issue, and the branch's ref, which reads its head (decisions 0068
# and 0242).
#
#   tools/trial_p80_branch_reads.sh OUT CONTROLLER_KEY REPO OPEN CLOSED MERGED BARE NEVER
#
# The Maintainer runs it at his own terminal, from anywhere; no session runs it, since it mints a credential.
# OUT is a directory that does not exist yet, outside this repo. CONTROLLER_KEY is the path of the Controller App's
# private key file, which only openssl reads. REPO is the canary, owner/name, which the Controller must be installed
# on (config/apps.json). Needs curl, openssl and python3, and no other login.
#
# The other five name work branches of REPO, each of the Factory's shape, factory-work/issue-N-k, and no two the same.
# Before the run, the Maintainer makes them so, with the trial-author App standing in for the App that
# opens the Factory's pull requests (tools/trial_as_app.sh open, which makes a branch, one commit and a pull request):
#   OPEN    the App's one pull request on it, left open;
#   CLOSED  the App's one pull request on it, closed unmerged, the branch kept;
#   MERGED  the App's one pull request on it, merged, then the branch deleted;
#   BARE    a branch that stands, with no pull request on it: one commit the Maintainer pushes himself, as a plain git
#           push of a new branch, since tools/trial_as_app.sh open always opens a pull request;
#   NEVER   a name no branch of REPO ever had.
# A pull request from a fork's branch of the same name is not asked: no account the Maintainer holds can fork REPO. The
# trial's page states it as a limit, and the port takes the unfavourable answer, that the head filter lists such a pull
# request: a branch from a fork is never the Factory's, and leaves the branch not told (adapters/branches.py).
#
# The pass condition, written before the run (docs/architecture/trials/P-80.md holds it whole):
#   pass: under a token for the Controller's installation narrowed to contents: read and pull_requests: read, on REPO
#   alone, the list of each of OPEN, CLOSED and MERGED is 200 with exactly one pull request: its head.ref the branch,
#   its head.repo.full_name REPO, its user.id the trial-author App's bot account's whole number and its user.type Bot,
#   in the state it was left in, and no link header naming a next page; the list of BARE and of NEVER is 200 and empty;
#   the ref of OPEN and of BARE is 200, its ref refs/heads/ and the branch, its object of type commit with a whole sha;
#   the ref of MERGED and of NEVER is 404.
#   fail otherwise.
#   Recorded, deciding nothing: CLOSED's ref, which the port never reads; and what a token narrowed to
#   pull_requests: read alone is answered for BARE's ref. REPO is public, so a grant it lacks may not show there
#   (decision 0068); a private repo is not asked here.
#
# Twice: once with a token narrowed to contents: read and pull_requests: read, which makes every branch's two reads,
# the list then the ref, in the order above; and once with one narrowed to pull_requests: read, which reads BARE's ref
# alone. Each time: sign a JWT with the key; mint a token for the Controller's installation that P-39 found
# (trials/P-39.grants.json), on REPO alone; make the reads; and revoke the token, recording the revocation's status.
# Each read is sent as the port sends it: the list's query built by urllib.parse.urlencode, the ref's path with the
# branch as it is. A token or a JWT is held in a shell variable only, reaches curl on its standard input, and is never
# printed, logged or written to a file. Each response is captured in a scratch directory outside the repo, redacted
# there by tools/redact_trial.py, and deleted; OUT receives only the redacted response (clean-N), what was asked
# (requests.json, each read with the branch it was of) and when the run started (ran_at). A read GitHub refuses is kept
# with its status. A session then builds the fixture from OUT alone.
#
# A mint that curl fails or GitHub refuses, or a revocation that does not return 204, stops the script with a
# non-zero exit; a refused mint shows its status and GitHub's answer, redacted, and a token that may be live is told
# to the Maintainer.
set -eu
set +x

if [ "$#" -ne 8 ]; then
    echo "usage: tools/trial_p80_branch_reads.sh OUT CONTROLLER_KEY REPO OPEN CLOSED MERGED BARE NEVER" >&2
    exit 2
fi
root=$(cd "$(dirname "$0")/.." && pwd -P)
if [ -e "$1" ] || [ -L "$1" ]; then
    echo "trial_p80_branch_reads: $1 exists; name a new directory" >&2
    exit 2
fi
# OUT is read as the file system resolves it, every link and .. followed, before it is held to be outside the repo.
if ! parent=$(CDPATH= cd "$(dirname -- "$1")" 2>/dev/null && pwd -P); then
    echo "trial_p80_branch_reads: the directory that would hold $1 does not exist; make it first" >&2
    exit 2
fi
out=$parent/$(basename -- "$1")
case "$out/" in "$root"/*)
    echo "trial_p80_branch_reads: $out is inside the repo; name a directory outside it" >&2
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
        echo "trial_p80_branch_reads: $above is another user's, or can be written by other users and is not sticky, or an ACL may let them; name a directory" \
            "under one only you can write to" >&2
        exit 2
    fi
    [ "$above" = / ] && break
    above=$(dirname -- "$above")
done
key=$2
if [ ! -r "$key" ]; then
    echo "trial_p80_branch_reads: cannot read the key file $key" >&2
    exit 2
fi
repo=$3
# A repo is one word of the shape GitHub allows, so it reaches the URL as nothing else.
case "$repo" in
    */*/*|/*|*/|-*|*[!A-Za-z0-9._/-]*) echo "trial_p80_branch_reads: $repo is not owner/name" >&2; exit 2 ;;
    */*) ;;
    *) echo "trial_p80_branch_reads: $repo is not owner/name" >&2; exit 2 ;;
esac
open=$4 closed=$5 merged=$6 bare=$7 never=$8

API=https://api.github.com
VERSION="X-GitHub-Api-Version: 2022-11-28"
ACCEPT="Accept: application/vnd.github+json"
# The raw answers are kept outside the repo, as OUT is: a TMPDIR inside it, or a link into it, is refused.
# The template names TMPDIR itself: macOS's mktemp -d alone does not always read it.
# Its own line: inside the cd, a failed mktemp would be read as the directory this stands in, which the clean-up removes.
made=$(mktemp -d "${TMPDIR:-/tmp}/trial-p80.XXXXXX")
scratch=$(cd "$made" && pwd -P)
case "$scratch/" in "$root"/*)
    rm -rf "$scratch"
    echo "trial_p80_branch_reads: the scratch directory $scratch is inside the repo; set TMPDIR outside it" >&2
    exit 2 ;;
esac
token=""

revoke() {
    printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -o /dev/null -w '%{http_code}' -X DELETE -H @- \
        -H "$ACCEPT" -H "$VERSION" "$API/installation/token"
}

unrevoked() {
    echo "trial_p80_branch_reads: $1: revoking its token returned $2, not 204. The token may be live for up to an hour;" \
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
    if [ -z "$token" ] && [ -n "${minted:-}" ]; then
        token=$(token_in "$minted")
        minted=""
    fi
    if [ -n "$token" ]; then
        last=$(revoke || true)
        echo "trial_p80_branch_reads: stopped with a token live; revoking it returned $last" >&2
        [ "$last" = 204 ] || unrevoked "the token live when the script stopped" "$last"
        token=""
    elif [ -n "${minting:-}" ]; then
        # Stopped while the mint was asked: its answer never came back here, and GitHub may have minted one.
        echo "trial_p80_branch_reads: stopped while a token was being minted; GitHub may have minted one, live for up to" \
            "an hour, and the Maintainer must revoke it by hand." >&2
    fi
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM

# Checked once the exit trap stands, after the scratch directory's refusal: python3 may write to TMPDIR as it starts.
# Each branch is a work branch's name, whole, as kernel/terms.py's WORK_BRANCH spells one, so it reaches the URL as
# nothing else; and no two are one branch, since each stands in one state.
if ! problem=$(python3 -I -c '
import re, sys
names = sys.argv[1:]
for name in names:
    if not re.fullmatch(r"factory-work/issue-[1-9][0-9]*-[1-9][0-9]*", name):
        sys.exit("%r is not a work branch'"'"'s name, factory-work/issue-N-k" % name)
twice = sorted({n for n in names if names.count(n) > 1})
if twice:
    sys.exit("%s is named twice; each branch stands in one state" % twice[0])
' "$open" "$closed" "$merged" "$bare" "$never" 2>&1); then
    echo "trial_p80_branch_reads: ${problem:-the branches could not be read}" >&2
    exit 2
fi

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# The Controller's name, id and installation, as the data and P-39's first reads give them; REPO must be one the data
# installs the Controller on, and the Factory's own repo is not asked.
ids=$(cd "$root" && python3 -I -c '
import json, sys
app = json.load(open("config/apps.json"))["apps"]["controller"]
if sys.argv[1] not in app["installed_on"] or sys.argv[1] == "combsmith/software-factory":
    sys.exit("trial_p80_branch_reads: %s is not the canary the Controller is installed on" % sys.argv[1])
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
    echo "trial_p80_branch_reads: $out could not be made new by this run (made since, or refused); name a new directory" >&2
    exit 2
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"
asked=""
n=0

# One read with the live token: the redacted answer goes to OUT as clean-N, and what was asked to requests.json, with
# the branch it reads and the state that branch stands in.
read_one() {   # NARROWED PATH STATE BRANCH
    n=$((n + 1))
    read_ok=1
    # curl is the last command of the pipeline, so its exit is the pipeline's; nothing after it hides a failure.
    printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -i -H @- -H "$ACCEPT" -H "$VERSION" \
        "$API/$2" > "$scratch/crlf-$n" || read_ok=0
    tr -d '\r' < "$scratch/crlf-$n" > "$scratch/raw-$n"
    rm -f "$scratch/crlf-$n"
    # The last head's status: a proxy's block, or an interim answer, comes first and is no answer to this read.
    status=$(awk 'BEGIN { head = 1 } { sub(/\r$/, "") } head && $0 != "" { if (/^HTTP\/[0-9.]+ [0-9]+/) found = $2; else exit } { head = ($0 == "") } END { print found }' "$scratch/raw-$n")
    if [ "$read_ok" = 0 ] || [ -z "$status" ]; then
        rm -f "$scratch/raw-$n"
        echo "trial_p80_branch_reads: GET /$2 with a token narrowed to $1: curl failed; nothing of it is kept" >&2
        exit 1
    fi
    (cd "$root" && python3 -m tools.redact_trial < "$scratch/raw-$n" > "$out/clean-$n") 2> "$out/redacted-$n"
    rm -f "$scratch/raw-$n"
    asked="$asked{\"n\": $n, \"as\": \"${slug}[bot]\", \"narrowed_to\": \"$1\", \"call\": \"GET /$2\","
    asked="$asked \"of\": \"$3\", \"branch\": \"$4\", \"status\": $status},"
    echo "GET /$2, narrowed to $1: $status"
}

# A branch's two reads, as adapters/branches.py makes them: its pull requests in every state, by REST's head filter on
# REPO's owner, the query built as the port builds it; then its ref, the branch written into the path as it is.
branch_reads() {   # NARROWED STATE BRANCH
    query=$(python3 -I -c '
import sys, urllib.parse
print(urllib.parse.urlencode({"state": "all", "head": sys.argv[1].split("/")[0] + ":" + sys.argv[2], "per_page": 100}))
' "$repo" "$3")
    read_one "$1" "repos/$repo/pulls?$query" "$2" "$3"
    read_one "$1" "repos/$repo/git/ref/heads/$3" "$2" "$3"
}

# A token for the Controller's installation narrowed to NARROWED, its permissions PERMISSIONS as the mint takes them,
# each read of the run made with it in turn, then revoked.
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
    jwt="" minting=""
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
            echo "trial_p80_branch_reads: $slug: GitHub minted a token narrowed to $1 and its answer was cut short; the" \
                "token may be live for up to an hour, and the Maintainer must revoke it by hand." >&2
        fi
        echo "trial_p80_branch_reads: $slug: nothing read, and nothing of the answer kept." >&2
        exit 1
    fi
    if [ "$minted_status" != 201 ] && [ -z "$token" ]; then
        token=$(token_in "$minted")    # a refusal cut short may hold one all the same; the trap revokes it
    fi
    if [ "$minted_status" != 201 ] && [ -n "$token" ]; then
        # A token the refusal carried all the same is left set, for the exit trap to revoke; its answer is not shown.
        minted=""
        echo "trial_p80_branch_reads: $slug: the mint answered ${minted_status:-none} and held a token all the same;" \
            "nothing read, and the token is revoked as the script stops." >&2
        exit 1
    fi
    if [ "$minted_status" != 201 ]; then
        # No token was minted, so the answer is GitHub's error: it is redacted before it is shown, and never written
        # to a file.
        echo "trial_p80_branch_reads: $slug: no token narrowed to $1 was minted (status ${minted_status:-none});" \
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
    if [ "$2" = "$BOTH" ]; then
        branch_reads "$1" open "$open"
        branch_reads "$1" closed "$closed"
        branch_reads "$1" merged "$merged"
        branch_reads "$1" bare "$bare"
        branch_reads "$1" never "$never"
    else
        read_one "$1" "repos/$repo/git/ref/heads/$bare" bare "$bare"
    fi
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

BOTH='"contents":"read","pull_requests":"read"'
with_token "contents: read and pull_requests: read" "$BOTH"
with_token "pull_requests: read" '"pull_requests":"read"'
printf '[%s]\n' "${asked%,}" > "$out/requests.json"
echo "Done. Hand $out to a session; it holds no credential. Each token was revoked with status 204."
