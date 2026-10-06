#!/usr/bin/env python3
"""
Apply the HA-General Testing dashboard YAML through Natural Automation's proven
QEMU Guest Agent execution path.

Purpose:
- Read the corrected dashboard payload staged on Node B.
- Parse it with PyYAML inside the Home Assistant container before modifying live.
- Back up the current /config/dashboards/testing.yaml.
- Replace the live dashboard.
- Parse the live copy again and report its view names.

This helper changes only the Testing dashboard YAML. It does not restart Home
Assistant or alter Zigbee, MQTT, devices, automations, DNS or other dashboards.
"""

from pathlib import Path
import sys

sys.path.insert(0, "/opt/natural-automation")
import natural_automation as na

payload_path = Path("/tmp/jns-testing-dashboard.b64")
b64 = payload_path.read_text().strip()

code = f"""
from pathlib import Path
import base64
import yaml
import shutil
import time
import json

target = Path("/config/dashboards/testing.yaml")
payload = base64.b64decode({b64!r})
text = payload.decode("utf-8")

parsed = yaml.safe_load(text)
if not isinstance(parsed, dict) or not isinstance(parsed.get("views"), list):
    raise RuntimeError("Testing dashboard YAML is valid YAML but has no views list")

backup = target.with_name(
    "testing.yaml.jns-fix-" + time.strftime("%Y%m%d-%H%M%S") + ".bak"
)
if target.exists():
    shutil.copy2(target, backup)

target.write_text(text)

live = yaml.safe_load(target.read_text())
if not isinstance(live, dict) or not isinstance(live.get("views"), list):
    raise RuntimeError("Live Testing dashboard failed post-write validation")

print(json.dumps({{
    "ok": True,
    "backup": str(backup),
    "bytes": target.stat().st_size,
    "views": [v.get("title") for v in live.get("views", [])],
}}, separators=(",", ":")))
"""

print(na.qga_python(code, timeout=15))
payload_path.unlink(missing_ok=True)
