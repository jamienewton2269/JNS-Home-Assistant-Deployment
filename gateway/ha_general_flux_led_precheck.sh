#!/usr/bin/env bash
set -Eeuo pipefail
ssh -o BatchMode=yes -o ConnectTimeout=10 nodeb 'bash -s' <<'NODEB'
set -Eeuo pipefail
VMID=905
echo '=== HA-GENERAL MAGIC HOME PRECHECK ==='
qm status "$VMID"
qm guest exec "$VMID" -- /bin/bash -lc "python3 - <<'PY'
import json,os,socket
root='/mnt/data/supervisor/homeassistant'
print('--- reachability 10.10.10.170:5577 ---')
s=socket.socket(); s.settimeout(3)
try:
 s.connect(('10.10.10.170',5577)); print('TCP_5577=OPEN')
except Exception as e: print('TCP_5577=FAIL',repr(e))
finally: s.close()
for rel,key in [('.storage/core.config_entries','entries'),('.storage/core.device_registry','devices'),('.storage/core.entity_registry','entities')]:
 p=os.path.join(root,rel)
 print('---',rel,'---')
 try:d=json.load(open(p,encoding='utf-8'))
 except Exception as e: print('READ_ERROR',e); continue
 for x in d.get('data',{}).get(key,[]):
  t=json.dumps(x,ensure_ascii=False).lower()
  if 'flux_led' in t or 'b4:e8:42:28:83:28' in t or '10.10.10.170' in t or '288328' in t or 'sofa_led' in t:
   safe=dict(x)
   for k in list(safe):
    if any(q in k.lower() for q in ('password','token','secret','local_key','api_key')): safe[k]='<REDACTED>'
   print(json.dumps(safe,ensure_ascii=False,sort_keys=True))
PY"
NODEB
