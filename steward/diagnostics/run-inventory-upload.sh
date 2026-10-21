#!/bin/sh
# Optional daily inventory/upload, only after private repo and access are configured.
set -eu
umask 077
DIR=/var/lib/jns-steward/reports
mkdir -p "$DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
HOST=$(hostname | tr -cd 'a-zA-Z0-9-')
REPORT="$DIR/${HOST}-${STAMP}.json"
python3 /usr/local/libexec/jns-steward/steward_host_inventory.py --out "$REPORT"
python3 /usr/local/libexec/jns-steward/steward_diagnostics_upload.py --input "$REPORT"
# Do not erase raw report before upload acknowledgement and review.
