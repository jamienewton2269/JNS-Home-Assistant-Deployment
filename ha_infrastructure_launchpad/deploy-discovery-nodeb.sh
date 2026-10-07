#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/ha_infrastructure_launchpad/discovery_server.py"
NODE_B="nodeb"
TARGET_DIR="/opt/jns-infrastructure-discovery"
STATE_DIR="/var/lib/jns-infrastructure-discovery"

[[ -s "$SRC" ]] || { echo "Missing discovery server: $SRC" >&2; exit 2; }

SRC_B64="$(base64 -w0 "$SRC")"
SRC_SHA="$(sha256sum "$SRC" | awk '{print $1}')"

timeout 120s ssh -o BatchMode=yes "$NODE_B"   "TARGET_DIR='$TARGET_DIR' STATE_DIR='$STATE_DIR' SRC_SHA='$SRC_SHA' SRC_B64='$SRC_B64' bash -s" <<'NODEB'
set -Eeuo pipefail

echo "[1/6] Install discovery service files"
install -d -m 0755 "$TARGET_DIR" "$STATE_DIR"
printf '%s' "$SRC_B64" | base64 -d > "$TARGET_DIR/discovery_server.py.new"
test -s "$TARGET_DIR/discovery_server.py.new"
install -m 0755 "$TARGET_DIR/discovery_server.py.new" "$TARGET_DIR/discovery_server.py"
rm -f "$TARGET_DIR/discovery_server.py.new"

ACTUAL_SHA="$(sha256sum "$TARGET_DIR/discovery_server.py" | awk '{print $1}')"
[ "$ACTUAL_SHA" = "$SRC_SHA" ] || {
  echo "Discovery server integrity mismatch expected=$SRC_SHA actual=$ACTUAL_SHA" >&2
  exit 43
}

echo "[2/6] Install systemd unit"
cat > /etc/systemd/system/jns-infrastructure-discovery.service <<'UNIT'
[Unit]
Description=JNS Infrastructure LAN Discovery API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/jns-infrastructure-discovery/discovery_server.py
Restart=on-failure
RestartSec=2
User=root
Group=root
Environment=JNS_DISCOVERY_BIND=10.10.10.235
Environment=JNS_DISCOVERY_PORT=8765
Environment=JNS_DISCOVERY_NETWORK=10.10.10.0/24
Environment=JNS_DISCOVERY_STATE=/var/lib/jns-infrastructure-discovery/servers.json
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/var/lib/jns-infrastructure-discovery

[Install]
WantedBy=multi-user.target
UNIT

echo "[3/6] Validate Python"
python3 -m py_compile "$TARGET_DIR/discovery_server.py"

echo "[4/6] Start service"
systemctl daemon-reload
systemctl enable --now jns-infrastructure-discovery.service
systemctl restart jns-infrastructure-discovery.service

echo "[5/6] Verify health endpoint"
for n in $(seq 1 20); do
  if curl -fsS --max-time 2 http://10.10.10.235:8765/health >/tmp/jns-discovery-health.json; then
    cat /tmp/jns-discovery-health.json
    break
  fi
  sleep 1
done
curl -fsS --max-time 2 http://10.10.10.235:8765/health >/dev/null

echo "[6/6] Run initial scan"
curl -fsS --max-time 45 -X POST http://10.10.10.235:8765/api/scan > "$STATE_DIR/initial-scan-response.json"
python3 - <<'PY'
import json
p="/var/lib/jns-infrastructure-discovery/initial-scan-response.json"
d=json.load(open(p,encoding="utf-8"))
print("host_count=",d.get("host_count"))
print("duration_seconds=",d.get("duration_seconds"))
print("finished_at=",d.get("finished_at"))
PY

echo "JNS_DISCOVERY_DEPLOY_OK"
echo "api=http://10.10.10.235:8765"
NODEB
