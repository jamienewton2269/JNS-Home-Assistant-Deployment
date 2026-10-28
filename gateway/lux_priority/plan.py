#!/usr/bin/env python3
"""JNS Lux ladder read-only VM905 patch validation (no HA config writes)."""
import base64,json,pathlib,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
ROOT=pathlib.Path('gateway/lux_priority')
def qga(args):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 until=time.monotonic()+100
 while not r.get('exited'):
  if not isinstance(r.get('pid'),int):raise RuntimeError('No guest agent PID')
  if time.monotonic()>until:raise RuntimeError('Guest agent dry-run still running')
  time.sleep(2)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 return r
assert 'running' in ssh_host('nodeb',['qm','status','905'])
prog=ROOT.joinpath('patch_vm905.py').read_bytes()
data=ROOT.joinpath('jns_lux_priority_ladder.yaml').read_bytes()
py="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(prog).decode())+"),'<jns-lux-priority>','exec'))"
r=qga(['docker','exec','homeassistant','python3','-c',py,base64.b64encode(data).decode(),'--dry-run'])
print('JNS_LUX_LADDER_DRYRUN',(r.get('out-data') or '')[-4200:],flush=True)
if r.get('exitcode')!=0:raise RuntimeError('Dry-run blocked: '+(r.get('err-data') or '')[-650:])
if 'JNS_LUX_LADDER_PLAN' not in (r.get('out-data') or ''):raise RuntimeError('Missing YAML plan attestation')
