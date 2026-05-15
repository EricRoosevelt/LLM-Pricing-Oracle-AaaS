#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

status=0
secret_pattern='sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{80,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'

scan_publishable_files() {
  if command -v rg >/dev/null 2>&1; then
    xargs -0 -r rg -n -I -l -e "$secret_pattern" -- 2>/dev/null
  else
    xargs -0 -r grep -E -I -l -- "$secret_pattern" 2>/dev/null
  fi
}

tracked_env_hits="$(git ls-files '.env' '.env.*' 2>/dev/null | grep -v -E '(^|/)\.env\.example$' || true)"
if [[ -n "$tracked_env_hits" ]]; then
  echo "Refusing to publish tracked environment files:"
  echo "$tracked_env_hits"
  status=1
fi

publish_hits="$(
  git ls-files --cached --others --exclude-standard -z \
    | scan_publishable_files \
    || true
)"
if [[ -n "$publish_hits" ]]; then
  echo "Potential high-confidence secrets in publishable files:"
  echo "$publish_hits" | sort -u
  status=1
fi

history_hits="$(git grep -I -l -E "$secret_pattern" $(git rev-list --all) -- 2>/dev/null || true)"
if [[ -n "$history_hits" ]]; then
  echo "Potential high-confidence secrets in git history:"
  echo "$history_hits" | sort -u
  status=1
fi

if [[ "$status" -ne 0 ]]; then
  echo "Secret scan failed. Remove or rotate the value before pushing."
  exit "$status"
fi

echo "Secret scan passed."
