#!/usr/bin/env python3
"""Guarded JNS Home Assistant General predictive 10AM comfort and bedtime learning deploy.
Backup both files; fail-closed alarm logic; no security automation or heating script changes.
"""
import base64,json,os,pathlib,re,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
DIR=pathlib.Path('gateway/heating_presence')
def qga(args,seconds=75):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 deadline=time.monotonic()+seconds
 while not r.get('exited'):
  if not isinstance(r.get('pid'),int):
   raise RuntimeError('Guest command status ambiguous, no blind retries')
  if time.monotonic()>=deadline:
   raise RuntimeError('Guest PID '+str(r['pid'])+' still active; manual inspection')
  time.sleep(2)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 return r
def core(src,args=(),seconds=95):
 encoded=base64.b64encode(src.encode()).decode()
 command="exec(compile(__import__('base64').b64decode("+repr(encoded)+"),'<jns-heating-presence>','exec'))"
 return qga(['docker','exec','homeassistant','python3','-c',command,*args],seconds)
def stage(flag):
 pkg=base64.b64encode((DIR/'jns_predictive_schedule.yaml').read_bytes()).decode()
 source=(DIR/'patch_vm905.py').read_text()
 result=core(source,[pkg,flag],seconds=135)
 out=result.get('out-data') or ''
 print('JNS_HEATING_STAGE_'+flag.replace('-',''),out[-2400:],flush=True)
 if result.get('exitcode')!=0:raise RuntimeError('Heating schedule '+flag+' blocked: '+(result.get('err-data') or '')[-250:])
 tag='JNS_HEATING_PRESENCE_APPLIED' if flag=='--apply' else 'JNS_HEATING_PRESENCE_PLAN'
 m=re.search(r'(?m)^'+tag+r' (\{[^\n]+\})',out)
 if not m:raise RuntimeError('Missing verified deployment report '+tag)
 return json.loads(m.group(1))
RESTORE=r"""
from pathlib import Path
import hashlib,os,stat,tempfile,sys
root=Path('/config')
p=root/'packages/jns_heating_predictive_schedule.yaml'
d=root/'dashboards/testing.yaml'
b=Path(sys.argv[1]);pkgsha=sys.argv[2];dashsha=sys.argv[3];oldsha=sys.argv[4]
assert b.name=='testing.yaml' and b.parent.parent==root/'.jns-backups'
assert b.parent.name.startswith('heating-presence-')
assert not b.is_symlink() and not d.is_symlink() and not p.is_symlink()
assert hashlib.sha256(p.read_bytes()).hexdigest()==pkgsha,'Package changed concurrently'
assert hashlib.sha256(d.read_bytes()).hexdigest()==dashsha,'Dashboard changed concurrently'
old=b.read_bytes()
assert hashlib.sha256(old).hexdigest()==oldsha,'Backup checksum mismatch'
st=d.stat();fd,tmp=tempfile.mkstemp(prefix='.jns-heating-rollback-',dir=str(d.parent))
try:
 with os.fdopen(fd,'wb') as f:
  f.write(old);f.flush();os.fsync(f.fileno())
 os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode));os.replace(tmp,d)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
p.unlink()
assert d.read_bytes()==old and not p.exists(),'Rollback verification failed'
print('JNS_HEATING_PRESENCE_ROLLBACK_VERIFIED')
"""
def rollback(m):
 r=core(RESTORE,[m['backup'],m['package_sha'],m['dashboard_after'],m['dashboard_before']],seconds=95)
 print('JNS_HEATING_ROLLBACK',(r.get('out-data') or '')[-400:],flush=True)
 if r.get('exitcode')!=0 or 'ROLLBACK_VERIFIED' not in (r.get('out-data') or ''):
  raise RuntimeError('Rollback verification blocked; check files')
def docker_started():
 r=qga(['docker','inspect','--format','{{.State.Running}} {{.State.StartedAt}}','homeassistant'],seconds=25)
 if r.get('exitcode')!=0:raise RuntimeError('HA Core container status not available')
 return (r.get('out-data') or '').strip()
def start_ha_command(name,args,limit):
 assert (name,args) in (('check','ha core check'),('restart','ha core restart'))
 runid=os.environ.get('GITHUB_RUN_ID','')
 if not runid.isdecimal():raise RuntimeError('Invalid GitHub run identity')
 marker='/tmp/jns-heatpresence-'+name+'-'+runid
 shell=('if test -e '+marker+'.rc; then exit 7; fi; '
        '(timeout -s TERM '+str(limit)+' '+args+' > '+marker+'.out 2>&1; echo $? > '+marker+'.rc) '
        '</dev/null >/dev/null 2>&1 & echo JNS_HEAT_PRESENCE_COMMAND_STARTED')
 r=qga(['sh','-c',shell],seconds=30)
 if r.get('exitcode')!=0 or 'JNS_HEAT_PRESENCE_COMMAND_STARTED' not in (r.get('out-data') or ''):
  raise RuntimeError('HA Core '+name+' command start not confirmed')
 print('JNS_HEATING_HA_COMMAND_STARTED',name,flush=True)
 return marker+'.rc'
def await_check(marker):
 deadline=time.monotonic()+295
 while time.monotonic()<deadline:
  time.sleep(7)
  r=qga(['sh','-c','if test -f '+marker+'; then cat '+marker+'; else echo PENDING; fi'],seconds=28)
  if r.get('exitcode')!=0:raise RuntimeError('HA config check exit marker unreadable')
  status=(r.get('out-data') or '').strip()
  if status=='PENDING':continue
  if not status.isdecimal():raise RuntimeError('Unexpected HA config check result')
  print('JNS_HEATING_CONFIG_CHECK_EXIT',status,flush=True)
  return int(status)==0
 raise RuntimeError('HA config validation unconfirmed before timeout')
VERIFY=r"""
import json,pathlib,yaml,hashlib,urllib.request,urllib.error
R=pathlib.Path('/config')
p=R/'packages/jns_heating_predictive_schedule.yaml'
u=R/'dashboards/testing.yaml'
d=yaml.safe_load(p.read_text())
v=yaml.safe_load(u.read_text())['views']
assert [x['id'] for x in d['automation']]==['jns_heating_learn_bedtime_v1','jns_heating_alarm_predictive_target_v1']
assert any(x.get('path')=='controls' and any(c.get('title')=='JNS Heating - Predictive Schedule' for c in x.get('cards',[])) for x in v)
assert any(x.get('path')=='house-temperature' and any(c.get('title')=='JNS Heating - Predictive Schedule and Bedtime Learning' for c in x.get('cards',[])) for x in v)
reg=json.loads((R/'.storage/core.entity_registry').read_text())['data']['entities']
def present(entity):
 return any(x.get('entity_id')==entity and not x.get('disabled_by') for x in reg)
required=['input_boolean.jns_heating_automatic_override','input_number.jns_heating_away_minimum_temp',
          'input_number.jns_heating_bedtime_samples','automation.jns_heating_learn_normal_bedtime_from_actual_activation',
          'automation.jns_heating_predictive_home_10am_and_learned_bedtime_setback']
result={'package_sha':hashlib.sha256(p.read_bytes()).hexdigest(),'dashboard_sha':hashlib.sha256(u.read_bytes()).hexdigest(),
        'helpers_present':{x:present(x) for x in required},'alarm_entities_registered':[x['entity_id'] for x in reg if x.get('entity_id','').startswith('alarm_control_panel.')]}
try:
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:80/api/',timeout=7):result['core_http']='200'
except urllib.error.HTTPError as e:result['core_http']=str(e.code)
except Exception as e:result['core_http']=type(e).__name__
print('JNS_HEAT_PRESENCE_LIVE_VERIFY '+json.dumps(result,sort_keys=True))
assert result['core_http'] in ('200','401'),'Core API is not ready'
assert all(result['helpers_present'].values()),'New helpers/automations not registered'
"""
def main():
 print('JNS_HEATING_PRESENCE_DEPLOY_BEGIN',flush=True)
 if 'running' not in ssh_host('nodeb',['qm','status','905']):raise RuntimeError('VM905 not running')
 oldstart=docker_started()
 print('JNS_HEATING_CORE_BEFORE',oldstart,flush=True)
 stage('--dry-run')
 manifest=stage('--apply')
 print('JNS_HEATING_BACKUP',manifest['backup'],flush=True)
 try:
  check=start_ha_command('check','ha core check',245)
  if not await_check(check):raise RuntimeError('Full HA config check rejected heating package')
 except BaseException:
  try:rollback(manifest)
  except Exception as e:print('JNS_HEATING_ROLLBACK_NEEDS_REVIEW',str(e)[:210],flush=True)
  raise
 print('JNS_HEATING_CONFIG_VALIDATED',flush=True)
 start_ha_command('restart','ha core restart',125)
 for attempt in range(28):
  time.sleep(6)
  try:
   state=docker_started()
   if state.startswith('true ') and state!=oldstart:
    print('JNS_HEATING_CORE_RESTART_CONFIRMED',state,flush=True)
    break
  except Exception as e:print('JNS_HEATING_CORE_POLL_RETRY',attempt+1,type(e).__name__,flush=True)
 else:raise RuntimeError('Core restart not observed; do not repeat blindly')
 for i in range(12):
  time.sleep(5)
  r=core(VERIFY,seconds=60)
  out=r.get('out-data') or ''
  print('JNS_HEATING_RUNTIME_VERIFICATION '+out[-1800:],flush=True)
  if r.get('exitcode')==0 and 'JNS_HEAT_PRESENCE_LIVE_VERIFY' in out:
   print('JNS_HEATING_DEPLOY_COMPLETE',flush=True)
   return
 raise RuntimeError('Core restarted, but new helper registration/HTTP health not confirmed')
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_HEATING_DEPLOY_BLOCKED '+type(e).__name__+': '+str(e)[:300],flush=True)
  sys.exit(2)
