#!/usr/bin/env bash
set -u
echo "=== NODE C STEWARD WEB PRECHECK ==="
hostname
whoami
id
echo
echo "sudo_noninteractive:"
if sudo -n true 2>/dev/null; then echo YES; else echo NO; fi
echo
echo "candidate steward/natural automation paths:"
find /home /opt /srv -maxdepth 3 \( -iname '*steward*' -o -iname '*natural*automation*' \) -print 2>/dev/null | head -50 || true
echo
echo "listening tcp ports:"
ss -ltn 2>/dev/null | sed -n '1,80p' || true
echo
echo "python:"
command -v python3 || true
python3 --version 2>/dev/null || true
