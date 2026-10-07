#!/usr/bin/env bash
set -Eeuo pipefail

REPO="/home/github-runner/actions-runner/_work/JNS-Home-Assistant-Deployment/JNS-Home-Assistant-Deployment"
RUNNER="github-runner"
SSH_DIR="/home/github-runner/.ssh"
KEY="$SSH_DIR/jns_github_deploy"
REMOTE="git@github.com:jamienewton2269/JNS-Home-Assistant-Deployment.git"
JOB="20261007T152000Z-ha-general-lux-dusk-04"
LOG="/var/log/jns-github-bridge-repair.log"

exec > >(tee -a "$LOG") 2>&1
log(){ printf '[%s] %s\n' "$(date '+%F %T%z')" "$*"; }
fail(){ log "ERROR: $1"; exit "${2:-1}"; }
trap 'rc=$?; log "FAILED line=$LINENO exit=$rc cmd=$BASH_COMMAND"; exit $rc' ERR

[ "$(id -u)" -eq 0 ] || fail "Run as root on Node C" 77
id "$RUNNER" >/dev/null 2>&1 || fail "Missing user $RUNNER" 78
[ -d "$REPO/.git" ] || fail "Repository missing: $REPO" 79
cd "$REPO"

log "1/8 repair ownership"
chown -R "$RUNNER:$RUNNER" "$REPO/.git" "$REPO/gateway"
sudo -u "$RUNNER" test -w "$REPO/.git/objects" || fail "Runner cannot write .git/objects" 80

log "2/8 prepare SSH deploy key"
install -d -o "$RUNNER" -g "$RUNNER" -m 0700 "$SSH_DIR"
if [ ! -f "$KEY" ]; then
  sudo -u "$RUNNER" ssh-keygen -q -t ed25519 -N "" -f "$KEY" -C "jns-nodec-gateway"
fi
chown "$RUNNER:$RUNNER" "$KEY" "$KEY.pub"
chmod 600 "$KEY"
chmod 644 "$KEY.pub"

cat >"$SSH_DIR/config" <<EOF
Host github.com
    HostName github.com
    User git
    IdentityFile $KEY
    IdentitiesOnly yes
EOF
chown "$RUNNER:$RUNNER" "$SSH_DIR/config"
chmod 600 "$SSH_DIR/config"

log "3/8 test GitHub SSH authentication"
if AUTH="$(sudo -u "$RUNNER" ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1)"; then
  AUTH_RC=0
else
  AUTH_RC=$?
fi
printf '%s\n' "$AUTH"
if ! printf '%s\n' "$AUTH" | grep -qi 'successfully authenticated'; then
  echo
  log "ACTION REQUIRED: add this key as a WRITE deploy key for JNS-Home-Assistant-Deployment:"
  cat "$KEY.pub"
  echo
  log "Then rerun this same script."
  exit 10
fi

log "GitHub SSH authentication accepted (ssh_rc=$AUTH_RC)"
log "4/8 switch origin to SSH"
sudo -u "$RUNNER" git remote set-url origin "$REMOTE"
[ "$(sudo -u "$RUNNER" git remote get-url origin)" = "$REMOTE" ] || fail "Origin switch failed" 81

log "5/8 fetch"
sudo -u "$RUNNER" git fetch origin

log "6/8 recover stranded result"
RESULT="gateway/results/${JOB}.txt"
STATUS="gateway/status/${JOB}.json"
if [ -f "$RESULT" ] && [ -f "$STATUS" ]; then
  sudo -u "$RUNNER" git add gateway/index.tsv "$RESULT" "$STATUS"
  if ! sudo -u "$RUNNER" git diff --cached --quiet; then
    sudo -u "$RUNNER" git commit -m "gateway: record stranded Node C job result"
  fi
fi

log "7/8 push and resync"
sudo -u "$RUNNER" git push origin main
sudo -u "$RUNNER" git pull --ff-only origin main

log "8/8 final checks"
DIRTY="$(sudo -u "$RUNNER" git status --porcelain)"
[ -z "$DIRTY" ] || { printf '%s\n' "$DIRTY"; fail "Repository still dirty" 82; }
pgrep -u "$RUNNER" -f 'Runner.Listener' >/dev/null || fail "Runner.Listener not running" 83
sudo -u "$RUNNER" git status --short --branch
log "JNS GITHUB BRIDGE REPAIR COMPLETE"
