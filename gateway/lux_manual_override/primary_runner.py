#!/usr/bin/env python3
"""Run guarded HA-Primary sidebar launcher deployment via trusted Node C->A."""
import base64,json,pathlib,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
root=pathlib.Path('gateway/lux_manual_override')
source=(root/'patch_vm902.py').read_bytes()
dashboard=(root/'ha_primary_dashboard.yaml').read_bytes()
mode='--apply' if '--apply' in sys.argv else '--dry-run'
code="DASH_B64="+repr(base64.b64encode(dashboard).decode())+";exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(source).decode())+"),'<lux-primary-panel>','exec'))"
response=json.loads(ssh_host('nodea',['qm','guest','exec','902','--','docker','exec','homeassistant','python3','-c',code,mode]))
pid=response.get('pid')
for i in range(120):
 if response.get('exited'):break
 if not isinstance(pid,int):raise RuntimeError('Missing initial VM902 PID')
 time.sleep(2)
 response=json.loads(ssh_host('nodea',['qm','guest','exec-status','902',str(pid)]))
out=response.get('out-data') or ''
print('JNS_PRIMARY_LUX_RESULT '+out[-6000:],flush=True)
if response.get('exitcode')!=0 or ('JNS_PRIMARY_LUX_APPLIED' if mode=='--apply' else 'JNS_PRIMARY_LUX_PLAN') not in out:
 print('JNS_PRIMARY_LUX_ERROR '+(response.get('err-data') or '')[-900:],flush=True)
 raise SystemExit(2)
