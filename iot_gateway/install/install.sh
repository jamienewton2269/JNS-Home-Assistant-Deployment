#!/usr/bin/env bash
set -euo pipefail

PREFIX=/usr/lib/jns-iot-gateway
ETC=/etc/jns-iot-gateway
PROFILE=zigbee_serial
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<EOF
Usage: sudo ./install.sh [--profile zigbee_serial|maintenance|disabled] [--config FILE]

Installs the lightweight JNS IoT Gateway core. Only dependencies required by
selected profiles are installed. Future profiles are intentionally rejected
until their modules are implemented.
EOF
}

CONFIG_SOURCE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:?missing profile}"; shift 2 ;;
    --config) CONFIG_SOURCE="${2:?missing config}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

case "$PROFILE" in
  zigbee_serial|maintenance|disabled) ;;
  zigbee2mqtt|thread_otbr|matter_thread_edge)
    echo "Profile '$PROFILE' is reserved but not implemented in v0.1.0." >&2
    exit 3
    ;;
  *) echo "Unknown profile: $PROFILE" >&2; exit 2 ;;
esac

install -d -m 0755 "$PREFIX" "$PREFIX/profiles" "$ETC" /var/lib/jns-iot-gateway
install -m 0755 "$SOURCE_DIR/core/jns_gateway.py" "$PREFIX/jns_gateway.py"
ln -sfn "$PREFIX/jns_gateway.py" /usr/local/sbin/jns-gateway
install -m 0644 "$SOURCE_DIR/profiles/"*.json "$PREFIX/profiles/"

if [[ -n "$CONFIG_SOURCE" ]]; then
  install -m 0640 "$CONFIG_SOURCE" "$ETC/gateway.json"
elif [[ ! -f "$ETC/gateway.json" ]]; then
  install -m 0640 "$SOURCE_DIR/config/gateway.example.json" "$ETC/gateway.json"
fi

install -m 0644 "$SOURCE_DIR/systemd/jns-iot-gateway-apply.service" /etc/systemd/system/
install -m 0644 "$SOURCE_DIR/systemd/jns-iot-gateway-health.service" /etc/systemd/system/
install -m 0644 "$SOURCE_DIR/systemd/jns-iot-gateway-health.timer" /etc/systemd/system/

if [[ "$PROFILE" == "zigbee_serial" ]]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends ser2net
  if ! id jns-ser2net >/dev/null 2>&1; then
    useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin jns-ser2net
  fi
  usermod -a -G dialout jns-ser2net
  install -m 0644 "$SOURCE_DIR/systemd/jns-iot-zigbee-serial.service" /etc/systemd/system/
else
  systemctl disable --now jns-iot-zigbee-serial.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/jns-iot-zigbee-serial.service "$ETC/ser2net-zigbee.yaml"
fi

python3 - "$ETC/gateway.json" "$PROFILE" <<'PY'
import json, os, sys, tempfile
path, profile = sys.argv[1], sys.argv[2]
with open(path, encoding='utf-8') as f:
    cfg = json.load(f)
cfg.setdefault('profile', {})['active'] = profile
fd, temp = tempfile.mkstemp(prefix='.jns-', dir=os.path.dirname(path))
with os.fdopen(fd, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
os.chmod(temp, 0o640)
os.replace(temp, path)
PY

systemctl daemon-reload
systemctl enable jns-iot-gateway-apply.service jns-iot-gateway-health.timer

if /usr/local/sbin/jns-gateway validate >/dev/null 2>&1; then
  systemctl restart jns-iot-gateway-apply.service
  systemctl enable --now jns-iot-gateway-health.timer
  /usr/local/sbin/jns-gateway emit NODE_INSTALL --field "version=0.1.0" --field "profile=$PROFILE" --message "JNS IoT Gateway installed" >/dev/null || true
  echo "JNS IoT Gateway v0.1.0 installed and profile applied: $PROFILE"
else
  echo "Core installed, but configuration still needs commissioning:" >&2
  echo "  $ETC/gateway.json" >&2
  echo "Then run: jns-gateway validate && jns-gateway apply" >&2
fi
