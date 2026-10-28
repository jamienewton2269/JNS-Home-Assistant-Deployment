#!/usr/bin/env python3
"""No-write preflight for predictive heating package/dashboard on HA-General VM905."""
import base64,json,pathlib,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
DIR=pathlib.Path('gateway/heating_presence')
src=base64.b64encode((DIR/'patch_vm905.py').read_bytes()).decode()
pkg=base64.b64encode((DIR/'jns_predictive_schedule.yaml').read_bytes()).decode()
code="exec(compile(__import__('base64').b64decode("+repr(src)+"),'<jns-heating-presence>','exec'))"
r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',code,pkg,'--dry-run']))
until=time.monotonic()+90
while not r.get('exited'):
 if not isinstance(r.get('pid'),int):raise RuntimeError('Missing QGA PID; no retry')
 if time.monotonic()>until:raise RuntimeError('QGA run incomplete; no retry')
 time.sleep(2)
 r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
out=r.get('out-data') or ''
print('JNS_HEATING_PRESENCE_DRYRUN_RESULT '+out[-3500:],flush=True)
if r.get('exitcode')!=0 or 'JNS_HEATING_PRESENCE_PLAN' not in out:
 print('JNS_HEATING_PRESENCE_DRYRUN_ERROR '+str(r.get('err-data') or '')[-750:],flush=True)
 raise SystemExit(2)
