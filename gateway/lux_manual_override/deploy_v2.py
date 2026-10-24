#!/usr/bin/env python3
"""Guarded JNS VM905 Lux V2 deploy: backup, core check, quick automation reload, verify.
NO Core restart. If reload unavailable, abort before writing.
"""
import base64,json,pathlib,re,subprocess,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
HERE=pathlib.Path('gateway/lux_manual_override')
def qga(args, timeout=240):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 pid=r.get('pid');until=time.monotonic()+timeout
 while not r.get('exited'):
  if not isinstance(pid,int):raise RuntimeError('QGA PID absent; no retry')
  if time.monotonic()>until:raise RuntimeError('QGA PID '+str(pid)+' incomplete; no retry')
  time.sleep(3)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 return r
def core_py(script, timeout=60):
 payload=base64.b64encode(script.encode()).decode()
 source="exec(__import__('base64').b64decode("+repr(payload)+"))"
 return qga(['docker','exec','homeassistant','python3','-c',source],timeout)
CHECK= """
import os,urllib.request,sys
t=os.getenv('SUPERVISOR_TOKEN') or os.getenv('HASSIO_TOKEN')
if not t:
 print('JNS_RELOAD_BLOCKED_NO_SUPERVISOR_TOKEN')
 sys.exit(4)
for url in ('http://supervisor/core/api/','http://supervisor/core/api/config'):
 try:
  req=urllib.request.Request(url,headers={'Authorization':'Bearer '+t})
  with urllib.request.urlopen(req,timeout=8) as r:
   print('JNS_RELOAD_HTTP_PREFLIGHT',r.status,url.rsplit('/',1)[-1])
   if r.status==200:break
 except Exception as exc:
  print('JNS_RELOAD_ENDPOINT_BLOCKED',type(exc).__name__)
else:sys.exit(4)
print('JNS_RELOAD_CAPABLE')
"""
RELOAD="""
import os,json,urllib.request,sys
t=os.getenv('SUPERVISOR_TOKEN') or os.getenv('HASSIO_TOKEN')
if not t:sys.exit(4)
req=urllib.request.Request('http://supervisor/core/api/services/automation/reload',
  data=b'{}',method='POST',
  headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=50) as r:
 print('JNS_LUX_AUTOMATION_RELOAD_HTTP',r.status)
 assert r.status in (200,201)
"""
VERIFY="""
import os,urllib.request,json,sys
t=os.getenv('SUPERVISOR_TOKEN') or os.getenv('HASSIO_TOKEN')
if not t:sys.exit(4)
for eid in ('automation.jns_lux_remember_manual_off_until_sunrise',
            'automation.general_shared_lux_progressive_control'):
 req=urllib.request.Request('http://supervisor/core/api/states/'+eid,
  headers={'Authorization':'Bearer '+t})
 with urllib.request.urlopen(req,timeout=10) as r:
  item=json.load(r)
  print('JNS_LUX_V2_LIVE_ENTITY',item.get('entity_id'),item.get('state'))
  assert item.get('state') in ('on','off')
"""
def runner(flag):
 cmd=[sys.executable,str(HERE/'runner_v2.py'),flag]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=170)
 print('JNS_LUX_V2_'+flag.replace('-','').upper()+' '+p.stdout[-6500:],flush=True)
 if p.returncode:raise RuntimeError('Guarded '+flag+' rejected: '+p.stderr[-350:])
 if flag=='--apply':
  m=re.search(r'JNS_LUX_V2_APPLIED (\{.+\})',p.stdout)
  if not m:raise RuntimeError('Missing verified apply manifest')
  return json.loads(m.group(1))
def restore(manifest):
 source=(HERE/'rollback_v2_vm905.py').read_bytes()
 encoded=base64.b64encode(source).decode()
 code="exec(compile(__import__('base64').b64decode("+repr(encoded)+"),'<jns-lux-v2-rollback>','exec'))"
 r=qga(['docker','exec','homeassistant','python3','-c',code,manifest['backup'],
        json.dumps(manifest['after_hashes'])],110)
 print('JNS_LUX_V2_ROLLBACK '+(r.get('out-data') or '')[-2000:],flush=True)
 if r.get('exitcode')!=0:raise RuntimeError('Rollback not confirmed '+(r.get('err-data') or '')[-250:])
def main():
 print('JNS_LUX_V2_BEGIN',flush=True)
 # Fail before ANY HA file write if authenticated no-restart automation reload is unavailable.
 test=core_py(CHECK)
 print('JNS_LUX_V2_RELOAD_PROBE '+(test.get('out-data') or '')[-900:],flush=True)
 if test.get('exitcode')!=0 or 'JNS_RELOAD_CAPABLE' not in (test.get('out-data') or ''):
  raise RuntimeError('Safe no-restart reload unavailable. No config files modified.')
 runner('--dry-run')
 record=runner('--apply')
 print('JNS_LUX_V2_BACKUP_VERIFIED '+record['backup'],flush=True)
 try:
  test=qga(['ha','core','check'],timeout=285)
  print('JNS_LUX_V2_CORE_CHECK '+json.dumps({'code':test.get('exitcode'),
     'out':(test.get('out-data') or '')[-500:],'error':(test.get('err-data') or '')[-400:]}),flush=True)
  if test.get('exitcode')!=0:raise RuntimeError('HA Core configuration check rejected V2')
  test=core_py(RELOAD,timeout=90)
  print('JNS_LUX_V2_RELOAD_RESULT '+(test.get('out-data') or '')[-600:],flush=True)
  if test.get('exitcode')!=0 or 'JNS_LUX_AUTOMATION_RELOAD_HTTP' not in (test.get('out-data') or ''):
   raise RuntimeError('Automation reload failed')
  test=core_py(VERIFY,timeout=90)
  print('JNS_LUX_V2_VERIFY '+(test.get('out-data') or '')[-1500:],flush=True)
  if test.get('exitcode')!=0:raise RuntimeError('Runtime automation entity verification failed')
 except BaseException:
  try:
   restore(record)
   c=core_py(RELOAD,timeout=90)
   print('JNS_LUX_V2_RESTORED_RELOAD '+(c.get('out-data') or '')[-500:],flush=True)
  except Exception as err:print('JNS_LUX_V2_RESTORE_REQUIRES_ATTENTION '+str(err)[:250],flush=True)
  raise
 print('JNS_LUX_V2_DEPLOY_SUCCESS_NO_CORE_RESTART',flush=True)
try:main()
except Exception as ex:
 print('JNS_LUX_V2_DEPLOY_BLOCKED '+type(ex).__name__+': '+str(ex)[:250],flush=True)
 sys.exit(2)
