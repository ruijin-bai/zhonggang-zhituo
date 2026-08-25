#!/usr/bin/env bash
set -euo pipefail

RULESET_NAME="${RULESET_NAME:-main-production-protection}"
REQUIRED_CHECK="${REQUIRED_CHECK:-zhituo/ci-gate}"
API_VERSION="${GITHUB_API_VERSION:-2022-11-28}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '==> %s\n' "$*"
}

command -v gh >/dev/null 2>&1 || fail "GitHub CLI (gh) is required: https://cli.github.com/"
command -v jq >/dev/null 2>&1 || fail "jq is required"

gh auth status >/dev/null 2>&1 || fail "GitHub CLI is not authenticated. Run: gh auth login"

REPO="${1:-${GH_REPO:-}}"
if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi
[[ "$REPO" =~ ^[^/]+/[^/]+$ ]] || fail "Cannot determine repository. Run inside the repo or pass OWNER/REPO as the first argument."

info "Repository: $REPO"
info "Ruleset: $RULESET_NAME"
info "Required status: $REQUIRED_CHECK"

ADMIN="$(gh api -H "X-GitHub-Api-Version: $API_VERSION" "repos/$REPO" --jq '.permissions.admin // false')"
[[ "$ADMIN" == "true" ]] || fail "The authenticated account needs repository Administration permission."

DEFAULT_BRANCH="$(gh api -H "X-GitHub-Api-Version: $API_VERSION" "repos/$REPO" --jq '.default_branch')"
[[ -n "$DEFAULT_BRANCH" ]] || fail "Unable to resolve the default branch."
info "Default branch: $DEFAULT_BRANCH"

# Prevent a typo in the required status context from deadlocking the default branch.
STATUS_PRESENT="$(
  gh api -H "X-GitHub-Api-Version: $API_VERSION" "repos/$REPO/commits/$DEFAULT_BRANCH/status" 2>/dev/null \
    | jq --arg context "$REQUIRED_CHECK" '[.statuses[]? | select(.context == $context)] | length' \
    || printf '0'
)"
[[ "$STATUS_PRESENT" =~ ^[0-9]+$ ]] || fail "Unable to inspect recent commit statuses."
[[ "$STATUS_PRESENT" -gt 0 ]] || fail "Required status '$REQUIRED_CHECK' was not found on the current $DEFAULT_BRANCH commit. Run CI successfully first or override REQUIRED_CHECK explicitly."

PAYLOAD="$(mktemp)"
trap 'rm -f "$PAYLOAD"' EXIT

jq -n \
  --arg name "$RULESET_NAME" \
  --arg check "$REQUIRED_CHECK" \
  '{
    name: $name,
    target: "branch",
    enforcement: "active",
    bypass_actors: [],
    conditions: {
      ref_name: {
        include: ["~DEFAULT_BRANCH"],
        exclude: []
      }
    },
    rules: [
      {type: "deletion"},
      {type: "non_fast_forward"},
      {type: "required_linear_history"},
      {
        type: "pull_request",
        parameters: {
          allowed_merge_methods: ["squash"],
          dismiss_stale_reviews_on_push: false,
          require_code_owner_review: false,
          require_last_push_approval: false,
          required_approving_review_count: 0,
          required_review_thread_resolution: true
        }
      },
      {
        type: "required_status_checks",
        parameters: {
          do_not_enforce_on_create: false,
          required_status_checks: [
            {context: $check}
          ],
          strict_required_status_checks_policy: true
        }
      }
    ]
  }' > "$PAYLOAD"

EXISTING_ID="$(
  gh api -H "X-GitHub-Api-Version: $API_VERSION" "repos/$REPO/rulesets?includes_parents=false" --paginate \
    | jq --arg name "$RULESET_NAME" -r '.[] | select(.name == $name and .source_type == "Repository") | .id' \
    | head -n 1
)"

if [[ -n "$EXISTING_ID" ]]; then
  info "Updating existing ruleset ID $EXISTING_ID"
  gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: $API_VERSION" \
    "repos/$REPO/rulesets/$EXISTING_ID" \
    --input "$PAYLOAD" >/dev/null
  RULESET_ID="$EXISTING_ID"
else
  info "Creating repository ruleset"
  RULESET_ID="$(
    gh api \
      --method POST \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: $API_VERSION" \
      "repos/$REPO/rulesets" \
      --input "$PAYLOAD" \
      --jq '.id'
  )"
fi

info "Verifying active ruleset"
gh api \
  -H "X-GitHub-Api-Version: $API_VERSION" \
  "repos/$REPO/rulesets/$RULESET_ID" \
  --jq '{id, name, enforcement, target, conditions, rules: [.rules[].type], bypass_actors}'

cat <<EOF

Configured successfully.

Default branch: $DEFAULT_BRANCH
Ruleset:        $RULESET_NAME (ID $RULESET_ID)
Required check: $REQUIRED_CHECK

Enforced:
  - changes must arrive through a pull request
  - zero approving reviews required (single-developer workflow)
  - review conversations must be resolved
  - only squash merge is allowed by this ruleset
  - '$REQUIRED_CHECK' must pass
  - the PR must be tested against the latest default branch
  - linear history is required
  - branch deletion is blocked
  - force pushes are blocked
  - no bypass actors are configured
EOF
