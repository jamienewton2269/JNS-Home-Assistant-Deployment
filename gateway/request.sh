#!/usr/bin/env bash
set -euo pipefail
ssh nodeb 'echo RESOLVE; getent ahostsv4 nodea || true; echo ROUTE; ip route; echo PING; timeout 5 ping -c 2 nodea || true; echo SSHCFG; ssh -G nodea 2>/dev/null | grep -E "^(hostname|user|port|identityfile|proxycommand) " || true'
