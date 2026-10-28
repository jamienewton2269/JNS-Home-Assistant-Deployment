#!/usr/bin/env python3
"""JNS guarded Lux per-light priority ladder deployment, Node C -> Node B -> VM905.
Never silently retry a guest operation. Back up and rollback config if HA check fails.
"""
import base64,json,os,pathlib,re,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
ROOT=pathlib.Path('gateway/lux_priority')
def guest(args,seconds=85):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 until=time.monotonic()+seconds
 while not r.get('exited'):
  if not isinstance(r.get('pid'),int):raise RuntimeError('Guest agent returned no PID; do not retry')
  if time.monotonic()>until:raise RuntimeError('QGA operation running: '+str(r['pid'])+'; no blind retry')
  time.sleep(2)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 return r
def py(source,args=(),seconds=75):
 b64=base64.b64encode(source.encode()).decode()
 code="exec(compile(__import__('base64').b64decode("+repr(b64)+"),'<jns-lux-ladder>','exec'))"
 return guest(['docker','exec','homeassistant','python3','-c',code,*args],seconds)
def patch(flag):
 pkg=base64.b64encode((ROOT/'jns_lux_priority_ladder.yaml').read_bytes()).decode()
 r=py((ROOT/'patch_vm905.py').read_text(),[pkg,flag],seconds=135)
 out=r.get('out-data') or ''
 print('JNS_LUX_LADDER_PATCH_'+flag.replace('-',''),out[-2500:],flush=True)
 if r.get('exitcode')!=0:raise RuntimeError('Scoped Lux patch blocked '+(r.get('err-data') or '')[-350:])
 mark='JNS_LUX_LADDER_APPLIED' if flag=='--apply' else 'JNS_LUX_LADDER_PLAN'
 m=re.search(r'(?m)^'+mark+r' (\{[^\n]+\})',out)
 if not m:raise RuntimeError('No patch attestation: '+mark)
 return json.loads(m.group(1))
RESTORE=r'''
import json,sys,hashlib,os,stat,tempfile
from pathlib import Path
root=Path('/config')
backup=Path(sys.argv[1])
m=json.loads(sys.argv[2])
assert backup.parent==root/'.jns-backups' and backup.name.startswith('lux-priority-ladder-')
files=['/config/automations.yaml','/config/dashboards/testing.yaml',
'/config/packages/jns_lux_manual_off_v1.yaml','/config/packages/jns_lux_priority_ladder.yaml']
for p in files:
 item=m.get(p)
 assert item and isinstance(item,dict)
 current=Path(p)
 assert not current.is_symlink() and current.is_file()
 assert hashlib.sha256(current.read_bytes()).hexdigest()==item['after_sha256'], 'Concurrent modification: '+p
for p in files:
 item=m[p];current=Path(p)
 if item['before_sha256'] is None:
  current.unlink()
  continue
 old=(backup/current.name).read_bytes()
 assert hashlib.sha256(old).hexdigest()==item['before_sha256'],'Backup changed '+p
 st=current.stat()
 fd,tmp=tempfile.mkstemp(prefix='.jns-lux-priority-restore-',dir=str(current.parent))
 try:
  with os.fdopen(fd,'wb') as f:f.write(old);f.flush();os.fsync(f.fileno())
  os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode));os.replace(tmp,current)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
assert not Path(files[-1]).exists()
print('JNS_LUX_LADDER_ROLLBACK_VERIFIED',flush=True)
'''
def rollback(m):
 r=py(RESTORE,[m['backup'],json.dumps(m['files'])],seconds=85)
 out=r.get('out-data') or ''
 print('JNS_LUX_LADDER_ROLLBACK',out[-750:],flush=True)
 if r.get('exitcode')!=0 or 'JNS_LUX_LADDER_ROLLBACK_VERIFIED' not in out:
  raise RuntimeError('Rollback could not be verified: '+(r.get('err-data') or '')[-200:])
def started():
 r=guest(['docker','inspect','--format','{{.State.Running}} {{.State.StartedAt}}','homeassistant'],seconds=28)
 if r.get('exitcode')!=0:raise RuntimeError('Core container state unavailable')
 return (r.get('out-data') or '').strip()
def background(kind,command,limit):
 assert (kind,command) in (('check','ha core check'),('restart','ha core restart'))
 rid=os.environ.get('GITHUB_RUN_ID','')
 if not rid.isdecimal():raise RuntimeError('Run identity not available')
 prefix='/tmp/jns-lux-ladder-'+kind+'-'+rid
 done=prefix+'.rc'
 shell=('if test -e '+done+'; then exit 7; fi; '
       '(timeout -s TERM '+str(limit)+' '+command+' > '+prefix+'.log 2>&1; echo $? > '+done+') '
       '</dev/null >/dev/null 2>&1 & echo JNS_LUX_LADDER_BG_STARTED')
 r=guest(['sh','-c',shell],seconds=30)
 if r.get('exitcode')!=0 or 'JNS_LUX_LADDER_BG_STARTED' not in (r.get('out-data') or ''):
  raise RuntimeError('HA '+kind+' launch was not confirmed')
 print('JNS_LUX_LADDER_HA_BG_STARTED',kind,flush=True)
 return done
def await_check(path,seconds=290):
 until=time.monotonic()+seconds
 while time.monotonic()<until:
  time.sleep(7)
  r=guest(['sh','-c','if test -f '+path+'; then cat '+path+'; else echo PENDING; fi'],seconds=28)
  if r.get('exitcode')!=0:raise RuntimeError('Check result unreadable')
  state=(r.get('out-data') or '').strip()
  if state=='PENDING':continue
  if not state.isdecimal():raise RuntimeError('Bad core check marker: '+state[:90])
  print('JNS_LUX_LADDER_HA_CHECK_EXIT',state,flush=True)
  return int(state)==0
 raise RuntimeError('HA Core check incomplete; leave file state for inspection')
VERIFY=r'''
import pathlib,json,yaml,hashlib,urllib.request,urllib.error
r=pathlib.Path('/config')
p=r/'packages/jns_lux_priority_ladder.yaml'
a=yaml.safe_load((r/'automations.yaml').read_text())
controller=[x for x in a if str(x.get('id'))=='1791918795028']
assert len(controller)==1
assert 'JNS_LUX_PRIORITY_LADDER_V1' in controller[0]['description']
assert any(x.get('entity_id')=='input_boolean.jns_lux_ladder_initialized' for x in controller[0]['conditions'])
d=yaml.safe_load((r/'dashboards/testing.yaml').read_text())
assert any(v.get('path')=='lux-priorities' for v in d['views'])
registry=json.loads((r/'.storage/core.entity_registry').read_text())['data']['entities']
entities={e.get('entity_id'):e for e in registry}
required=['input_boolean.jns_lux_ladder_initialized','input_number.jns_lux_ladder_stage_gap',
'input_boolean.jns_lux_include_hall','input_boolean.jns_lux_include_front',
'input_number.jns_lux_rank_hall','input_number.jns_lux_rank_front',
'binary_sensor.jns_lux_priority_bright_stable']
registrations={e:(e in entities and not entities[e].get('disabled_by')) for e in required}
bootstrap=[e for e in registry if e.get('unique_id')=='jns_lux_ladder_bootstrap_v1' and not e.get('disabled_by')]
try:
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:80/api/',timeout=5) as resp:
  http=resp.status
except urllib.error.HTTPError as e:http=e.code
except Exception as e:http=type(e).__name__
result={'core_http':http,'config_sha':hashlib.sha256(p.read_bytes()).hexdigest(),
        'registered':registrations,'bootstrap_registered':bool(bootstrap),
        'controller_loaded':True,'dashboard_loaded':True}
print('JNS_LUX_LADDER_LIVE_VERIFY '+json.dumps(result,sort_keys=True))
assert http in (200,401),'Core API unavailable'
assert all(registrations.values()),'New helpers not all registered'
assert bootstrap,'Bootstrap automation not registered'
'''
def main():
 print('JNS_LUX_LADDER_DEPLOY_BEGIN',flush=True)
 if 'running' not in ssh_host('nodeb',['qm','status','905']):raise RuntimeError('Target VM905 not running')
 before=started()
 print('JNS_LUX_LADDER_CORE_BEFORE',before,flush=True)
 patch('--dry-run')
 manifest=patch('--apply')
 print('JNS_LUX_LADDER_BACKUP',manifest['backup'],flush=True)
 try:
  done=background('check','ha core check',250)
  if not await_check(done):raise RuntimeError('HA Core configuration validation failed')
 except BaseException:
  try:rollback(manifest)
  except Exception as e:print('JNS_LUX_LADDER_ROLLBACK_REVIEW',type(e).__name__,str(e)[:230],flush=True)
  raise
 print('JNS_LUX_LADDER_CONFIG_VALIDATED',flush=True)
 background('restart','ha core restart',140)
 for n in range(28):
  time.sleep(7)
  try:
   current=started()
   if current.startswith('true ') and current!=before:
    print('JNS_LUX_LADDER_CORE_RESTART_OBSERVED',current,flush=True)
    break
  except Exception as e:print('JNS_LUX_LADDER_CORE_OBSERVATION',n+1,type(e).__name__,flush=True)
 else:raise RuntimeError('Core restart not confirmed; no second restart')
 for n in range(18):
  time.sleep(6)
  try:
   r=py(VERIFY,seconds=50)
   out=r.get('out-data') or ''
   if 'JNS_LUX_LADDER_LIVE_VERIFY' in out:print(out[-1250:],flush=True)
   if r.get('exitcode')==0 and 'JNS_LUX_LADDER_LIVE_VERIFY' in out:
    print('JNS_LUX_LADDER_DEPLOY_VERIFIED',flush=True)
    return
  except Exception as e:print('JNS_LUX_LADDER_POSTCHECK_RETRY',n+1,type(e).__name__,flush=True)
 raise RuntimeError('Core started but helper registrations not confirmed; inspect, no blind restart')
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_LUX_LADDER_DEPLOY_BLOCKED '+type(e).__name__+': '+str(e)[:310],flush=True)
  sys.exit(2)
