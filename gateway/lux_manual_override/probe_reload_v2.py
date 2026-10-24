#!/usr/bin/env python3
"""Read-only discovery of authorised HAOS automation reload access; no secrets printed."""
import base64,json,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
def qga(args):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 pid=r.get('pid')
 for _ in range(35):
  if r.get('exited'):break
  if not isinstance(pid,int):raise RuntimeError('QGA missing PID')
  time.sleep(1);r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 return r
r=qga(['ha','--help'])
print('HA_CLI_HELP',str(r.get('out-data') or '')[:4500],flush=True)
CODE=r"""
import os,urllib.request,urllib.error
tok=os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
print('SUPERVISOR_TOKEN_EXISTS',bool(tok))
for url in ('http://supervisor/core/api/','http://supervisor/core/api/config',
            'http://supervisor/core/api/states/automation.jns_lux_remember_manual_off_until_sunrise',
            'http://127.0.0.1:8123/api/'):
 try:
  req=urllib.request.Request(url,headers={'Authorization':'Bearer '+tok} if tok else {})
  with urllib.request.urlopen(req,timeout=6) as res:
   print('RELOAD_PROBE',url,'STATUS',res.status,'CONTENT_TYPE',res.headers.get('Content-Type'))
 except urllib.error.HTTPError as exc:
  print('RELOAD_PROBE',url,'HTTP',exc.code)
 except Exception as exc:
  print('RELOAD_PROBE',url,'ERROR',type(exc).__name__)
"""
src="exec(__import__('base64').b64decode("+repr(base64.b64encode(CODE.encode()).decode())+"))"
r=qga(['docker','exec','homeassistant','python3','-c',src])
print('HA_CORE_API_PROBE',(r.get('out-data') or '')[-3000:],'EXIT',r.get('exitcode'),flush=True)
