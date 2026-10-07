#!/usr/bin/env bash
# JNS Trusted Gateway: narrowly scoped HA-General package deployment handler.
# Intended to be installed root-owned and invoked ONLY by /usr/local/sbin/jns-gateway-exec
# for job_type=ha_package_install. It is not a general command runner.
set -Eeuo pipefail

JOB_JSON="${1:?job json required}"
NODEB_IP="10.10.10.235"
VMID="905"
HA_IP="10.10.10.223"
PKG_DIR="/mnt/data/supervisor/homeassistant/packages"

python3 - "$JOB_JSON" <<'PY' > /tmp/jns-ha-package-job.env
import base64, json, re, shlex, sys
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
print("VERIFY_ENTITIES="+shlex.quote("\n".join(verify)))
PY
source /tmp/jns-ha-package-job.env
rm -f /tmp/jns-ha-package-job.env

TARGET="$PKG_DIR/$PACKAGE_NAME"
STAMP="$(date +%Y%m%dT%H%M%S)"
BACKUP="$TARGET.jns-backup-$STAMP"

ssh -o BatchMode=yes -o ConnectTimeout=10 "root@$NODEB_IP" \
  "qm status $VMID | grep -q 'status: running'"

# Back up only the target package, never unrelated automations/packages.
ssh "root@$NODEB_IP" \
  "qm guest exec $VMID -- /bin/bash -lc 'mkdir -p $PKG_DIR; if [ -f "$TARGET" ]; then cp -a "$TARGET" "$BACKUP"; fi' >/dev/null"

# Write package content to a temporary file and atomically move into place.
printf '%s' "$CONTENT_B64" | base64 -d > "/tmp/$PACKAGE_NAME"
ssh "root@$NODEB_IP" \
  "qm guest exec $VMID -- /bin/bash -lc 'cat > "$TARGET.jns-new"' --input-data "$(cat "/tmp/$PACKAGE_NAME")" >/dev/null"
rm -f "/tmp/$PACKAGE_NAME"
ssh "root@$NODEB_IP" \
  "qm guest exec $VMID -- /bin/bash -lc 'mv "$TARGET.jns-new" "$TARGET"' >/dev/null"

set +e
CHECK_OUT="$(ssh "root@$NODEB_IP" "qm guest exec $VMID -- /bin/bash -lc 'ha core check'" 2>&1)"
CHECK_RC=$?
set -e
printf '%s\n' "$CHECK_OUT"
if [ "$CHECK_RC" -ne 0 ]; then
  echo "HA config validation failed; restoring package backup"
  ssh "root@$NODEB_IP" \
    "qm guest exec $VMID -- /bin/bash -lc 'if [ -f "$BACKUP" ]; then mv -f "$BACKUP" "$TARGET"; else rm -f "$TARGET"; fi'" >/dev/null
  exit 42
fi

# Packages can span helpers/scripts/automations; a Core restart is the reliable
# native application path after a successful full config check.
ssh "root@$NODEB_IP" \
  "qm guest exec $VMID -- /bin/bash -lc 'ha core restart'" >/dev/null

# Verify Core returns healthy.
for _ in $(seq 1 30); do
  if ssh "root@$NODEB_IP" "qm guest exec $VMID -- /bin/bash -lc 'ha core info'" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
ssh "root@$NODEB_IP" "qm guest exec $VMID -- /bin/bash -lc 'ha core info'"

# Verify requested entities/IDs are represented in HA's entity registry where applicable.
if [ -n "${VERIFY_ENTITIES:-}" ]; then
  while IFS= read -r item; do
    [ -z "$item" ] && continue
    ssh "root@$NODEB_IP" \
      "qm guest exec $VMID -- /bin/bash -lc 'grep -Fq -- "$item" /mnt/data/supervisor/homeassistant/.storage/core.entity_registry'"
    echo "verified=$item"
  done <<< "$VERIFY_ENTITIES"
fi

echo "HA_PACKAGE_INSTALL_OK"
echo "target=ha-general"
echo "nodeb_ip=$NODEB_IP"
echo "vmid=$VMID"
echo "ha_ip=$HA_IP"
echo "package=$TARGET"
echo "backup=$BACKUP"
