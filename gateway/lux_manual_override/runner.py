#!/usr/bin/env python3
"""Run guarded HA-General Lux manual-off patch via Node C runner and VM905 QGA."""
import base64,json,pathlib,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
HERE=pathlib.Path('gateway/lux_manual_override')
CODE=(HERE/'patch_vm905.py').read_bytes()
PACKAGE=(HERE/'jns_lux_manual_off_v1.yaml').read_bytes()
MODE='--apply' if '--apply' in sys.argv else '--dry-run'
source="PACKAGE_B64="+repr(base64.b64encode(PACKAGE).decode())+";exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(CODE).decode())+"),'<jns-lux-manual-patch>','exec'))"
command=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',source,MODE]
data=json.loads(ssh_host('nodeb',command))
pid=data.get('pid')
deadline=time.monotonic()+160
while not data.get('exited'):
    if not isinstance(pid,int):raise RuntimeError('Guest exec returned no initial PID; manual review')
    if time.monotonic()>deadline:raise RuntimeError('Guest exec incomplete PID '+str(pid))
    time.sleep(2)
    data=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
print('JNS_LUX_RUNNER',data.get('out-data','')[-8500:],flush=True)
if data.get('exitcode')!=0:
    print('JNS_LUX_RUNNER_ERROR',(data.get('err-data') or '')[-1000:],flush=True)
    raise SystemExit(2)
if ('JNS_LUX_MANUAL_APPLIED' if MODE=='--apply' else 'JNS_LUX_MANUAL_PLAN') not in data.get('out-data',''):
    raise SystemExit('no expected plan/apply result')
