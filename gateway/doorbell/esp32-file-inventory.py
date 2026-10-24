#!/usr/bin/env python3
"""Read-only inspection of doorbell firmware filenames on HA900."""
import subprocess
r=subprocess.run(["ssh","nodea","qm guest exec 900 -- ls -la /mnt/data/supervisor/homeassistant/esphome"],capture_output=True,text=True,timeout=20)
print("ESPHOME_LIST_EXIT",r.returncode)
print("ESPHOME_LIST",(r.stdout or r.stderr)[:3000])
