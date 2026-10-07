#!/usr/bin/env bash
# JNS trusted gateway end-to-end health test. Read-only.
set -Eeuo pipefail

JOB_JSON="${1:?job json required}"
NODEB_HOST="nodeb"
NODEB_IP="10.10.10.235"
VMID="905"

python3 - "$JOB_JSON" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
if d.get("job_type")!="gateway_bridge_selftest":
    raise SystemExit("wrong job_type")
if d.get("target") not in (None,"ha-general"):
    raise SystemExit("target must be ha-general")
PY

ssh_runner() {
  /usr/sbin/runuser -u github-runner -- /usr/bin/ssh     -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new     -o HostName="$NODEB_IP" "$NODEB_HOST" "$@"
}

echo "stage=nodec-runner status=ok"
ssh_runner "true"
echo "stage=nodec-to-nodeb-ssh status=ok"

ssh_runner "qm status $VMID | grep -q 'status: running'"
echo "stage=nodeb-to-vm905 status=ok"

JSON="$(ssh_runner "qm guest exec $VMID -- /bin/bash -lc 'ha core info'")"
printf '%s\n' "$JSON" | python3 -c '
import json,sys
d=json.load(sys.stdin)
if not d.get("exited") or int(d.get("exitcode",125)) != 0:
    print(d, file=sys.stderr)
    raise SystemExit(1)
out=d.get("out-data") or ""
if "version:" not in out:
    print(out, file=sys.stderr)
    raise SystemExit(1)
print("stage=vm905-ha-core status=ok")
'
echo "GATEWAY_BRIDGE_SELFTEST_OK"
