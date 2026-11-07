#!/usr/bin/env bash
# JNS Health Intelligence: download and prepare locally; NO installation or HA restart.
set -euo pipefail
umask 077
BASE="https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/dev/jns-health-intelligence-v01-20261031/health-intelligence"
DEST="/root/jns-health/staging"
mkdir -p "$DEST"
python3 - "$BASE" "$DEST" <<'PY'
import sys, urllib.request, pathlib
base, dest = sys.argv[1], pathlib.Path(sys.argv[2])
for name, local in [
    ("tools/build_private_package.py", "build_private_package.py"),
    ("dashboards/jns_health_intelligence.yaml", "jns_health_intelligence.yaml")
]:
    with urllib.request.urlopen(base + "/" + name, timeout=20) as r:
        (dest / local).write_bytes(r.read())
    (dest / local).chmod(0o600)
PY
: "${JNS_HEALTH_PROFILE_A:?Set private sensor prefix for Profile A}"
: "${JNS_HEALTH_PROFILE_B:?Set private sensor prefix for Profile B}"
python3 "$DEST/build_private_package.py" \
  --profile-a "$JNS_HEALTH_PROFILE_A" \
  --profile-b "$JNS_HEALTH_PROFILE_B" \
  --out "$DEST/jns_health_private_package.yaml"
python3 - "$DEST" <<'PY'
import pathlib, sys
p=pathlib.Path(sys.argv[1])
pkg=(p/"jns_health_private_package.yaml").read_text()
dash=(p/"jns_health_intelligence.yaml").read_text()
assert pkg.count("unique_id: jns_health_profile_") == 18
required={
 "sensor.jns_health_profile_a_heart_rate",
 "sensor.jns_health_profile_a_hrv",
 "sensor.jns_health_profile_a_steps",
 "sensor.jns_health_profile_b_heart_rate",
 "sensor.jns_health_profile_b_hrv",
 "sensor.jns_health_profile_b_steps",
}
assert all(x in dash for x in required)
assert "_heart_rate_variability" in pkg
assert "_daily_steps" in pkg
print("PASS: 18 private template sensors and dashboard aliases staged.")
print("Private source configuration remains on Node C.")
print("NOT deployed. No HA configuration modified and no restart requested.")
PY
