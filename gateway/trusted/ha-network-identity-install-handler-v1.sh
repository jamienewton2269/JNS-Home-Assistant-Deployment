#!/usr/bin/env bash
# JNS Trusted Gateway: deploy JNS Network Identity to HA-General.
set -Eeuo pipefail

JOB_JSON="${1:?job json required}"
NODEB_HOST="nodeb"
NODEB_IP="10.10.10.235"
VMID="905"
HA_ROOT="/mnt/data/supervisor/homeassistant"
TARGET_DIR="$HA_ROOT/custom_components/jns_network_identity"
ENABLE_FILE="$HA_ROOT/packages/jns_network_identity_enable.yaml"

ssh_as_runner() {
  /usr/sbin/runuser -u github-runner -- /usr/bin/ssh \
    -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
    -o HostName="$NODEB_IP" "$NODEB_HOST" "$@"
}

python3 - "$JOB_JSON" <<'PY' > /tmp/jns-network-identity-job.env
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
if d.get("job_type")!="ha_network_identity_install":
    raise SystemExit("wrong job_type")
if d.get("target") not in (None,"ha-general"):
    raise SystemExit("target must be ha-general")
print("JOB_ID="+repr(str(d.get("job_id",""))))
PY
source /tmp/jns-network-identity-job.env
rm -f /tmp/jns-network-identity-job.env

REAL_JOB="$(readlink -f "$JOB_JSON")"
REPO_ROOT="$(readlink -f "$(dirname "$REAL_JOB")/../..")"
SRC="$REPO_ROOT/custom_components/jns_network_identity"

for f in __init__.py manifest.json services.yaml card.js; do
  [ -f "$SRC/$f" ] || { echo "Missing source file: $SRC/$f" >&2; exit 66; }
done

ssh_as_runner   "qm status $VMID | grep -q 'status: running'"

STAMP="$(date +%Y%m%dT%H%M%S)"
BACKUP="$HA_ROOT/.jns-backups/network-identity-$STAMP"

ssh_as_runner   "qm guest exec $VMID -- /bin/bash -lc 'mkdir -p "$HA_ROOT/.jns-backups" "$TARGET_DIR" "$HA_ROOT/packages"; if [ -d "$TARGET_DIR" ]; then cp -a "$TARGET_DIR" "$BACKUP"; fi' >/dev/null"

for f in __init__.py manifest.json services.yaml card.js; do
  B64="$(base64 -w0 "$SRC/$f")"
  ssh_as_runner \
    "qm guest exec $VMID -- /bin/bash -lc 'base64 -d > \"$TARGET_DIR/$f.jns-new\"' --input-data '$B64'" >/dev/null
  ssh_as_runner \
    "qm guest exec $VMID -- /bin/bash -lc 'mv \"$TARGET_DIR/$f.jns-new\" \"$TARGET_DIR/$f\"'" >/dev/null
done

ssh_as_runner   "qm guest exec $VMID -- /bin/bash -lc 'printf "%s\n" "jns_network_identity:" > "$ENABLE_FILE"'" >/dev/null

set +e
CHECK_OUT="$(ssh_as_runner   "qm guest exec $VMID -- /bin/bash -lc 'ha core check'" 2>&1)"
CHECK_RC=$?
set -e
printf '%s\n' "$CHECK_OUT"

if [ "$CHECK_RC" -ne 0 ]; then
  echo "HA config validation failed; restoring previous component"
  ssh_as_runner     "qm guest exec $VMID -- /bin/bash -lc 'rm -rf "$TARGET_DIR"; if [ -d "$BACKUP" ]; then cp -a "$BACKUP" "$TARGET_DIR"; fi; rm -f "$ENABLE_FILE"'" >/dev/null
  exit 42
fi

ssh_as_runner   "qm guest exec $VMID -- /bin/bash -lc 'ha core restart'" >/dev/null

for _ in $(seq 1 45); do
  if ssh_as_runner     "qm guest exec $VMID -- /bin/bash -lc 'ha core info'" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

ssh_as_runner   "qm guest exec $VMID -- /bin/bash -lc 'ha core info'"
ssh_as_runner "qm guest exec $VMID -- /bin/bash -lc \"ha core logs | tail -n 120 | grep -i -E 'jns_network_identity|network identity' || true\""

echo "HA_NETWORK_IDENTITY_INSTALL_OK"
echo "job_id=$JOB_ID"
echo "target=ha-general"
echo "vmid=$VMID"
echo "component=$TARGET_DIR"
echo "backup=$BACKUP"
