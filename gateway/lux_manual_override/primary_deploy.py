#!/usr/bin/env python3
"""Guarded HA-Primary JNS Lighting sidebar launcher deploy with validation."""
import base64,json,pathlib,re,subprocess,sys,time,urllib.request
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
folder=pathlib.Path('gateway/lux_manual_override')
def guest(args,limit=270):
 r=json.loads(ssh_host('nodea',['qm','guest','exec','902','--',*args]))
 pid=r.get('pid');stop=time.monotonic()+limit
 while not r.get('exited'):
  if not isinstance(pid,int):raise RuntimeError('No initial PID, status unknown')
  if time.monotonic()>stop:raise RuntimeError('Long-running guest PID '+str(pid)+'; stop, do not repeat')
  time.sleep(3);r=json.loads(ssh_host('nodea',['qm','guest','exec-status','902',str(pid)]))
 return r
def ha(*command):
 r=guest(['ha',*command],limit=290)
 print('JNS_PRIMARY_HA_RESULT '+json.dumps({'command':' '.join(command),
    'exitcode':r.get('exitcode'),'stdout':(r.get('out-data') or '')[-400:]}),flush=True)
 return r.get('exitcode')==0
def runner(mode):
 r=subprocess.run([sys.executable,str(folder/'primary_runner.py'),mode],
           capture_output=True,text=True,timeout=165)
 print('JNS_PRIMARY_LAUNCHER '+mode+' '+r.stdout[-4000:],flush=True)
 if r.returncode:raise RuntimeError('Primary launcher runner '+mode+' failed')
 if mode=='--apply':
  m=re.search(r'JNS_PRIMARY_LUX_APPLIED (\{.+\})',r.stdout)
  if not m:raise RuntimeError('Primary apply manifest missing')
  return json.loads(m.group(1))
 return None
def rollback(info):
 script=(folder/'rollback_vm902.py').read_bytes()
 arg="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(script).decode())+"),'<primary-lux-rollback>','exec'))"
 r=guest(['docker','exec','homeassistant','python3','-c',arg,info['backup'],
          info['configuration_sha'],info['dashboard_sha']],90)
 print('JNS_PRIMARY_ROLLBACK '+(r.get('out-data') or '')[-300:],flush=True)
 if r.get('exitcode')!=0:raise RuntimeError('Rollback blocked')
def main():
 print('JNS_PRIMARY_LUX_START',flush=True)
 runner('--dry-run')
 record=runner('--apply')
 print('JNS_PRIMARY_LUX_BACKUP '+record['backup'],flush=True)
 try:valid=ha('core','check')
 except Exception as e:
  print('JNS_PRIMARY_CHECK_UNCONFIRMED '+str(e)[:140],flush=True)
  try:rollback(record)
  except Exception as r:print('JNS_PRIMARY_ROLLBACK_UNCONFIRMED '+str(r)[:140],flush=True)
  raise
 if not valid:
  rollback(record)
  raise RuntimeError('Primary configuration invalid and restored')
 print('JNS_PRIMARY_LUX_CONFIG_VALID',flush=True)
 # Do not retry Core restart if execution status becomes uncertain.
 if not ha('core','restart'):raise RuntimeError('Primary core restart failed or unknown')
 print('JNS_PRIMARY_LUX_RESTART_COMPLETE',flush=True)
 if not ha('core','info'):raise RuntimeError('Primary core info not ready')
 print('JNS_PRIMARY_LUX_DEPLOY_COMPLETE',flush=True)
try:main()
except Exception as e:
 print('JNS_PRIMARY_LUX_BLOCKED '+type(e).__name__+': '+str(e)[:200],flush=True)
 raise SystemExit(2)
