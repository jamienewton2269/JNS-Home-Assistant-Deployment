#!/usr/bin/env python3
"""Read-only VM902 audit for legitimately authorised HA API clients."""
import readiness_probe as rp, json
q=['qm','guest','exec','902','--','docker','ps','--format','{{.Names}}']
try:
 d=json.loads(rp.ssh_host('nodea',q))
 for i in range(35):
  if d.get('exited'):break
  import time;time.sleep(1)
  d=json.loads(rp.ssh_host('nodea',['qm','guest','exec-status','902',str(d['pid'])]))
 if d.get('exitcode')!=0:
  print('VM902_CONTAINER_AUDIT blocked');raise SystemExit(0)
 names=(d.get('out-data') or '').splitlines()
 print("VM902_CONTAINERS",json.dumps([n for n in names if n=='homeassistant' or n.startswith('addon_')]))
except Exception as e:
 print('VM902_CONTAINER_AUDIT blocked',type(e).__name__)
