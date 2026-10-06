#!/usr/bin/env bash
set -Eeuo pipefail
echo "=== CT130 NETWORK MONITOR PREFLIGHT ==="
echo "runner=$(hostname) user=$(whoami)"
date -Is
echo "-- CT130 status --"
sudo -n pct status 130
echo "-- monitor service --"
sudo -n pct exec 130 -- systemctl is-active jns-netmon.service
echo "-- health endpoint --"
sudo -n pct exec 130 -- curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:8080/health
echo
echo "-- API state summary --"
sudo -n pct exec 130 -- curl --noproxy '*' -fsS --max-time 35 http://127.0.0.1:8080/api/state | python3 -c 'import json,sys; d=json.load(sys.stdin); print("version:",d.get("version")); print("devices:",len(d.get("devices",[]))); print("links:",len(d.get("links",[])))'
