#!/usr/bin/env bash
# JNS Trusted Gateway: narrowly scoped HA-General package deployment handler.
# Transaction succeeds only when the command inside the HA VM succeeds,
# deployed bytes match, HA config validates, Core restarts, and requested checks pass.
set -Eeuo pipefail

JOB_JSON="${1:?job json required}"
NODEB_HOST="nodeb"
NODEB_IP="10.10.10.235"
VMID="905"
HA_IP="10.10.10.223"
PKG_DIR="/mnt/data/supervisor/homeassistant/packages"

ssh_as_runner() {
  /usr/sbin/runuser -u github-runner -- /usr/bin/ssh     -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new     -o HostName="$NODEB_IP" "$NODEB_HOST" "$@"
}

guest_exec() {
  local shell_cmd="$1"
  local raw rc pid status exited
  set +e
  raw="$(ssh_as_runner "qm guest exec $VMID -- /bin/bash -lc $(printf '%q' "$shell_cmd")" 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    printf '%s\n' "$raw" >&2
    return "$rc"
  fi

  pid="$(printf '%s\n' "$raw" | python3 -c '
import json,sys
raw=sys.stdin.read()
start=raw.find("{")
if start < 0:
    raise SystemExit(0)
try:
    d=json.loads(raw[start:])
except Exception:
    raise SystemExit(0)
p=d.get("pid")
if p is not None:
    print(int(p))
' || true)"

  if [ -n "$pid" ]; then
    raw=""
    for _ in $(seq 1 180); do
      set +e
      status="$(ssh_as_runner "qm guest exec-status $VMID $pid" 2>&1)"
      rc=$?
      set -e
      if [ "$rc" -ne 0 ]; then
        printf '%s\n' "$status" >&2
        return "$rc"
      fi
      exited="$(printf '%s\n' "$status" | python3 -c '
import json,sys
raw=sys.stdin.read()
start=raw.find("{")
if start < 0:
    print(0); raise SystemExit
try:
    d=json.loads(raw[start:])
except Exception:
    print(0); raise SystemExit
print(1 if d.get("exited") else 0)
')"
      if [ "$exited" = "1" ]; then
        raw="$status"
        break
      fi
      sleep 1
    done
    [ -n "$raw" ] || {
      echo "guest command did not finish within 180 seconds pid=$pid" >&2
      return 124
    }
  fi

  printf '%s\n' "$raw" | python3 -c '
import json,sys
raw=sys.stdin.read()
start=raw.find("{")
if start < 0:
    sys.stderr.write(raw)
    raise SystemExit(125)
try:
    d=json.loads(raw[start:])
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

python3 - "$JOB_JSON" <<'PY' > /tmp/jns-ha-package-job.env
import base64, hashlib, json, re, shlex, sys
p=sys.argv[1]
d=json.load(open(p,encoding="utf-8"))
if d.get("job_type")!="ha_package_install":
    raise SystemExit("wrong job_type")
if d.get("target") not in (None,"ha-general"):
    raise SystemExit("target must be ha-general")
name=d.get("package_name","")
if not re.fullmatch(r"[a-z0-9][a-z0-9_\-]{0,63}\.yaml", name):
    raise SystemExit("invalid package_name")
content=d.get("content_b64","")
raw=base64.b64decode(content, validate=True)
if not raw or len(raw)>131072:
    raise SystemExit("package payload size invalid")
verify=d.get("verify_entities",[])
if not isinstance(verify,list) or len(verify)>32:
    raise SystemExit("verify_entities invalid")
for v in verify:
    if not isinstance(v,str) or not re.fullmatch(r"[a-z0-9_\.\-]{1,128}",v):
        raise SystemExit("invalid verify entity")
print("PACKAGE_NAME="+shlex.quote(name))
print("CONTENT_B64="+shlex.quote(content))
print("CONTENT_SHA256="+shlex.quote(hashlib.sha256(raw).hexdigest()))
print("VERIFY_ENTITIES="+shlex.quote("\n".join(verify)))
PY
source /tmp/jns-ha-package-job.env
rm -f /tmp/jns-ha-package-job.env

TARGET="$PKG_DIR/$PACKAGE_NAME"
STAMP="$(date +%Y%m%dT%H%M%S)"
BACKUP="$TARGET.jns-backup-$STAMP"

ssh_as_runner "qm status $VMID | grep -q 'status: running'"

rollback() {
  echo "ROLLBACK: restoring previous package" >&2
  guest_exec "if [ -f '$BACKUP' ]; then mv -f '$BACKUP' '$TARGET'; else rm -f '$TARGET'; fi" >/dev/null || true
}
trap 'rc=$?; if [ "$rc" -ne 0 ]; then rollback; fi; exit "$rc"' EXIT

guest_exec "mkdir -p '$PKG_DIR'; if [ -f '$TARGET' ]; then cp -a '$TARGET' '$BACKUP'; fi" >/dev/null
guest_exec "printf '%s' '$CONTENT_B64' | base64 -d > '$TARGET.jns-new' && test -s '$TARGET.jns-new' && mv '$TARGET.jns-new' '$TARGET'" >/dev/null

ACTUAL_SHA="$(guest_exec "sha256sum '$TARGET' | cut -d ' ' -f1" | tr -d '\r\n')"
[ "$ACTUAL_SHA" = "$CONTENT_SHA256" ] || {
  echo "Package integrity mismatch expected=$CONTENT_SHA256 actual=$ACTUAL_SHA" >&2
  exit 43
}

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

if [ -n "${VERIFY_ENTITIES:-}" ]; then
  while IFS= read -r item; do
    [ -z "$item" ] && continue
    guest_exec "grep -Fq -- '$item' /mnt/data/supervisor/homeassistant/.storage/core.entity_registry"
    echo "verified=$item"
  done <<< "$VERIFY_ENTITIES"
fi

trap - EXIT
echo "HA_PACKAGE_INSTALL_OK"
echo "target=ha-general"
echo "nodeb_host=$NODEB_HOST"
echo "nodeb_ip=$NODEB_IP"
echo "vmid=$VMID"
echo "ha_ip=$HA_IP"
echo "package=$TARGET"
echo "sha256=$CONTENT_SHA256"
echo "backup=$BACKUP"
