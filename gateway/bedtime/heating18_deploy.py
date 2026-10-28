#!/usr/bin/env python3
"""JNS protected deployment: HA-General bedtime trigger sets Lyric target to 18C.
Node C -> Node B -> VM905. Roll back on config check failure; never run bedtime or alter thermostat now.
"""
import base64,json,os,pathlib,re,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
ROOT=pathlib.Path('gateway/bedtime')
PATCH=ROOT/'heating18_patch_vm905.py'
def guest(args,timeout=75):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 end=time.monotonic()+timeout
 while not r.get('exited'):
  pid=r.get('pid')
  if not isinstance(pid,int):raise RuntimeError('QGA command status missing; no blind retry')
  if time.monotonic()>end:raise RuntimeError('QGA PID '+str(pid)+' running; no retry')
  time.sleep(2)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 return r
def core(code,args=(),timeout=70):
 encoded=base64.b64encode(code.encode()).decode()
 cmd="exec(compile(__import__('base64').b64decode("+repr(encoded)+"),'<jns-heat18>','exec'))"
 return guest(['docker','exec','homeassistant','python3','-c',cmd,*args],timeout)
def run_patch(flag):
 r=core(PATCH.read_text(),[flag])
 out=r.get('out-data') or ''
 print('JNS_HEAT18_PATCH_'+flag.replace('-',''),out[-1900:],flush=True)
 if r.get('exitcode')!=0:raise RuntimeError('HA905 bedtime patch '+flag+' failed; '+(r.get('err-data') or '')[-180:])
 tag='JNS_BEDTIME_HEAT18_APPLIED' if flag=='--apply' else 'JNS_BEDTIME_HEAT18_PLAN'
 m=re.search(r'(?m)^'+tag+r' (\{[^\n]+\})',out)
 if not m:raise RuntimeError('Missing confirmed '+tag)
 return json.loads(m.group(1))
RESTORE=r'''
from pathlib import Path
import hashlib,os,stat,tempfile,sys
p=Path('/config/packages/jns_bedtime_controller.yaml')
b=Path(sys.argv[1])
after=sys.argv[2]; before=sys.argv[3]
assert b.name==p.name and b.parent.parent==Path('/config/.jns-backups') and b.parent.name.startswith('bedtime-heating18-')
assert not p.is_symlink() and not b.is_symlink()
current=p.read_bytes();old=b.read_bytes()
assert hashlib.sha256(current).hexdigest()==after,'Concurrent edit; rollback blocked'
assert hashlib.sha256(old).hexdigest()==before,'Backup changed; rollback blocked'
s=p.stat()
fd,tmp=tempfile.mkstemp(prefix='.jns-heat18-restore-',dir=str(p.parent))
try:
 with os.fdopen(fd,'wb') as f:
  f.write(old);f.flush();os.fsync(f.fileno())
 os.chown(tmp,s.st_uid,s.st_gid);os.chmod(tmp,stat.S_IMODE(s.st_mode));os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
print('JNS_HEAT18_BACKUP_RESTORED',hashlib.sha256(p.read_bytes()).hexdigest())
'''
def rollback(m):
 r=core(RESTORE,[m['backup'],m['after_sha256'],m['before_sha256']])
 print('JNS_HEAT18_ROLLBACK',(r.get('out-data') or '')[-300:],flush=True)
 if r.get('exitcode')!=0:raise RuntimeError('Rollback not confirmed: '+(r.get('err-data') or '')[-180:])
def started():
 r=guest(['docker','inspect','--format','{{.State.StartedAt}}','homeassistant'],timeout=25)
 if r.get('exitcode')!=0:raise RuntimeError('Core container start time not available')
 return (r.get('out-data') or '').strip()
def detached(label,command,limit):
 assert (label,command) in (('check','ha core check'),('restart','ha core restart'))
 runid=os.environ.get('GITHUB_RUN_ID','')
 if not runid.isdecimal():raise RuntimeError('Missing workflow run identity')
 prefix='/tmp/jns-heating18-'+label+'-'+runid
 done=prefix+'.rc';out=prefix+'.log'
 # BusyBox timeout accepts -s TERM but not --signal=TERM.
 shell='if test -e '+done+'; then exit 7; fi; (timeout -s TERM '+str(limit)+' '+command+' > '+out+' 2>&1; echo $? > '+done+') </dev/null >/dev/null 2>&1 & echo JNS_HEAT18_BG_STARTED'
 r=guest(['sh','-c',shell],timeout=30)
 if r.get('exitcode')!=0 or 'JNS_HEAT18_BG_STARTED' not in (r.get('out-data') or ''):raise RuntimeError(label+' start not confirmed')
 print('JNS_HEAT18_BG_STARTED',label,flush=True)
 return done
def poll_done(done,timeout=290):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  time.sleep(7)
  r=guest(['sh','-c','if test -f '+done+'; then cat '+done+'; else echo PENDING; fi'],timeout=24)
  if r.get('exitcode')!=0:raise RuntimeError('Cannot inspect Core config check')
  result=(r.get('out-data') or '').strip()
  if result=='PENDING':continue
  if result.isdecimal():
   print('JNS_HEAT18_CHECK_EXIT',result,flush=True)
   return int(result)==0
  raise RuntimeError('Unrecognised config-check marker')
 raise RuntimeError('Core config check still running or unknown; manual inspection needed')
VERIFY=r'''
import json,pathlib,yaml,hashlib
p=pathlib.Path('/config/packages/jns_bedtime_controller.yaml')
data=yaml.safe_load(p.read_text())
a=[x for x in data['automation'] if x.get('id')=='jns_bedtime_trigger_on_mode']
assert len(a)==1
seq=a[0]['actions']
assert seq[0]=={'action':'climate.set_temperature','target':{'entity_id':'climate.thermostat_thermostat'},'data':{'temperature':18},'continue_on_error':True}
assert seq[1]=={'action':'script.jns_bedtime_shutdown'}
registry=json.loads(pathlib.Path('/config/.storage/core.entity_registry').read_text())['data']['entities']
assert any(x.get('platform')=='automation' and not x.get('disabled_by') and (x.get('unique_id')=='jns_bedtime_trigger_on_mode' or x.get('entity_id')=='automation.jns_bedtime_dashboard_or_hallway_activation') for x in registry)
print('JNS_HEAT18_POST_RESTART_VERIFIED',json.dumps({'thermostat_target':18,'bedtime_automation_present':True,'script_preserved':True,'file_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
'''
HTTP=r'''
import urllib.request,urllib.error
try:
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8123/api/',timeout=7) as r: print('HA_HTTP',r.status)
except urllib.error.HTTPError as e: print('HA_HTTP',e.code)
except Exception as e: print('HA_HTTP_ERROR',type(e).__name__)
'''
def main():
 print('JNS_HEAT18_DEPLOY_START',flush=True)
 if 'running' not in ssh_host('nodeb',['qm','status','905']):raise RuntimeError('HA905 not running; refusing modification')
 before=started()
 print('JNS_HEAT18_CORE_STARTED_BEFORE',before,flush=True)
 run_patch('--dry-run')
 m=run_patch('--apply')
 print('JNS_HEAT18_BACKUP',m['backup'],flush=True)
 try:
  done=detached('check','ha core check',245)
  if not poll_done(done,290):raise RuntimeError('HA Core configuration check rejected bedtime heating change')
 except BaseException:
  try:rollback(m)
  except Exception as e:print('JNS_HEAT18_ROLLBACK_BLOCKED',type(e).__name__,str(e)[:180],flush=True)
  raise
 print('JNS_HEAT18_CONFIG_VALIDATED',flush=True)
 # HA Core API reload is not authorised: restart only once, then verify actual container start.
 done=detached('restart','ha core restart',120)
 print('JNS_HEAT18_RESTART_REQUESTED',flush=True)
 changed=False
 for attempt in range(22):
  time.sleep(7)
  try:
   current=started()
   if current!=before and current:
    print('JNS_HEAT18_CORE_RESTART_OBSERVED',current,flush=True)
    changed=True
    break
  except Exception as e: print('JNS_HEAT18_RESTART_OBSERVATION',attempt+1,type(e).__name__,flush=True)
 if not changed:raise RuntimeError('Core restart not observed; do NOT blindly retry; configuration remains validated on disk')
 # Test the Core's HTTP endpoint; an unauthenticated 401 is expected, and verifies it has started.
 online=False
 for attempt in range(13):
  try:
   r=core(HTTP,timeout=35)
   out=(r.get('out-data') or '')
   if r.get('exitcode')==0 and ('HA_HTTP 401' in out or 'HA_HTTP 200' in out):
    print('JNS_HEAT18_CORE_HTTP_READY',out.strip(),flush=True)
    online=True
    break
  except Exception as e:print('JNS_HEAT18_HTTP_PROBE',attempt+1,type(e).__name__,flush=True)
  time.sleep(6)
 if not online:raise RuntimeError('Core restarted, but HTTP availability not confirmed')
 r=core(VERIFY,timeout=45)
 print('JNS_HEAT18_AFTER_RESTART',(r.get('out-data') or '')[-1800:],flush=True)
 if r.get('exitcode')!=0 or 'JNS_HEAT18_POST_RESTART_VERIFIED' not in (r.get('out-data') or ''):
  raise RuntimeError('Post-restart bedtime entity verification failed')
 print('JNS_HEAT18_DEPLOY_SUCCESS',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_HEAT18_DEPLOY_FAILED',type(e).__name__,str(e)[:350],flush=True)
  sys.exit(2)
