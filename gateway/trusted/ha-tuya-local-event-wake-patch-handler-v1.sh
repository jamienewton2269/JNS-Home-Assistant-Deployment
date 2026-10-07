#!/usr/bin/env bash
# JNS Trusted Gateway: bounded Tuya Local commissioning connection test for
# sleepy/event-wake Wi-Fi sensors on HA-General.
#
# Scope: patch ONLY custom_components/tuya_local/config_flow.py so config-flow
# connection probes cannot hang for minutes. Runtime Tuya Local behaviour is
# otherwise untouched.
set -Eeuo pipefail

JOB_JSON="${1:?job json required}"
NODEB_HOST="nodeb"
NODEB_IP="10.10.10.235"
VMID="905"
HA_ROOT="/mnt/data/supervisor/homeassistant"
TARGET="$HA_ROOT/custom_components/tuya_local/config_flow.py"
BACKUP_ROOT="$HA_ROOT/.jns-backups"
PATCHED_CALL='await asyncio.wait_for(device.async_refresh(), timeout=3.0)'
ORIGINAL_CALL='await device.async_refresh()'

ssh_as_runner() {
  /usr/sbin/runuser -u github-runner -- /usr/bin/ssh \
    -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
    -o HostName="$NODEB_IP" "$NODEB_HOST" "$@"
}

python3 - "$JOB_JSON" <<'PY' > /tmp/jns-tuya-wake-job.env
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
if d.get("job_type")!="ha_tuya_local_event_wake_patch":
    raise SystemExit("wrong job_type")
if d.get("target") not in (None,"ha-general"):
    raise SystemExit("target must be ha-general")
if d.get("patch") not in (None,"bounded-config-flow-v1"):
    raise SystemExit("unsupported patch")
print("JOB_ID="+repr(str(d.get("job_id",""))))
PY
source /tmp/jns-tuya-wake-job.env
rm -f /tmp/jns-tuya-wake-job.env

ssh_as_runner \
  "qm status $VMID | grep -q 'status: running'"

STAMP="$(date +%Y%m%dT%H%M%S)"
BACKUP="$BACKUP_ROOT/tuya-local-event-wake-$STAMP"

# Inspect and back up before any mutation. The patch is deliberately
# preconditioned on exactly two stock refresh calls so an upstream Tuya Local
# change cannot be silently patched in the wrong place.
PRECHECK="$(ssh_as_runner \
  "qm guest exec $VMID -- /bin/bash -lc 'test -f \"$TARGET\"; printf \"original=%s patched=%s\\n\" \"\$(grep -Fc \"$ORIGINAL_CALL\" \"$TARGET\" || true)\" \"\$(grep -Fc \"$PATCHED_CALL\" \"$TARGET\" || true)\"'" 2>&1)"
printf '%s\n' "$PRECHECK"

if printf '%s\n' "$PRECHECK" | grep -q 'original=0 patched=2'; then
  echo "Patch already present; no file change required"
else
  printf '%s\n' "$PRECHECK" | grep -q 'original=2 patched=0' || {
    echo "Refusing patch: Tuya Local config_flow.py does not match expected precondition" >&2
    exit 43
  }

  ssh_as_runner \
    "qm guest exec $VMID -- /bin/bash -lc 'mkdir -p \"$BACKUP\"; cp -a \"$TARGET\" \"$BACKUP/config_flow.py\"; sed -i \"s|$ORIGINAL_CALL|$PATCHED_CALL|g\" \"$TARGET\"; test \"\$(grep -Fc \"$PATCHED_CALL\" \"$TARGET\")\" -eq 2'" >/dev/null
fi

set +e
CHECK_OUT="$(ssh_as_runner \
  "qm guest exec $VMID -- /bin/bash -lc 'ha core check'" 2>&1)"
CHECK_RC=$?
set -e
printf '%s\n' "$CHECK_OUT"

if [ "$CHECK_RC" -ne 0 ]; then
  echo "HA config validation failed; restoring Tuya Local backup"
  if [ -f /dev/null ]; then :; fi
  ssh_as_runner \
    "qm guest exec $VMID -- /bin/bash -lc 'if [ -f \"$BACKUP/config_flow.py\" ]; then cp -af \"$BACKUP/config_flow.py\" \"$TARGET\"; fi'" >/dev/null
  exit 42
fi

ssh_as_runner \
  "qm guest exec $VMID -- /bin/bash -lc 'ha core restart'" >/dev/null

healthy=0
for _ in $(seq 1 45); do
  if ssh_as_runner \
    "qm guest exec $VMID -- /bin/bash -lc 'ha core info'" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done

if [ "$healthy" -ne 1 ]; then
  echo "HA Core did not recover after patch; restoring backup" >&2
  ssh_as_runner \
    "qm guest exec $VMID -- /bin/bash -lc 'if [ -f \"$BACKUP/config_flow.py\" ]; then cp -af \"$BACKUP/config_flow.py\" \"$TARGET\"; ha core restart; fi'" >/dev/null
  exit 44
fi

ssh_as_runner \
  "qm guest exec $VMID -- /bin/bash -lc 'ha core info'"
ssh_as_runner \
  "qm guest exec $VMID -- /bin/bash -lc 'grep -nF \"$PATCHED_CALL\" \"$TARGET\"; ha core logs | tail -n 120 | grep -i -E \"tuya_local|tuya local\" || true'"

echo "HA_TUYA_LOCAL_EVENT_WAKE_PATCH_OK"
echo "job_id=$JOB_ID"
echo "target=ha-general"
echo "vmid=$VMID"
echo "file=$TARGET"
echo "backup=$BACKUP"
