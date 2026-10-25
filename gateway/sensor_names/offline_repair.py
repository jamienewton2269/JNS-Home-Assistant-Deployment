#!/usr/bin/env python3
"""JNS VM905 guarded cold device-registry name repair, no MQTT/ID changes.
Fallback only because no running authorised WS-API app was found.
Stages exact semantic edits while Core is active, stops Core, applies verified
bytes when stopped, starts Core, checks names and preserves entity identifiers.
Never overwrites concurrent registry changes; creates durable rollback backup.
"""
import base64,hashlib,json,shlex,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
TARGETS={
'0xa4c13833916ae7d1':('Soil Moisture Probe 1','AOYAN','Soil moisture sensor'),
'0xa4c1386faf69d5e0':('Soil Moisture Probe 2','AOYAN','Soil moisture sensor'),
'0xa4c138cf0342f0d9':('Soil Moisture Probe 3','AOYAN','Soil moisture sensor'),
'0xa4c1383917c90309':('External Rain Sensor','HOBEIAN','Rainwater detection sensor'),
}
STAGE=r'''
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,copy
T={
'0xa4c13833916ae7d1':('Soil Moisture Probe 1','AOYAN','Soil moisture sensor'),
'0xa4c1386faf69d5e0':('Soil Moisture Probe 2','AOYAN','Soil moisture sensor'),
'0xa4c138cf0342f0d9':('Soil Moisture Probe 3','AOYAN','Soil moisture sensor'),
'0xa4c1383917c90309':('External Rain Sensor','HOBEIAN','Rainwater detection sensor')}
sha=lambda data: hashlib.sha256(data).hexdigest()
p=Path('/config/.storage/core.device_registry')
ep=Path('/config/.storage/core.entity_registry')
orig=p.read_bytes()
obj=json.loads(orig)
entries=obj['data']['devices']
before=[(e['entity_id'],e.get('unique_id'),e.get('device_id')) for e in json.loads(ep.read_text())['data']['entities']]
matched=[]
changes=[]
for ieee,(name,mfg,model) in T.items():
 dlist=[d for d in entries if any(isinstance(z,list) and len(z)>1 and
             z[0]=='mqtt' and z[1].lower()=='zigbee2mqtt_'+ieee
             for z in d.get('identifiers',[]))]
 if len(dlist)!=1:raise RuntimeError('device identity not unique: '+ieee)
 d=dlist[0]
 if d.get('manufacturer')!=mfg or d.get('model')!=model:raise RuntimeError('Device model/manufacturer mismatch: '+ieee)
 if d.get('name_by_user') not in (None,name):raise RuntimeError('Existing user name requires manual review: '+ieee)
 matched.append(d['id'])
 changes.append({'ieee':ieee,'device_id':d['id'],'old':d.get('name_by_user'),'new':name})
copy_obj=copy.deepcopy(obj)
for d in copy_obj['data']['devices']:
 for ch in changes:
  if d.get('id')==ch['device_id']:d['name_by_user']=ch['new']
modified={d['id'] for d in copy_obj['data']['devices'] if d not in entries}
assert set(matched)==modified or (not modified and all(x['old']==x['new'] for x in changes))
new=json.dumps(copy_obj,ensure_ascii=False,indent=2).encode()+b'\n'
assert len(copy_obj['data']['devices'])==len(entries)
assert len(set(matched))==4
assert len(before)>0
folder=Path('/config/.jns-backups/sensor-names')
folder.mkdir(mode=0o700,parents=True,exist_ok=True)
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
original=folder/('device_registry-original-'+stamp+'.json')
staged=folder/('device_registry-staged-'+stamp+'.json')
manifest=folder/('manifest-'+stamp+'.json')
for f in (original,staged,manifest):
 if f.exists():raise RuntimeError('Stage backup name collision')
original.write_bytes(orig)
staged.write_bytes(new)
assert original.read_bytes()==orig and staged.read_bytes()==new
result={'original_host': '/mnt/data/supervisor/homeassistant/.storage/core.device_registry',
 'backup_host':'/mnt/data/supervisor/homeassistant/'+str(original.relative_to('/config')),
 'staged_host':'/mnt/data/supervisor/homeassistant/'+str(staged.relative_to('/config')),
 'old_hash':sha(orig),'new_hash':sha(new),'changes':changes,'entity_count':len(before)}
manifest.write_text(json.dumps(result,indent=2)+'\n')
print('JNS_SENSOR_NAMES_STAGE '+json.dumps(result,sort_keys=True),flush=True)
'''
VERIFY=r'''
import json
from pathlib import Path
T={'0xa4c13833916ae7d1':'Soil Moisture Probe 1',
'0xa4c1386faf69d5e0':'Soil Moisture Probe 2',
'0xa4c138cf0342f0d9':'Soil Moisture Probe 3',
'0xa4c1383917c90309':'External Rain Sensor'}
ds=json.loads(Path('/config/.storage/core.device_registry').read_text())['data']['devices']
es=json.loads(Path('/config/.storage/core.entity_registry').read_text())['data']['entities']
for ieee,name in T.items():
 matches=[d for d in ds if any(len(z)>1 and z[0]=='mqtt' and z[1]=='zigbee2mqtt_'+ieee for z in d.get('identifiers',[]))]
 assert len(matches)==1 and matches[0].get('name_by_user')==name, 'name mismatch '+ieee
 attached=[e for e in es if e.get('device_id')==matches[0]['id']]
 assert len(attached)>=3, 'missing sensor entity '+ieee
 assert all(x.get('entity_id') and x.get('unique_id') for x in attached),'entity identity missing'
print('JNS_SENSOR_NAMES_VERIFIED '+json.dumps({'names':T,'device_count':len(T),'entities':sum(1 for e in es if e.get('device_id') in [d['id'] for d in ds if any(len(z)>1 and z[0]=='mqtt' and z[1]=='zigbee2mqtt_'+ieee for z in d.get('identifiers',[]) for ieee in T)])}),flush=True)
'''
def guest(args, seconds=110,allow_fail=False):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 pid=r.get('pid');deadline=time.monotonic()+seconds
 while not r.get('exited'):
  if not isinstance(pid,int) or time.monotonic()>deadline:raise RuntimeError('VM905 guest process timed out')
  time.sleep(2)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 if r.get('exitcode')!=0 and not allow_fail:raise RuntimeError('Guest command failed: '+str(args[:3])+' '+(r.get('err-data') or '')[-130:])
 return r
def shell(c,seconds=40):
 return guest(['/bin/sh','-c',c],seconds)
def core_running():
 r=guest(['docker','inspect','-f','{{.State.Running}}','homeassistant'],30,allow_fail=True)
 return r.get('exitcode')==0 and (r.get('out-data') or '').strip()=='true'
def stop_core():
 guest(['ha','core','stop'],95,allow_fail=True)
 for n in range(15):
  if not core_running():return
  time.sleep(2)
 raise RuntimeError('Core did not stop: refusing registry write')
def start_core():
 r=guest(['ha','core','start'],95,allow_fail=True)
 for n in range(40):
  if core_running():return
  time.sleep(2)
 raise RuntimeError('Core failed to start')
def run_python(code):
 enc=base64.b64encode(code.encode()).decode()
 expr="exec(__import__('base64').b64decode("+repr(enc)+"))"
 return guest(['docker','exec','homeassistant','python3','-c',expr],70).get('out-data') or ''
if 'running' not in ssh_host('nodeb',['qm','status','905']):
 raise RuntimeError('VM905 is not running')
if not core_running():raise RuntimeError('HA-Core is not running: refusing changes')
print('JNS_SENSOR_NAMES_COLD_PREFLIGHT VM905 running; Core online',flush=True)
stage_out=run_python(STAGE)
line=next((x[len('JNS_SENSOR_NAMES_STAGE '):] for x in stage_out.splitlines() if x.startswith('JNS_SENSOR_NAMES_STAGE ')),None)
if not line:raise RuntimeError('Stage report absent')
report=json.loads(line)
print('JNS_SENSOR_NAMES_COLD_STAGED '+json.dumps({'count':len(report['changes']),'backup':report['backup_host']}),flush=True)
def sha_at(path):
 r=guest(['sha256sum',path],35)
 return (r.get('out-data') or '').split()[0]
original=report['original_host'];backup=report['backup_host'];staged=report['staged_host']
if sha_at(original)!=report['old_hash'] or sha_at(backup)!=report['old_hash'] or sha_at(staged)!=report['new_hash']:
 raise RuntimeError('Stage SHA validation failed')
stopped=False;swapped=False
try:
 stop_core();stopped=True
 if sha_at(original)!=report['old_hash']:raise RuntimeError('Registry changed during shutdown; aborting')
 if sha_at(backup)!=report['old_hash'] or sha_at(staged)!=report['new_hash']:raise RuntimeError('Backup/stage integrity error')
 cp='set -eu; cp -p '+shlex.quote(original)+' '+shlex.quote(original+'.jns-atomic')
 cp+='; cat '+shlex.quote(staged)+' > '+shlex.quote(original+'.jns-atomic')
 cp+='; mv -f '+shlex.quote(original+'.jns-atomic')+' '+shlex.quote(original)
 shell(cp)
 swapped=True
 if sha_at(original)!=report['new_hash']:raise RuntimeError('Installed registry hash mismatch')
 start_core();stopped=False
 checked=run_python(VERIFY)
 if 'JNS_SENSOR_NAMES_VERIFIED ' not in checked:raise RuntimeError('Post-start verification absent')
 print('JNS_SENSOR_NAMES_COLD_APPLIED '+json.dumps({'result':'success','backup':backup,'names':{c['ieee']:c['new'] for c in report['changes']}}),flush=True)
except BaseException as e:
 print('JNS_SENSOR_NAMES_COLD_ERROR '+type(e).__name__+': '+str(e)[:130],flush=True)
 if swapped:
  try:
   if core_running(): stop_core()
   if sha_at(original)!=report['new_hash']:raise RuntimeError('Unexpected concurrent registry change; manual restore needed')
   cp='set -eu; cp -p '+shlex.quote(original)+' '+shlex.quote(original+'.jns-rollback')
   cp+='; cat '+shlex.quote(backup)+' > '+shlex.quote(original+'.jns-rollback')
   cp+='; mv -f '+shlex.quote(original+'.jns-rollback')+' '+shlex.quote(original)
   shell(cp)
   print('JNS_SENSOR_NAMES_COLD_ROLLBACK_RESTORED',flush=True)
  except BaseException as re:
   print('JNS_SENSOR_NAMES_COLD_ROLLBACK_BLOCKED '+str(re)[:160],flush=True)
 if not core_running():
  try:start_core();print('JNS_SENSOR_NAMES_COLD_CORE_RESTARTED',flush=True)
  except BaseException as ce:print('JNS_SENSOR_NAMES_COLD_START_BLOCKED '+str(ce)[:140],flush=True)
 raise
