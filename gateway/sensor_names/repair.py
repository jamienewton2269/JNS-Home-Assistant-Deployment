#!/usr/bin/env python3
"""Guarded HA905 friendly device name update via a permitted add-on Core API proxy.

Changes only Home Assistant device registry name_by_user through documented WS API.
Never changes Zigbee2MQTT friendly_name, entity IDs, automations, MQTT topics or firmware.
Never stores or logs API credentials; token travels only through in-guest pipe.
"""
import base64,json,shlex,sys,time
from pathlib import Path
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

INNER=r'''
import json,sys,websocket
from datetime import datetime,timezone
from pathlib import Path
TOKEN=sys.stdin.read().strip()
if not TOKEN or len(TOKEN)<16: raise RuntimeError('no authorized add-on token')
EXPECTED={
 '0xa4c13833916ae7d1': ('Soil Moisture Probe 1','AOYAN','Soil moisture sensor'),
 '0xa4c1386faf69d5e0': ('Soil Moisture Probe 2','AOYAN','Soil moisture sensor'),
 '0xa4c138cf0342f0d9': ('Soil Moisture Probe 3','AOYAN','Soil moisture sensor'),
 '0xa4c1383917c90309': ('External Rain Sensor','HOBEIAN','Rainwater detection sensor'),
}
sock=None
sequence=0
changed=[]
before={}
def request(t, **kwargs):
 global sequence
 sequence+=1
 sock.send(json.dumps({'id':sequence,'type':t,**kwargs}))
 for _ in range(30):
  m=json.loads(sock.recv())
  if m.get('id')==sequence:
   if not m.get('success'):raise RuntimeError('API '+t+' unsuccessful '+str(m.get('error',{}).get('code',''))[:80])
   return m.get('result')
 raise RuntimeError('API response unavailable')
def find(devices):
 result={}
 for ieee in EXPECTED:
  matches=[d for d in devices if any(isinstance(i,(tuple,list)) and len(i)>=2 and
             i[0]=='mqtt' and str(i[1]).lower()=='zigbee2mqtt_'+ieee
             for i in d.get('identifiers',[]))]
  if len(matches)!=1:raise RuntimeError('Expected exactly one HA device for '+ieee)
  result[ieee]=matches[0]
 return result
def subset(ent,device_ids):
 return sorted((e['entity_id'],e.get('unique_id'),e.get('device_id')) for e in ent
               if e.get('device_id') in device_ids and e.get('entity_id','').startswith(('sensor.','binary_sensor.')))
try:
 sock=websocket.create_connection('ws://supervisor/core/websocket',timeout=10)
 hello=json.loads(sock.recv())
 if hello.get('type')!='auth_required':raise RuntimeError('Unexpected WS handshake')
 sock.send(json.dumps({'type':'auth','access_token':TOKEN}))
 TOKEN=None
 if json.loads(sock.recv()).get('type')!='auth_ok':raise RuntimeError('Add-on API permission unavailable')
 all_devices=request('config/device_registry/list')
 current=find(all_devices)
 before_entities=subset(request('config/entity_registry/list'),[d['id'] for d in current.values()])
 for ieee,(name,mfg,model) in EXPECTED.items():
  device=current[ieee]
  if device.get('manufacturer')!=mfg or device.get('model')!=model:
   raise RuntimeError('Identity mismatch for '+ieee)
  if device.get('name_by_user') not in (None,name):
   raise RuntimeError('Custom friendly name already set, refusing overwrite for '+ieee)
  before[ieee]={'id':device['id'],'name':device.get('name'),
                'name_by_user':device.get('name_by_user'),'target':name}
 backup_dir=Path('/config/.jns-backups/sensor-names')
 backup_dir.mkdir(parents=True,exist_ok=True)
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 backup=backup_dir/('sensor-name-'+stamp+'.json')
 if backup.exists(): raise RuntimeError('Backup collision, refused')
 backup.write_text(json.dumps({'before':before,'entity_ids':before_entities},indent=2)+'\n')
 print('JNS_SENSOR_NAMES_PLAN '+json.dumps({'target_count':len(before),'backup':str(backup),'unchanged_entity_count':len(before_entities)}),flush=True)
 try:
  for ieee,(target,_,_) in EXPECTED.items():
   device=current[ieee]
   if device.get('name_by_user')==target:continue
   updated=request('config/device_registry/update',device_id=device['id'],name_by_user=target)
   if updated.get('name_by_user')!=target:raise RuntimeError('Device name update not acknowledged: '+ieee)
   changed.append(ieee)
  after=find(request('config/device_registry/list'))
  after_entities=subset(request('config/entity_registry/list'),[d['id'] for d in after.values()])
  if before_entities!=after_entities:raise RuntimeError('Entity identity changed unexpectedly')
  if not all(after[ieee].get('name_by_user')==data[0] for ieee,data in EXPECTED.items()):
   raise RuntimeError('Post-update names not verified')
 except BaseException:
  for ieee in reversed(changed):
   try:request('config/device_registry/update',device_id=before[ieee]['id'],name_by_user=before[ieee]['name_by_user'])
   except BaseException:print('JNS_SENSOR_NAME_ROLLBACK_FAILED '+ieee,flush=True)
  raise
 print('JNS_SENSOR_NAMES_APPLIED '+json.dumps({'status':'verified','names':{ieee:v[0] for ieee,v in EXPECTED.items()},
    'entity_count_unchanged':len(before_entities),'backup':str(backup),'changed_count':len(changed)}),flush=True)
finally:
 if sock:
  try:sock.close()
  except:pass
'''
def guest(argv,limit=75):
 item=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*argv]))
 pid=item.get('pid')
 deadline=time.monotonic()+limit
 while not item.get('exited'):
  if not isinstance(pid,int) or time.monotonic()>deadline:raise RuntimeError('Guest exec did not finish')
  time.sleep(2)
  item=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 if item.get('exitcode')!=0:
  print('JNS_SENSOR_NAMES_BLOCKED '+json.dumps({'exitcode':item.get('exitcode'),
        'out_tail':(item.get('out-data') or '')[-700:]}),flush=True)
  raise RuntimeError('Guest name update blocked')
 return item.get('out-data') or ''
if 'running' not in ssh_host('nodeb',['qm','status','905']):
 raise RuntimeError('VM905 not running')
names=guest(['docker','ps','--format','{{.Names}}'],35).splitlines()
# Use only the explicitly HA-API-capable Advanced SSH app as credential source.
addon='addon_a0d7b954_ssh'
if addon not in names:raise RuntimeError('Advanced SSH app not running; no credentials used and no changes')
expr="exec(__import__('base64').b64decode("+repr(base64.b64encode(INNER.encode()).decode())+"))"
script=("set -o pipefail; docker exec "+shlex.quote(addon)+
        " sh -c 'printf %s \"$SUPERVISOR_TOKEN\"' | "+
        "docker exec -i homeassistant python3 -c "+shlex.quote(expr))
out=guest(['/bin/sh','-c',script],110)
print(out[-8500:],flush=True)
if 'JNS_SENSOR_NAMES_APPLIED ' not in out:raise RuntimeError('No verified apply result')
