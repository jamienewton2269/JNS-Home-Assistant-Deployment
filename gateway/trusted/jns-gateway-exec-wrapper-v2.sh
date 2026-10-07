#!/usr/bin/env bash
# Root-owned wrapper for /usr/local/sbin/jns-gateway-exec.
# Adds narrowly scoped HA package and JNS Network Identity install job types.
set -Eeuo pipefail

JOB="${1:?immutable queue job JSON required}"
REAL="$(readlink -f -- "$JOB")"
case "$REAL" in
  */gateway/queue/*.json) ;;
  *) echo "Rejected: job must be an immutable gateway/queue JSON file" >&2; exit 64 ;;
esac
[ -f "$REAL" ] || { echo "Rejected: job file missing" >&2; exit 66; }

JOB_TYPE="$(python3 - "$REAL" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
v=d.get("job_type")
if not isinstance(v,str): raise SystemExit(65)
print(v)
PY
)"

case "$JOB_TYPE" in
  ha_package_install)
    exec /usr/local/libexec/jns-gateway-ha-package-install "$REAL"
    ;;
  ha_network_identity_install)
    exec /usr/local/libexec/jns-gateway-ha-network-identity-install "$REAL"
    ;;
  *)
    exec /usr/local/sbin/jns-gateway-exec.base "$REAL"
    ;;
esac
