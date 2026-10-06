#!/usr/bin/env bash
set -Eeuo pipefail
echo "=== CT130 NETWORK MONITOR PREFLIGHT ==="
echo "runner=$(hostname) user=$(whoami)"
date -Is
echo "-- CT130 --"
sudo -n pct status 130
echo "-- service --"
sudo -n pct exec 130 -- systemctl is-active jns-netmon.service
echo "-- current health --"
sudo -n pct exec 130 -- curl -fsS --max-time 5 http://10.10.10.240:8080/health
echo
echo "-- state version --"
sudo -n pct exec 130 -- curl -fsS --max-time 30 http://10.10.10.240:8080/api/state | python3 -c 'import json,sys; d=json.load(sys.stdin); print("version:",d.get("version")); print("devices:",len(d.get("devices",[]))); print("links:",len(d.get("links",[])))'
