#!/usr/bin/env bash
set -euo pipefail
echo "NODEA LAN"
ssh nodea 'hostname; ip -4 -br addr; ip route'
echo "NODEB LAN"
ssh nodeb 'hostname; ip -4 -br addr; ip route'
