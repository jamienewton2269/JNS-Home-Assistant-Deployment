#!/usr/bin/env python3
"""Preflight WC patch inside actual HA-General Core container (no writes)."""
import sys,json,base64,time,pathlib
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
source=pathlib.Path('gateway/wc-lighting/patch_core.py').read_bytes()
cmd="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(source).decode())+"),'<wc-patch>','exec'))"
command=['qm','guest','exec','905','--timeout','12','--','docker','exec','homeassistant','python3','-c',cmd]
res=json.loads(ssh_host('nodeb',command))
for i in range(40):
 if res.get('exited'):break
 if not isinstance(res.get('pid'),int):raise RuntimeError('Guest agent did not return PID')
 time.sleep(1)
 res=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(res['pid'])]))
print('WC_PREFLIGHT',res.get('out-data','')[:1000],flush=True)
if not res.get('exited') or res.get('exitcode')!=0:raise SystemExit(1)
d=json.loads(res.get('out-data') or '{}')
if d.get('status') not in ['preflight_ok','already_applied']:raise SystemExit(2)
print('WC_READY_FOR_TARGETED_APPLY',flush=True)
