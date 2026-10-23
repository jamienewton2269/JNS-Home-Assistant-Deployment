#!/usr/bin/env bash
# JNS HA Steward local knowledge refresh. Only manages its own private checkout,
# three cache files and compact SQLite facts; never restarts HA or Steward.
set -Eeuo pipefail
export GIT_TERMINAL_PROMPT=0
umask 077

REPO='jamienewton2269/JNS-Steward-Diagnostics'
BASE='/var/lib/jns-steward-knowledge'
SOURCE="$BASE/repo"
DATA='/opt/natural-automation/data'

[[ "$(id -u)" == 0 ]] || { echo "BLOCKED: root wrapper required"; exit 77; }
[[ -d "$DATA" && -d /opt/natural-automation/steward ]] || {
  echo "BLOCKED: active Steward data layout not found; no modifications"; exit 66;
}
command -v git >/dev/null && command -v python3 >/dev/null || {
  echo "BLOCKED: git/python3 unavailable"; exit 69;
}
install -d -o root -g root -m 0700 "$BASE"
# Scoped, read-only GitHub deploy key for THIS private diagnostics repository.
# Private material remains on Node B. The public key must be added to GitHub
# Settings > Deploy keys with ALLOW WRITE ACCESS UNCHECKED.
CREDS="$BASE/credentials"
KEY="$CREDS/diagnostics_readonly"
install -d -o root -g root -m 0700 "$CREDS"
if [[ ! -s "$KEY" || ! -s "$KEY.pub" ]]; then
  [[ ! -e "$KEY" && ! -e "$KEY.pub" ]] || {
    echo "BLOCKED: partial diagnostics key files, manual review required"; exit 65;
  }
  ssh-keygen -q -t ed25519 -N '' -C 'jns-steward-diagnostics-readonly' -f "$KEY"
fi
chmod 0600 "$KEY"
chmod 0644 "$KEY.pub"
# GitHub's published Ed25519 host key (fingerprint verified against GitHub Docs).
printf '%s\n' 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl' > "$CREDS/known_hosts"
chmod 0600 "$CREDS/known_hosts"
fingerprint="$(ssh-keygen -lf "$CREDS/known_hosts" | awk '{print $2}')"
[[ "$fingerprint" = 'SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU' ]] || {
  echo "BLOCKED: github.com host key fingerprint mismatch"; exit 65;
}
export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o UserKnownHostsFile=$CREDS/known_hosts -o StrictHostKeyChecking=yes"

if [[ ! -d "$SOURCE/.git" ]]; then
  if [[ -e "$SOURCE" ]]; then
    echo "BLOCKED: target checkout path unexpectedly exists"; exit 73
  fi
  scratch="$(mktemp -d "$BASE/clone.XXXXXX")"
  trap 'rm -rf "$scratch"' EXIT
  cloned=0
  if timeout 45 git -c core.askPass=/bin/false clone --depth 1 \
     "git@github.com:$REPO.git" "$scratch/repo" >/dev/null 2>&1; then
    cloned=1
  elif timeout 45 git -c core.askPass=/bin/false clone --depth 1 \
     "https://github.com/$REPO.git" "$scratch/repo" >/dev/null 2>&1; then
    cloned=1
  fi
  if [[ "$cloned" -ne 1 ]]; then
    echo "BLOCKED: private diagnostics repo unavailable using existing credentials; no new credentials requested"
    exit 78
  fi
  mv "$scratch/repo" "$SOURCE"
  trap - EXIT
  rmdir "$scratch" || true
fi

remote="$(git -C "$SOURCE" remote get-url origin)"
case "$remote" in
  "git@github.com:$REPO.git"|"https://github.com/$REPO.git") ;;
  *) echo "BLOCKED: unexpected private repository origin"; exit 65 ;;
esac

# This checkout is exclusively managed by this job, not a working source tree.
if ! timeout 60 git -C "$SOURCE" fetch --quiet --depth=1 origin main; then
  echo "BLOCKED: source refresh unavailable; retained previous Steward cache"
  exit 75
fi
git -C "$SOURCE" reset --hard --quiet FETCH_HEAD

# Do not import partial or failed inventories; builder handles audit freshness.
python3 "$SOURCE/knowledge/build_seed.py" --repo-root "$SOURCE" \
  --output "$SOURCE/knowledge/generated" >/dev/null
python3 "$SOURCE/knowledge/sync_onsite.py" \
  --repo-checkout "$SOURCE" --data-dir "$DATA" --dry-run
python3 "$SOURCE/knowledge/sync_onsite.py" \
  --repo-checkout "$SOURCE" --data-dir "$DATA"
echo "JNS_STEWARD_KNOWLEDGE_REFRESH_OK"
