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
