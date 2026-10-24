#!/usr/bin/env python3
"""Read-only JNS Steward audit of HA905 localhost API and native steward binding.
No bearer token is used or printed.
"""
import base64,json,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
CODE=r"""
import urllib.request,urllib.error
for port in (80,8123):
 u=f'http://127.0.0.1:{port}/api/'
 try:
  with urllib.request.urlopen(u,timeout=6) as r:
   print('HA_CORE_LOOPBACK',port,'STATUS',r.status)
 except urllib.error.HTTPError as e:
  print('HA_CORE_LOOPBACK',port,'STATUS',e.code)
 except Exception as e:
  print('HA_CORE_LOOPBACK',port,'ERROR',type(e).__name__)
"""
def one(cmd):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*cmd]))
 pid=r.get('pid')
 for _ in range(40):
  if r.get('exited'): break
  if not isinstance(pid,int): raise RuntimeError('QGA missing PID')
  time.sleep(1)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 if not r.get('exited'):raise RuntimeError('QGA timeout')
 if r.get('exitcode')!=0:raise RuntimeError('Read-only guest probe nonzero')
 return r.get('out-data') or ''
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(CODE.encode()).decode())+"))"
print(one(['docker','exec','homeassistant','python3','-c',code]),flush=True)
# Host-side binding is checked independently so a service's active status is not taken as HTTP health.
raw=ssh_host('nodeb',['sh','-c',"systemctl show natural-automation.service -p ExecStart --value | cut -c 1-350; ss -ltn | grep -E ':(8099|8123|80) ' || true; systemctl show natural-automation.service -p EnvironmentFiles --value | cut -c 1-200"])
print('HOST_STEWARD_BINDING',raw[:1200],flush=True)
