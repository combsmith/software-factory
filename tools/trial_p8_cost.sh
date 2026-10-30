#!/bin/sh
# Trial P-8, the cost of a pass: what one pass over every open item costs in GraphQL points (issue 13, design
# section 6, P-8 and P-32; the Maintainer's working ruling of 2026-10-19 on issue 13).
#
#   tools/trial_p8_cost.sh OUT READER_KEY OWNER/REPO [OWNER/REPO ...]
#
# The Maintainer runs it at his own terminal, from anywhere; no session runs it, since it mints a credential.
# OUT is a directory that does not exist yet, outside this repo. READER_KEY is the path of the reader App's private
# key file, which only openssl reads. Each OWNER/REPO is a repo the reader App's installation reaches
# (trials/P-39.reach.json). Needs curl, openssl and python3; no gh login is used.
#
# It signs a JWT with the reader App's key, mints a token for the installation P-39 found (trials/P-39.grants.json),
# narrowed to metadata, pull_requests, issues and checks, each read, and makes these GraphQL reads with it, in order:
#   1. the counts of open pull requests and open issues in every repo given, in one query (what a pass reads first,
#      so that it can size the next read);
#   2. for each repo, the pass's read shaped as the design has it (section 4.1, "What a pass reads", and section
#      3.3): the full facts of each open pull request, and the two-depth listing of each open issue, with P-32's
#      question answered in the same read, its top-level pages sized to the counts of step 1;
#   3. for each repo, the same read with both top-level pages a hundred wide, the design's "a hundred to a request",
#      whatever the counts, so that the two sizings can be compared.
# Then it revokes the token and records the revocation's status. GitHub reports each read's cost in `rateLimit` of
# the same response, which is where the fixture takes it from, with the response's `date`. A token or a JWT is held
# in a shell variable only, reaches curl on its standard input, and is never printed, logged or written to a file.
# Each response is captured in a scratch directory outside the repo, redacted there by tools/redact_trial.py, and
# deleted; OUT receives only the redacted responses (clean-N), what was asked (requests.json: each read's call and
# its variables, never the credential) and when the run started (ran_at). A session then builds the fixtures from
# OUT alone.
#
# A mint, or a read, that curl fails or GitHub refuses, or a revocation that does not return 204, stops the script
# with a non-zero exit: what was read is not kept, a refused mint shows its status and GitHub's answer, redacted,
# and a token that may be live is told to the Maintainer. A mint GitHub answered 201 whose token cannot be read is
# written nowhere, not even to scratch: its token is revoked if it can be found in the answer, and the Maintainer is
# told it may be live if not.
set -eu
set +x
unset CURL_HOME

if [ "$#" -lt 3 ]; then
    echo "usage: tools/trial_p8_cost.sh OUT READER_KEY OWNER/REPO [OWNER/REPO ...]" >&2
    exit 2
fi
root=$(cd "$(dirname "$0")/.." && pwd -P)
if [ -e "$1" ] || [ -L "$1" ]; then
    echo "trial_p8_cost: $1 exists; name a new directory" >&2
    exit 2
fi
# OUT is read as the file system resolves it, every link and .. followed, before it is held to be outside the repo.
if ! parent=$(CDPATH= cd "$(dirname -- "$1")" 2>/dev/null && pwd -P); then
    echo "trial_p8_cost: the directory that would hold $1 does not exist; make it first" >&2
    exit 2
fi
out=$parent/$(basename -- "$1")
case "$out/" in "$root"/*)
    echo "trial_p8_cost: $out is inside the repo; name a directory outside it" >&2
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
        echo "trial_p8_cost: $above is another user's, or can be written by other users and is not sticky; name a directory" \
            "under one only you can write to" >&2
        exit 2
    fi
    [ "$above" = / ] && break
    above=$(dirname -- "$above")
done
key=$2
if [ ! -r "$key" ]; then
    echo "trial_p8_cost: cannot read the key file $key" >&2
    exit 2
fi
shift 2
# A repo is OWNER/REPO in the characters GitHub allows, and nothing else: its words reach a query and a shell expansion.
for repo in "$@"; do
    if ! printf '%s\n' "$repo" | grep -Eq '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$'; then
        echo "trial_p8_cost: $repo is not OWNER/REPO" >&2
        exit 2
    fi
done

API=https://api.github.com
VERSION="X-GitHub-Api-Version: 2022-11-28"
ACCEPT="Accept: application/vnd.github+json"
JSON="Content-Type: application/json"
scratch=$(mktemp -d)
case "$scratch/" in "$root"/*)
    rmdir "$scratch"
    echo "trial_p8_cost: the scratch directory $scratch is inside the repo; set TMPDIR outside it" >&2
    exit 2 ;;
esac
token=""

revoke() {
    printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -o /dev/null -w '%{http_code}' -X DELETE -H @- \
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
    echo "trial_p8_cost: revoking the token returned $1, not 204. The token may be live for up to an hour;" \
        "the Maintainer must revoke it by hand." >&2
}

finish() {
    if [ -z "$token" ] && [ -n "${minted:-}" ]; then
        token=$(token_in "$minted")
        minted=""
    fi
    if [ -n "$token" ]; then
        last=$(revoke || true)
        echo "trial_p8_cost: stopped with a token live; revoking it returned $last" >&2
        [ "$last" = 204 ] || unrevoked "$last"
        token=""
    fi
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

repos=$*

# The reader App's id and installation, as the data and P-39's first reads give them.
ids=$(cd "$root" && python3 -I -c '
import json
app = json.load(open("config/apps.json"))["apps"]["reader"]
fixture = json.load(open("trials/P-39.grants.json"))
read = [e for e in fixture["exchanges"] if e["request"]["call"] == "GET /orgs/combsmith/installations"]
found = {i["app_id"]: i["id"] for i in read[0]["response"]["body"]["installations"]}
print("%s %d %d" % (app["name"], app["app_id"], found[app["app_id"]]))
')
# shellcheck disable=SC2086  # the three words are split on purpose
set -- $ids
slug=$1 app_id=$2 installation=$3

# OUT is made here, by this script alone and for its user alone: one made since it was found absent is refused,
# never written into, since what is in it may be a link to a file this run would overwrite.
if ! mkdir -m 700 "$out"; then
    echo "trial_p8_cost: $out could not be made new by this run (made since, or refused); name a new directory" >&2
    exit 2
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"

# The pass's read, as the design shapes it. Its variables size each page; a connection's own count and whether a
# further page exists are read with it, so that a list read short is known to be short (section 3.3, `complete`).
PASS=$(cat <<'EOF'
query Pass($owner: String!, $name: String!, $prs: Int!, $issues: Int!, $files: Int!, $reviews: Int!, $threads: Int!, $checks: Int!, $events: Int!, $labels: Int!, $issueEvents: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    pullRequests(states: OPEN, first: $prs, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage }
      nodes {
        number
        state
        isDraft
        author { login __typename }
        authorAssociation
        isCrossRepository
        headRefOid
        baseRefOid
        baseRefName
        baseRef { branchProtectionRule { id } refUpdateRule { requiredApprovingReviewCount } }
        mergeable
        changedFiles
        additions
        deletions
        updatedAt
        files(first: $files) { totalCount pageInfo { hasNextPage } nodes { path changeType } }
        labels(first: $labels) { totalCount pageInfo { hasNextPage } nodes { name } }
        reviews(first: $reviews) {
          totalCount
          pageInfo { hasNextPage }
          nodes { databaseId author { login __typename } authorAssociation state commit { oid } submittedAt }
        }
        reviewThreads(first: $threads) {
          totalCount
          pageInfo { hasNextPage }
          nodes {
            id isResolved isOutdated path line
            resolvedBy { login }
            comments(first: 1) { nodes { author { login __typename } authorAssociation createdAt } }
          }
        }
        commits(last: 1) {
          nodes {
            commit {
              oid
              committedDate
              statusCheckRollup {
                state
                contexts(first: $checks) {
                  totalCount
                  pageInfo { hasNextPage }
                  nodes {
                    __typename
                    ... on CheckRun {
                      name conclusion status completedAt
                      checkSuite { app { databaseId } workflowRun { file { path } } }
                    }
                    ... on StatusContext { context state createdAt }
                  }
                }
              }
            }
          }
        }
        timelineItems(first: $events, itemTypes: [LABELED_EVENT, UNLABELED_EVENT, REVIEW_DISMISSED_EVENT, ADDED_TO_MERGE_QUEUE_EVENT, REMOVED_FROM_MERGE_QUEUE_EVENT, READY_FOR_REVIEW_EVENT, CONVERT_TO_DRAFT_EVENT]) {
          totalCount
          pageInfo { hasNextPage }
          nodes {
            __typename
            ... on LabeledEvent { actor { login __typename } label { name } createdAt }
            ... on UnlabeledEvent { actor { login __typename } label { name } createdAt }
            ... on ReviewDismissedEvent { actor { login __typename } previousReviewState createdAt review { databaseId } }
            ... on AddedToMergeQueueEvent { actor { login __typename } createdAt }
            ... on RemovedFromMergeQueueEvent { actor { login __typename } createdAt }
            ... on ReadyForReviewEvent { actor { login __typename } createdAt }
            ... on ConvertToDraftEvent { actor { login __typename } createdAt }
          }
        }
        mergeQueueEntry { state position }
        closingIssuesReferences(first: 10) { totalCount nodes { number } }
      }
    }
    issues(states: OPEN, first: $issues, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage }
      nodes {
        number
        author { login __typename }
        authorAssociation
        createdAt
        updatedAt
        labels(first: $labels) { totalCount pageInfo { hasNextPage } nodes { name } }
        timelineItems(first: $issueEvents, itemTypes: [LABELED_EVENT, UNLABELED_EVENT]) {
          totalCount
          pageInfo { hasNextPage }
          nodes {
            __typename
            ... on LabeledEvent { actor { login __typename } label { name } createdAt }
            ... on UnlabeledEvent { actor { login __typename } label { name } createdAt }
          }
        }
        closedByPullRequestsReferences(first: 10, includeClosedPrs: false) {
          totalCount
          nodes { number isDraft author { login __typename } }
        }
      }
    }
  }
  rateLimit { cost nodeCount used remaining limit resetAt }
}
EOF
)
# The pages below the top level, the same for every read, a hundred wide: a list longer than that says so in its
# pageInfo, and a pass reads the rest a page at a time. On 2026-10-20 some pull requests' timelines, reviews, files
# and checks, and some issues' timelines, ran past a hundred.
FILES=100 REVIEWS=100 THREADS=100 CHECKS=100 EVENTS=100 LABELS=20 ISSUE_EVENTS=100

n=0
asked=""

# One GraphQL read, with the token: the body is built by python from the query and its variables, written in the
# scratch directory (it holds no credential), sent with curl -i, and the response redacted into OUT as clean-N.
graphql() {   # QUERY VARIABLES_JSON CALL
    n=$((n + 1))
    printf '%s' "$1" | python3 -I -c '
import json, sys
json.dump({"query": sys.stdin.read(), "variables": json.loads(sys.argv[1])}, open(sys.argv[2], "w"))' \
        "$2" "$scratch/body-$n"
    read_ok=1
    printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -i -X POST -H @- -H "$ACCEPT" -H "$VERSION" -H "$JSON" \
        --data-binary "@$scratch/body-$n" "$API/graphql" > "$scratch/crlf-$n" || read_ok=0
    tr -d '\r' < "$scratch/crlf-$n" > "$scratch/raw-$n"
    rm -f "$scratch/crlf-$n" "$scratch/body-$n"
    status=$(sed -n '1s/^HTTP\/[0-9.]* \([0-9][0-9]*\).*/\1/p' "$scratch/raw-$n")
    if [ "$read_ok" = 0 ] || [ "$status" != 200 ]; then
        rm -f "$scratch/raw-$n"
        echo "trial_p8_cost: read $n ($3) failed (curl ok: $read_ok, status: ${status:-none}); nothing of it is kept." >&2
        exit 1
    fi
    (cd "$root" && python3 -m tools.redact_trial < "$scratch/raw-$n" > "$out/clean-$n") 2> "$out/redacted-$n"
    rm -f "$scratch/raw-$n"
    # A 200 can carry errors beside partial data, as a read past GitHub's node limit does: that is not a pass's read.
    if ! sed -n '/^{/,$p' "$out/clean-$n" | python3 -I -c '
import json, sys
answer = json.load(sys.stdin)
sys.exit(1 if not isinstance(answer, dict) or "errors" in answer or not answer.get("data") else 0)'; then
        echo "trial_p8_cost: read $n ($3) answered 200 with errors or no data; it is kept, redacted, as clean-$n, and the" \
            "run stops." >&2
        exit 1
    fi
    asked="$asked{\"n\": $n, \"call\": \"$3\", \"variables\": $2},"
    echo "read $n: $3"
}

# The token, minted and held in a variable only.
now=$(date +%s)
header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
claims=$(printf '{"iat":%d,"exp":%d,"iss":%d}' $((now - 60)) $((now + 540)) "$app_id" | b64url)
signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
jwt="$header.$claims.$signature"
minted=$(printf 'Authorization: Bearer %s\n' "$jwt" | curl -q -sS -w '\n%{http_code}' -X POST -H @- -H "$ACCEPT" \
    -H "$VERSION" -d '{"permissions":{"metadata":"read","pull_requests":"read","issues":"read","checks":"read"}}' \
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
        [ "$revoked" = 204 ] || unrevoked "$revoked"
    else
        echo "trial_p8_cost: $slug: GitHub minted a token for installation $installation and its answer could not" \
            "be read; the token may be live for up to an hour, and the Maintainer must revoke it by hand." >&2
    fi
    echo "trial_p8_cost: $slug: nothing read, and nothing of the answer kept." >&2
    exit 1
fi
if [ "$minted_status" != 201 ] && [ -z "$token" ]; then
    token=$(token_in "$minted")    # a refusal cut short may hold one all the same; the trap revokes it
fi
if [ "$minted_status" != 201 ] && [ -n "$token" ]; then
    # A token the refusal carried all the same is left set, for the exit trap to revoke; its answer is not shown.
    minted=""
    echo "trial_p8_cost: $slug: the mint answered ${minted_status:-none} and held a token all the same;" \
        "nothing read, and the token is revoked as the script stops." >&2
    exit 1
fi
if [ "$minted_status" != 201 ]; then
    # No token was minted, so the answer is GitHub's error: it is redacted before it is shown, and never written to a
    # file.
    echo "trial_p8_cost: $slug: no token was minted for installation $installation (status ${minted_status:-none});" \
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

# 1. The counts, in one query: an alias r0, r1, ... for each repo given.
# shellcheck disable=SC2086  # one repo a line
counts=$(printf '%s\n' $repos | python3 -I -c '
import json, sys
repos = [line.split("/", 1) for line in sys.stdin.read().split()]
fields = " ".join("r%d: repository(owner: \"%s\", name: \"%s\") { nameWithOwner pullRequests(states: OPEN) { totalCount } "
                  "issues(states: OPEN) { totalCount } }" % (i, owner, name) for i, (owner, name) in enumerate(repos))
print("query Counts { %s rateLimit { cost nodeCount used remaining limit resetAt } }" % fields)')
graphql "$counts" '{}' "POST /graphql, Counts: the open pull requests and issues of each repo, one query"

# 2. For each repo, the pass's read with its top-level pages sized to the counts, a hundred at most.
# shellcheck disable=SC2086  # one repo a line
sizes=$(sed -n '/^{/,$p' "$out/clean-1" | python3 -I -c '
import json, sys
data = json.load(sys.stdin)["data"]
for i in range(len(sys.argv) - 1):
    repo = data["r%d" % i]
    print(sys.argv[i + 1], min(repo["pullRequests"]["totalCount"], 100), min(repo["issues"]["totalCount"], 100))' $repos)
below="\"files\": $FILES, \"reviews\": $REVIEWS, \"threads\": $THREADS, \"checks\": $CHECKS, \"events\": $EVENTS, \"labels\": $LABELS, \"issueEvents\": $ISSUE_EVENTS"
# shellcheck disable=SC2086  # one line a repo: its name, its open pull requests and its open issues
set -- $sizes
while [ "$#" -ge 3 ]; do
    repo=$1 prs=$2 issues=$3
    shift 3
    graphql "$PASS" "{\"owner\": \"${repo%/*}\", \"name\": \"${repo#*/}\", \"prs\": $prs, \"issues\": $issues, $below}" \
        "POST /graphql, Pass: $repo, the top-level pages sized to the counts ($prs pull requests, $issues issues)"
done

# 3. For each repo, the same read with both top-level pages a hundred wide.
for repo in $repos; do
    graphql "$PASS" "{\"owner\": \"${repo%/*}\", \"name\": \"${repo#*/}\", \"prs\": 100, \"issues\": 100, $below}" \
        "POST /graphql, Pass: $repo, both top-level pages a hundred wide"
done

revoked=$(revoke || true)
if [ "$revoked" != 204 ]; then
    unrevoked "$revoked"
    exit 1
fi
token=""
printf '{"as": "%s", "app_id": %d, "installation": %d, "revoked": "%s", "reads": [%s]}\n' \
    "$slug" "$app_id" "$installation" "$revoked" "${asked%,}" > "$out/requests.json"
echo "Done. Hand $out to a session; it holds no credential. The token was revoked with status $revoked."
