#!/usr/bin/env bash
set -euo pipefail
echo "SOURCE"
ssh nodeb '
  systemctl is-active jns-ha-replication.service || true
  zfs get -Hp -o name,property,value logicalused,used,referenced,volsize vmdata/vm-902-disk-1 2>/dev/null || true
  ip -s link show vmbr0 | sed -n "1,12p"
  ps -eo pid,etime,cmd | grep -E "zfs send|jns-ha-replicate" | grep -v grep || true
'
echo "TARGET"
ssh nodea '
  zfs get -Hp -o name,property,value logicalused,used,referenced,volsize vmdata/vm-902-disk-1 2>/dev/null || true
  ip -s link show vmbr0 | sed -n "1,12p"
'
