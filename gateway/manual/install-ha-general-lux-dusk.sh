#!/usr/bin/env bash
set -Eeuo pipefail

REPO="/home/github-runner/actions-runner/_work/JNS-Home-Assistant-Deployment/JNS-Home-Assistant-Deployment"
EXECUTOR="/usr/local/sbin/jns-gateway-exec"
JOB="$REPO/gateway/queue/20261008T173800Z-ha-general-lux-dusk-07.json"
LOGDIR="$REPO/gateway/manual-results"
STAMP="$(date +%Y%m%dT%H%M%S)"
LOG="$LOGDIR/ha-general-lux-dusk-manual-$STAMP.txt"

cd "$REPO"
mkdir -p "$LOGDIR"

echo "=== JNS HA-GENERAL LUX/DUSK MANUAL TRUSTED INSTALL ==="
echo "repo=$REPO"
echo "job=$JOB"
echo "executor=$EXECUTOR"

if [[ ! -x "$EXECUTOR" ]]; then
  echo "ERROR: trusted executor missing: $EXECUTOR" >&2
  exit 78
fi

if [[ ! -f "$JOB" ]]; then
  echo "ERROR: deployment job missing: $JOB" >&2
  exit 66
fi

echo "--- refreshing repository ---"
git pull --ff-only origin main

echo "--- validating target/job metadata ---"
python3 - "$JOB" <<'PY'
import json,sys
p=sys.argv[1]
d=json.load(open(p,encoding="utf-8"))
expected={
    "job_type":"ha_package_install",
    "target":"ha-general",
    "proxmox_host":"nodeb",
    "vmid":905,
    "ha_address":"10.10.10.223",
    "package_name":"house_lighting_lux_dusk.yaml",
}
bad=[]
for k,v in expected.items():
    if d.get(k)!=v:
        bad.append(f"{k}: expected {v!r}, got {d.get(k)!r}")
if bad:
    raise SystemExit("Refusing install; unexpected job metadata:\n" + "\n".join(bad))
print("job metadata OK")
PY

echo "--- executing through trusted root-owned gateway executor ---"
set +e
sudo "$EXECUTOR" "$JOB" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
set -e

echo
echo "manual_result_log=$LOG"
echo "exit_code=$rc"

if [[ "$rc" -eq 0 ]]; then
  echo "INSTALL_COMPLETE"
else
  echo "INSTALL_FAILED_OR_ROLLED_BACK"
fi

exit "$rc"
