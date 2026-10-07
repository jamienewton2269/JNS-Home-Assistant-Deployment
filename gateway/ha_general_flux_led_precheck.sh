#!/usr/bin/env bash
set -Eeuo pipefail
echo '=== SNUG SOFA LED HOSTNAME PRECHECK ==='
echo 'hostname=JNS-288328'
echo '--- Node C ---'
getent hosts JNS-288328 || true
command -v host >/dev/null && host JNS-288328 || true
command -v nc >/dev/null && nc -vz -w3 JNS-288328 5577 || true

ssh -o BatchMode=yes -o ConnectTimeout=10 nodeb 'bash -s' <<'NODEB'
set -Eeuo pipefail
echo '--- Node B ---'
getent hosts JNS-288328 || true
command -v host >/dev/null && host JNS-288328 || true
if command -v nc >/dev/null; then nc -vz -w3 JNS-288328 5577 || true; fi
NODEB
