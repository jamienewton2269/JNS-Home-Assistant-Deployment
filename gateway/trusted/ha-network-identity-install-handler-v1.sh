#!/usr/bin/env bash
# JNS Trusted Gateway: deploy JNS Network Identity to HA-General.
# Transaction succeeds only when the command inside the HA VM succeeds,
# deployed files match source hashes, HA config validates, and Core restarts cleanly.
set -Eeuo pipefail

JOB_JSON="${1:?job json required}"
NODEB_HOST="nodeb"
NODEB_IP="10.10.10.235"
VMID="905"
HA_ROOT="/mnt/data/supervisor/homeassistant"
TARGET_DIR="$HA_ROOT/custom_components/jns_network_identity"
ENABLE_FILE="$HA_ROOT/packages/jns_network_identity_enable.yaml"

ssh_as_runner() {
  /usr/sbin/runuser -u github-runner -- /usr/bin/ssh     -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new     -o HostName="$NODEB_IP" "$NODEB_HOST" "$@"
}

# Proxmox qm guest exec returns JSON and may itself exit 0 even when the guest
# command failed. Always parse the guest exitcode and surface guest output.
guest_exec() {
  local shell_cmd="$1"
  local json rc
  set +e
  json="$(ssh_as_runner "qm guest exec $VMID -- /bin/bash -lc $(printf '%q' "$shell_cmd")" 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    printf '%s\n' "$json" >&2
    return "$rc"
  fi

  printf '%s\n' "$json" | python3 -c '
import json,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
except Exception:
    sys.stderr.write(raw)
    raise SystemExit(125)
out=d.get("out-data") or ""
err=d.get("err-data") or ""
if out: sys.stdout.write(out)
if err: sys.stderr.write(err)
if not d.get("exited"):
    raise SystemExit(124)
rc=int(d.get("exitcode",125))
raise SystemExit(rc if 0 <= rc <= 125 else 125)
'
}

python3 - "$JOB_JSON" <<'PY' > /tmp/jns-network-identity-job.env
import json,shlex,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
if d.get("job_type")!="ha_network_identity_install":
    raise SystemExit("wrong job_type")
if d.get("target") not in (None,"ha-general"):
    raise SystemExit("target must be ha-general")
job=str(d.get("job_id",""))
if not job:
    raise SystemExit("job_id required")
print("JOB_ID="+shlex.quote(job))
PY
source /tmp/jns-network-identity-job.env
rm -f /tmp/jns-network-identity-job.env

REAL_JOB="$(readlink -f "$JOB_JSON")"
REPO_ROOT="$(readlink -f "$(dirname "$REAL_JOB")/../..")"
SRC="$REPO_ROOT/custom_components/jns_network_identity"

for f in __init__.py manifest.json services.yaml card.js; do
  [ -s "$SRC/$f" ] || { echo "Missing/empty source file: $SRC/$f" >&2; exit 66; }
done
python3 -m json.tool "$SRC/manifest.json" >/dev/null

ssh_as_runner "qm status $VMID | grep -q 'status: running'"

STAMP="$(date +%Y%m%dT%H%M%S)"
BACKUP="$HA_ROOT/.jns-backups/network-identity-$STAMP"

rollback() {
  echo "ROLLBACK: restoring previous JNS Network Identity deployment" >&2
  guest_exec "rm -rf '$TARGET_DIR'; if [ -d '$BACKUP' ]; then cp -a '$BACKUP' '$TARGET_DIR'; fi; rm -f '$ENABLE_FILE'" >/dev/null || true
}
trap 'rc=$?; if [ "$rc" -ne 0 ]; then rollback; fi; exit "$rc"' EXIT

guest_exec "mkdir -p '$HA_ROOT/.jns-backups' '$HA_ROOT/custom_components' '$HA_ROOT/packages'; if [ -d '$TARGET_DIR' ]; then cp -a '$TARGET_DIR' '$BACKUP'; fi; mkdir -p '$TARGET_DIR'" >/dev/null

for f in __init__.py manifest.json services.yaml card.js; do
  B64="$(base64 -w0 "$SRC/$f")"
  guest_exec "printf '%s' '$B64' | base64 -d > '$TARGET_DIR/$f.jns-new' && test -s '$TARGET_DIR/$f.jns-new' && mv '$TARGET_DIR/$f.jns-new' '$TARGET_DIR/$f'" >/dev/null
done

# A HA package value must be a mapping/list, not YAML null.
guest_exec "printf '%s\n' 'jns_network_identity: {}' > '$ENABLE_FILE'" >/dev/null

# Verify exact bytes made it through the bridge.
for f in __init__.py manifest.json services.yaml card.js; do
  EXPECTED="$(sha256sum "$SRC/$f" | awk '{print $1}')"
  ACTUAL="$(guest_exec "sha256sum '$TARGET_DIR/$f'" | cut -d' ' -f1 | tr -d '\r\n')"
  [ "$EXPECTED" = "$ACTUAL" ] || {
    echo "Integrity mismatch for $f expected=$EXPECTED actual=$ACTUAL" >&2
    exit 43
  }
done

# Validate the JSON manifest in the target VM before HA sees it.
guest_exec "python3 -m json.tool '$TARGET_DIR/manifest.json' >/dev/null"

# The guest command's exitcode is authoritative.
guest_exec "ha core check"

guest_exec "ha core restart" >/dev/null

healthy=0
for _ in $(seq 1 45); do
  if guest_exec "ha core info" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
[ "$healthy" -eq 1 ] || { echo "Home Assistant Core did not return healthy" >&2; exit 44; }

# Fail if this deployment produced current component/config loader errors.
LOGS="$(guest_exec "ha core logs | tail -n 160")"
printf '%s\n' "$LOGS" | grep -i -E 'jns_network_identity|network identity' || true
if printf '%s\n' "$LOGS" | grep -i -E 'ERROR .*jns_network_identity|Error parsing manifest.json.*jns_network_identity|Invalid package configuration.*jns_network_identity' >/dev/null; then
  echo "Post-deploy HA logs contain JNS Network Identity errors" >&2
  exit 45
fi

trap - EXIT
echo "HA_NETWORK_IDENTITY_INSTALL_OK"
echo "job_id=$JOB_ID"
echo "target=ha-general"
echo "vmid=$VMID"
echo "component=$TARGET_DIR"
echo "backup=$BACKUP"
