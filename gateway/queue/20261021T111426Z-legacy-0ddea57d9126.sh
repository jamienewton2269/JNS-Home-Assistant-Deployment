#!/usr/bin/env bash
set -Eeuo pipefail
echo "=== V1 LIVE SOURCE INVENTORY ==="
date -Is
ssh nodeb '
  set -Eeuo pipefail
  echo "HOST=$(hostname)"
  echo "--- natural automation files ---"
  find /opt/natural-automation -maxdepth 3 -type f \
    ! -path "*/backup-*/*" ! -path "*/__pycache__/*" ! -path "*/data/*" \
    -printf "%p\t%s bytes\n" | sort
  echo "--- real progress files ---"
  find /opt/real-progress -maxdepth 2 -type f ! -path "*/__pycache__/*" -printf "%p\t%s bytes\n" 2>/dev/null | sort || true
  echo "--- service ---"
  systemctl cat natural-automation.service
  echo "--- hashes ---"
  find /opt/natural-automation/steward -maxdepth 1 -type f -name "*.py" -print0 2>/dev/null |
    xargs -0r sha256sum
  sha256sum /opt/natural-automation/natural_automation.py
  sha256sum /opt/real-progress/real_progress.py 2>/dev/null || true
'
