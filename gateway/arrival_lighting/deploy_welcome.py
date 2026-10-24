#!/usr/bin/env python3
"""Controlled Welcome Home VM905 deployment. No lights activated at install."""
import base64,json,re,sys,time
from pathlib import Path
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
WELCOME=(Path('gateway/arrival_lighting/jns_welcome_home_vm905.STAGED.yaml')).read_bytes()
PATCH=(Path('gateway/arrival_lighting/patch_welcome.py')).read_bytes()
def guest(args,limit=600):
 res=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 pid=res.get('pid')
 until=time.monotonic()+limit
 while not res.get('exited'):
  if not isinstance(pid,int):raise RuntimeError('QGA initial PID missing')
  if time.monotonic()>until:raise RuntimeError('QGA '+str(pid)+' exceeded timeout')
  time.sleep(3)
  res=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 return res
def package(mode):
 src="WELCOME_PACKAGE_B64="+repr(base64.b64encode(WELCOME).decode())+";exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(PATCH).decode())+"),'<welcome-patch>','exec'))"
 res=guest(['docker','exec','homeassistant','python3','-c',src,mode],90)
 print('JNS_WELCOME_'+mode+' '+(res.get('out-data') or '')[-1800:],flush=True)
 if res.get('exitcode')!=0:raise RuntimeError('welcome package '+mode+' failed '+(res.get('err-data') or '')[-200:])
 return res.get('out-data') or ''
def core(command,limit=400):
 r=guest(['ha',*command],limit)
 print('JNS_WELCOME_HA '+json.dumps({'command':' '.join(command),'exitcode':r.get('exitcode'),
  'output_tail':(r.get('out-data') or '')[-430:]}),flush=True)
 return r.get('exitcode')==0
def rollback(m):
 script="from pathlib import Path;import hashlib;p=Path("+repr(m['path'])+");assert hashlib.sha256(p.read_bytes()).hexdigest()=="+repr(m['sha256'])+";p.unlink();print('JNS_WELCOME_PACKAGE_RESTORED')"
 r=guest(['docker','exec','homeassistant','python3','-c',script],75)
 print('JNS_WELCOME_ROLLBACK '+(r.get('out-data') or '')[-500:],flush=True)
 if r.get('exitcode')!=0:raise RuntimeError('package rollback blocked')
if __name__=='__main__':
 try:
  package('--dry-run')
  output=package('--apply')
  match=re.search(r'JNS_WELCOME_APPLIED (\{.+\})',output)
  if not match:raise RuntimeError('missing package manifest')
  manifest=json.loads(match.group(1))
  try:valid=core(['core','check'],360)
  except Exception:valid=False
  if not valid:
   rollback(manifest);raise RuntimeError('HA-General config check failed; package removed')
  print('JNS_WELCOME_CORE_CONFIG_VALID',flush=True)
  if not core(['core','restart'],560):raise RuntimeError('HA General restart unsuccessful')
  if not core(['core','info'],120):raise RuntimeError('HA General post-restart health not confirmed')
  print('JNS_WELCOME_INSTALLED_DISABLED_READY_FOR_TEST',flush=True)
 except Exception as e:
  print('JNS_WELCOME_DEPLOY_FAILED '+type(e).__name__+' '+str(e)[:270],flush=True)
  raise SystemExit(1)
