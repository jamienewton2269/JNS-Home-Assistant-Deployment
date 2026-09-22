#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run as root." >&2; exit 1; fi
systemctl disable --now jns-iot-gateway-health.timer jns-iot-gateway-apply.service jns-iot-zigbee-serial.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/jns-iot-gateway-health.timer \
      /etc/systemd/system/jns-iot-gateway-health.service \
      /etc/systemd/system/jns-iot-gateway-apply.service \
      /etc/systemd/system/jns-iot-zigbee-serial.service \
      /usr/local/sbin/jns-gateway
rm -rf /usr/lib/jns-iot-gateway
systemctl daemon-reload
printf '%s\n' "Core removed. Configuration/state under /etc/jns-iot-gateway and /var/lib/jns-iot-gateway were retained for recovery."
