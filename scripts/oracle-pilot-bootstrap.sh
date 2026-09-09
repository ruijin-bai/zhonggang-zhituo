#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s <ubuntu@host> <ssh-private-key> <pilot-admin-email> [git-sha]\n' "$0" >&2
  exit 2
}

[[ $# -ge 3 && $# -le 4 ]] || usage
ssh_target="$1"
ssh_key="$2"
pilot_email="$3"
git_sha="${4:-origin/main}"
repository="ruijin-bai/zhonggang-zhituo"

command -v gh >/dev/null 2>&1 || { printf 'FAIL: gh is required\n' >&2; exit 1; }
command -v ssh >/dev/null 2>&1 || { printf 'FAIL: ssh is required\n' >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { printf 'FAIL: GitHub CLI authentication is required\n' >&2; exit 1; }
[[ -f "$ssh_key" ]] || { printf 'FAIL: SSH key not found: %s\n' "$ssh_key" >&2; exit 1; }
[[ "$pilot_email" == *@* && "$pilot_email" != *@zhituo.local ]] || {
  printf 'FAIL: a non-demo Pilot administrator email is required\n' >&2
  exit 1
}

ssh_args=(-i "$ssh_key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
temp_pub="$(mktemp)"
trap 'rm -f "$temp_pub"' EXIT

printf '==> Waiting for cloud-init\n'
ssh "${ssh_args[@]}" "$ssh_target" 'cloud-init status --wait'
ssh "${ssh_args[@]}" "$ssh_target" 'sudo cat /home/zhituo/.ssh/id_ed25519.pub' > "$temp_pub"

key_title="zhituo-oracle-pilot"
if ! gh repo deploy-key list --repo "$repository" | grep -Fq "$key_title"; then
  printf '==> Registering the VM read-only GitHub deploy key\n'
  gh repo deploy-key add "$temp_pub" --repo "$repository" --title "$key_title"
fi

printf '==> Cloning the governed mainline and deploying %s\n' "$git_sha"
ssh "${ssh_args[@]}" "$ssh_target" bash -s -- "$git_sha" "$pilot_email" <<'REMOTE'
set -euo pipefail
git_sha="$1"
pilot_email="$2"
sudo install -d -o zhituo -g zhituo -m 0750 /opt/zhituo
if [[ ! -d /opt/zhituo/current/.git ]]; then
  sudo -Hu zhituo env GIT_SSH_COMMAND='ssh -o StrictHostKeyChecking=accept-new' \
    git clone git@github.com:ruijin-bai/zhonggang-zhituo.git /opt/zhituo/current
fi
sudo -Hu zhituo git -C /opt/zhituo/current fetch --prune origin main
target_sha="$(sudo -Hu zhituo git -C /opt/zhituo/current rev-parse "${git_sha}^{commit}")"
main_sha="$(sudo -Hu zhituo git -C /opt/zhituo/current rev-parse 'origin/main^{commit}')"
[[ "$target_sha" == "$main_sha" ]] || {
  printf 'FAIL: bootstrap SHA must equal the current governed origin/main\n' >&2
  exit 1
}
sudo -Hu zhituo git -C /opt/zhituo/current switch main
sudo -Hu zhituo git -C /opt/zhituo/current merge --ff-only origin/main
sudo -u zhituo env PILOT_ADMIN_EMAIL="$pilot_email" \
  bash /opt/zhituo/current/scripts/pilot-up.sh
sudo systemctl daemon-reload
sudo systemctl enable zhituo-pilot.service
sudo systemctl restart zhituo-pilot.service
sudo -u zhituo env ZHITUO_PILOT_ENV_FILE=/opt/zhituo/current/deploy/pilot/.env \
  bash /opt/zhituo/current/scripts/pilot-health.sh
REMOTE

printf 'PASS  Oracle host bootstrapped and reboot service enabled\n'
