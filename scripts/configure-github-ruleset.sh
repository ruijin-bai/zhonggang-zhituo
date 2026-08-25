#!/usr/bin/env bash

set -euo pipefail

RULESET_NAME="main-protection"
REPOSITORY=""
DRY_RUN=false

usage() {
  cat <<'EOF'
Configure the GitHub ruleset for the main branch.

Usage:
  ./scripts/configure-github-ruleset.sh [--repo OWNER/REPO] [--dry-run]

Options:
  --repo OWNER/REPO  Configure an explicit repository instead of the current one.
  --dry-run          Print the desired ruleset without changing GitHub.
  -h, --help         Show this help.
EOF
}

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

while (($# > 0)); do
  case "$1" in
    --repo)
      (($# >= 2)) || fail "--repo requires OWNER/REPO"
      REPOSITORY="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

command -v gh >/dev/null 2>&1 || fail "GitHub CLI (gh) is not installed"
gh auth status --hostname github.com >/dev/null 2>&1 || \
  fail "GitHub CLI is not authenticated; run: gh auth login"

if [[ -z "$REPOSITORY" ]]; then
  REPOSITORY="$(gh repo view --json nameWithOwner --jq '.nameWithOwner')"
fi

[[ "$REPOSITORY" =~ ^[^/[:space:]]+/[^/[:space:]]+$ ]] || \
  fail "invalid repository: $REPOSITORY (expected OWNER/REPO)"

DEFAULT_BRANCH="$(gh api "repos/$REPOSITORY" --jq '.default_branch')"
[[ "$DEFAULT_BRANCH" == "main" ]] || \
  fail "default branch is '$DEFAULT_BRANCH', not 'main'; no changes were made"

MERGE_METHOD_AVAILABLE="$(
  gh api "repos/$REPOSITORY" \
    --jq '(.allow_squash_merge == true) or (.allow_rebase_merge == true)'
)"
[[ "$MERGE_METHOD_AVAILABLE" == "true" ]] || \
  fail "linear history requires squash or rebase merging to be enabled"

PAYLOAD_FILE="$(mktemp)"
trap 'rm -f -- "$PAYLOAD_FILE"' EXIT

cat >"$PAYLOAD_FILE" <<EOF
{
  "name": "$RULESET_NAME",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"],
      "exclude": []
    }
  },
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "required_linear_history"},
    {
      "type": "pull_request",
      "parameters": {
        "allowed_merge_methods": ["squash", "rebase"],
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          {"context": "zhituo/ci-gate"}
        ],
        "strict_required_status_checks_policy": true
      }
    }
  ]
}
EOF

printf 'Repository: %s\nRuleset:   %s\n' "$REPOSITORY" "$RULESET_NAME"

if [[ "$DRY_RUN" == "true" ]]; then
  printf '\nDry run; GitHub was not changed. Desired payload:\n'
  if command -v python >/dev/null 2>&1; then
    python -m json.tool "$PAYLOAD_FILE"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m json.tool "$PAYLOAD_FILE"
  else
    command cat "$PAYLOAD_FILE"
  fi
  exit 0
fi

mapfile -t MATCHING_RULESET_IDS < <(
  gh api --paginate \
    "repos/$REPOSITORY/rulesets?includes_parents=false&targets=branch&per_page=100" \
    --jq ".[] | select(.name == \"$RULESET_NAME\") | .id"
)

if ((${#MATCHING_RULESET_IDS[@]} > 1)); then
  fail "found multiple repository rulesets named '$RULESET_NAME'; resolve duplicates first"
fi

if ((${#MATCHING_RULESET_IDS[@]} == 1)); then
  RULESET_ID="${MATCHING_RULESET_IDS[0]}"
  gh api --method PUT "repos/$REPOSITORY/rulesets/$RULESET_ID" \
    --input "$PAYLOAD_FILE" --silent
  ACTION="updated"
else
  RULESET_ID="$(
    gh api --method POST "repos/$REPOSITORY/rulesets" \
      --input "$PAYLOAD_FILE" --jq '.id'
  )"
  ACTION="created"
fi

VERIFICATION="$(
  gh api "repos/$REPOSITORY/rulesets/$RULESET_ID" --jq '
    [
      .name,
      .target,
      .enforcement,
      (.bypass_actors | length | tostring),
      (.conditions.ref_name.include | join(",")),
      ([.rules[].type] | sort | join(",")),
      (.rules[] | select(.type == "pull_request") | .parameters.required_approving_review_count | tostring),
      (.rules[] | select(.type == "required_status_checks") | .parameters.required_status_checks | map(.context) | join(",")),
      (.rules[] | select(.type == "required_status_checks") | .parameters.strict_required_status_checks_policy | tostring)
    ] | @tsv'
)"

IFS=$'\t' read -r \
  ACTUAL_NAME ACTUAL_TARGET ACTUAL_ENFORCEMENT ACTUAL_BYPASS_COUNT \
  ACTUAL_INCLUDE ACTUAL_RULE_TYPES ACTUAL_APPROVALS ACTUAL_CHECKS ACTUAL_STRICT \
  <<<"$VERIFICATION"

EXPECTED_RULE_TYPES="deletion,non_fast_forward,pull_request,required_linear_history,required_status_checks"

[[ "$ACTUAL_NAME" == "$RULESET_NAME" ]] || fail "verification failed: ruleset name"
[[ "$ACTUAL_TARGET" == "branch" ]] || fail "verification failed: target"
[[ "$ACTUAL_ENFORCEMENT" == "active" ]] || fail "verification failed: enforcement"
[[ "$ACTUAL_BYPASS_COUNT" == "0" ]] || fail "verification failed: bypass actors"
[[ "$ACTUAL_INCLUDE" == "refs/heads/main" ]] || fail "verification failed: target branch"
[[ "$ACTUAL_RULE_TYPES" == "$EXPECTED_RULE_TYPES" ]] || fail "verification failed: rule types"
[[ "$ACTUAL_APPROVALS" == "0" ]] || fail "verification failed: approvals"
[[ "$ACTUAL_CHECKS" == "zhituo/ci-gate" ]] || fail "verification failed: required status"
[[ "$ACTUAL_STRICT" == "true" ]] || fail "verification failed: latest-main policy"

printf 'Ruleset %s and verified (id=%s).\n' "$ACTION" "$RULESET_ID"
printf 'URL: https://github.com/%s/settings/rules/%s\n' "$REPOSITORY" "$RULESET_ID"

if gh api "repos/$REPOSITORY/branches/main/protection" --silent >/dev/null 2>&1; then
  printf '%s\n' \
    "warning: classic branch protection also exists and may add stricter requirements." >&2
fi
