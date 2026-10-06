#!/usr/bin/env bash
# ==============================================================================
# Deploy HA-General DNS name and Testing dashboard
# ==============================================================================
# PURPOSE
#   Gives HA-General (VM905 / 10.10.10.223) a stable local DNS name and installs
#   the Home Assistant-native "Testing" dashboard used for device recovery,
#   testing and commissioning.
#
# CHANGES
#   DNS: AdGuard Home CT218 gets:
#        ha-general.home.arpa -> 10.10.10.223
#        ha-general           -> 10.10.10.223
#   HA:  /config/dashboards/testing.yaml
#        /config/www/community/auto-entities/auto-entities.js
#        safe merge into the existing top-level lovelace: configuration.
#
# DASHBOARD BEHAVIOUR
#   - Lights/switches are toggle controls.
#   - Fans get a separate tab.
#   - Sensor and binary-sensor states get a separate tab.
#   - Grow lights and protected IT can be separated by HA Labels.
#   - Commissioning uses native Home Assistant Areas and Labels.
#   - Newly discovered entities are consumed automatically by Auto Entities.
#
# SAFETY
#   - Backs up AdGuardHome.yaml and configuration.yaml before modification.
#   - Preserves the existing General dashboard.
#   - Validates Home Assistant configuration before requesting a restart.
#   - Restores configuration.yaml automatically if validation fails.
#   - Does not alter Zigbee/MQTT network identity or device pairing.
#
# RUN LOCATION
#   Node C self-hosted GitHub runner / management gateway.
#
# DOCUMENTATION CATALOGUE DESCRIPTION
#   "Deploys the stable ha-general.home.arpa DNS name and the HA-General Testing
#    dashboard with automatic light/switch/fan/sensor discovery and native HA
#    commissioning via Areas and Labels; validates configuration before restart."
# ==============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASH_FILE="$REPO_ROOT/ha_testing_dashboard/testing-dashboard.yaml"
NODE_B="nodeb"
HA_IP="10.10.10.223"
STAMP="$(date +%Y%m%d-%H%M%S)"

[[ -f "$DASH_FILE" ]] || { echo "Missing $DASH_FILE" >&2; exit 1; }

# Catalogue this reusable script on the Node C documentation web root when present.
DOC_DIR="/home/github-runner/steward-web/docs"
if [[ -d "$DOC_DIR" ]]; then
  DOC_FILE="$DOC_DIR/script-catalogue.txt"
  DOC_LINE="deploy-ha-general-testing.sh - Deploys the stable ha-general.home.arpa DNS name and the HA-General Testing dashboard with automatic light/switch/fan/sensor discovery and native HA commissioning via Areas and Labels; validates configuration before restart."
  touch "$DOC_FILE"
  TMP_DOC="$(mktemp)"
  grep -v "^deploy-ha-general-testing\.sh - " "$DOC_FILE" > "$TMP_DOC" || true
  printf "%s\n" "$DOC_LINE" >> "$TMP_DOC"
  cat "$TMP_DOC" > "$DOC_FILE"
  rm -f "$TMP_DOC"
fi

echo "=== 1/6 Configure HA-General DNS aliases ==="
timeout 20s ssh -o BatchMode=yes "$NODE_B" "bash -s" <<EOF_DNS
set -euo pipefail
pct exec 218 -- cp -a /opt/AdGuardHome/AdGuardHome.yaml /opt/AdGuardHome/AdGuardHome.yaml.jns-ha-general-$STAMP.bak
pct exec 218 -- python3 - <<\'PY\'
from pathlib import Path
p=Path("/opt/AdGuardHome/AdGuardHome.yaml")
s=p.read_text()
entries=[("ha-general.home.arpa","10.10.10.223"),("ha-general","10.10.10.223")]
if "  rewrites: []" in s:
    block="  rewrites:\n" + "".join(f"    - domain: {d}\n      answer: {a}\n" for d,a in entries)
    s=s.replace("  rewrites: []",block,1)
else:
    marker="  rewrites:\n"
    if marker not in s:
        raise SystemExit("AdGuard rewrites section not found")
    additions=""
    for d,a in entries:
        if f"domain: {d}" not in s:
            additions += f"    - domain: {d}\n      answer: {a}\n"
    if additions:
        s=s.replace(marker,marker+additions,1)
p.write_text(s)
PY
pct exec 218 -- systemctl restart AdGuardHome
pct exec 218 -- systemctl is-active AdGuardHome
EOF_DNS

echo "=== 2/6 Verify DNS server answers ==="
timeout 12s ssh -o BatchMode=yes "$NODE_B" "pct exec 218 -- sh -lc \'command -v nslookup >/dev/null && { nslookup ha-general.home.arpa 127.0.0.1; nslookup ha-general 127.0.0.1; } || grep -A8 \"rewrites:\" /opt/AdGuardHome/AdGuardHome.yaml\'"

echo "=== 3/6 Prepare dashboard payload ==="
DASH_B64="$(base64 -w0 "$DASH_FILE")"

echo "=== 4/6 Install dashboard through the proven Natural Automation QGA path ==="
timeout 150s ssh -o BatchMode=yes "$NODE_B" "DASH_B64=\'$DASH_B64\' STAMP=\'$STAMP\' python3 -s" <<\'PY_NODEB\'
import os, json, textwrap
from pathlib import Path
import sys
sys.path.insert(0,"/opt/natural-automation")
import natural_automation as na

dash_b64=os.environ["DASH_B64"]
stamp=os.environ["STAMP"]
code = r"""
from pathlib import Path
import base64, urllib.request, subprocess, shutil, json, time

root=Path("/config")
cfg=root/"configuration.yaml"
backup=root/f"configuration.yaml.jns-testing-{STAMP}.bak"
dash=root/"dashboards"/"testing.yaml"
js=root/"www"/"community"/"auto-entities"/"auto-entities.js"

(root/"dashboards").mkdir(parents=True,exist_ok=True)
js.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(cfg,backup)
dash.write_bytes(base64.b64decode(DASH_B64))

url="https://raw.githubusercontent.com/thomasloven/lovelace-auto-entities/v1.16.1/auto-entities.js"
with urllib.request.urlopen(url,timeout=20) as r:
    js.write_bytes(r.read())

text=cfg.read_text()
lines=text.splitlines()
start=None
for i,l in enumerate(lines):
    if l.startswith("lovelace:"):
        start=i; break
if start is None:
    raise RuntimeError("Existing lovelace block not found")
end=len(lines)
for j in range(start+1,len(lines)):
    l=lines[j]
    if l and not l[0].isspace() and not l.startswith("#"):
        end=j; break
block=lines[start:end]

if not any(x.strip().startswith("resource_mode:") for x in block):
    insert_at=1
    for i,x in enumerate(block[1:],1):
        if x.startswith("  mode:"):
            insert_at=i+1; break
    block.insert(insert_at,"  resource_mode: yaml")

if not any(x.startswith("  resources:") for x in block):
    d_idx=next((i for i,x in enumerate(block) if x.startswith("  dashboards:")),len(block))
    res=[
      "  resources:",
      "    - url: /local/community/auto-entities/auto-entities.js?v=1.16.1",
      "      type: module",
    ]
    block[d_idx:d_idx]=res
elif not any("auto-entities.js" in x for x in block):
    r_idx=next(i for i,x in enumerate(block) if x.startswith("  resources:"))
    insert_at=r_idx+1
    while insert_at < len(block) and (not block[insert_at] or block[insert_at].startswith("    ") or block[insert_at].startswith("      ")) and not block[insert_at].startswith("  dashboards:"):
        insert_at+=1
    block[insert_at:insert_at]=[
      "    - url: /local/community/auto-entities/auto-entities.js?v=1.16.1",
      "      type: module",
    ]

if not any("testing-dashboard:" in x for x in block):
    d_idx=next(i for i,x in enumerate(block) if x.startswith("  dashboards:"))
    insert_at=len(block)
    block[insert_at:insert_at]=[
      "    testing-dashboard:",
      "      mode: yaml",
      "      title: Testing",
      "      icon: mdi:test-tube",
      "      show_in_sidebar: true",
      "      require_admin: false",
      "      filename: dashboards/testing.yaml",
    ]

new_lines=lines[:start]+block+lines[end:]
cfg.write_text("\n".join(new_lines)+"\n")

check=subprocess.run(
    ["python3","-m","homeassistant","--script","check_config","-c","/config"],
    text=True,capture_output=True,timeout=90
)
print("CHECK_EXIT",check.returncode)
print((check.stdout or "")[-4000:])
print((check.stderr or "")[-4000:])
if check.returncode != 0:
    shutil.copy2(backup,cfg)
    raise RuntimeError("Home Assistant config check failed; configuration.yaml restored")

print(json.dumps({
  "ok":True,
  "backup":str(backup),
  "dashboard":str(dash),
  "resource":str(js),
  "resource_bytes":js.stat().st_size,
},separators=(",",":")))
"""
code=code.replace("STAMP",repr(stamp)).replace("DASH_B64",repr(dash_b64))
print(na.qga_python(code, timeout=125))
PY_NODEB

echo "=== 5/6 Restart HA Core ==="
timeout 20s ssh -o BatchMode=yes "$NODE_B" "timeout 15s qm guest exec 905 --timeout 10 -- ha core restart >/dev/null || true"

echo "Waiting for HA-General HTTP..."
for n in $(seq 1 36); do
  if timeout 6s ssh -o BatchMode=yes "$NODE_B" "curl -fsS --max-time 3 http://$HA_IP/ >/dev/null"; then
    echo "HA-General HTTP ready after attempt $n."
    break
  fi
  sleep 5
done

echo "=== 6/6 Verify dashboard/resource endpoints ==="
timeout 10s ssh -o BatchMode=yes "$NODE_B" "curl -sS -o /dev/null -w \'root=%{http_code}\\n\' --max-time 4 http://$HA_IP/; curl -sS -o /dev/null -w \'testing=%{http_code}\\n\' --max-time 4 http://$HA_IP/testing-dashboard/controls; curl -sS -o /dev/null -w \'auto_entities=%{http_code}\\n\' --max-time 4 http://$HA_IP/local/community/auto-entities/auto-entities.js?v=1.16.1"

echo
echo "=== DEPLOYMENT COMPLETE ==="
echo "Companion internal URL: http://ha-general.home.arpa/"
echo "Testing dashboard:      http://ha-general.home.arpa/testing-dashboard/controls"
echo "Commissioning:          http://ha-general.home.arpa/testing-dashboard/commissioning"