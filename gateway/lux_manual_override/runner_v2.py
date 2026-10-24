#!/usr/bin/env python3
"""JNS guarded Node C -> Node B -> HA905 Lux V2 runner; no restart."""
import base64,json,pathlib,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
HERE=pathlib.Path('gateway/lux_manual_override')
source=(HERE/'patch_v2_vm905.py').read_bytes()
mode='--apply' if '--apply' in sys.argv else '--dry-run'
code="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(source).decode())+"),'<jns-lux-v2>','exec'))"
cmd=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',code,mode]
r=json.loads(ssh_host('nodeb',cmd));pid=r.get('pid')
until=time.monotonic()+150
while not r.get('exited'):
 if not isinstance(pid,int):raise RuntimeError('Missing QGA PID; no blind retry')
 if time.monotonic()>until:raise RuntimeError('QGA PID '+str(pid)+' unfinished; no retry')
 time.sleep(2)
 r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
out=r.get('out-data') or ''
print('JNS_LUX_V2_RESULT '+out[-8000:],flush=True)
if r.get('exitcode')!=0 or ('JNS_LUX_V2_APPLIED' if mode=='--apply' else 'JNS_LUX_V2_PLAN') not in out:
 print('JNS_LUX_V2_ERROR '+(r.get('err-data') or '')[-500:],flush=True)
 raise SystemExit(2)
