#!/usr/bin/env python3
"""Guarded VM905 Hallway / Fireplace / Open-Meteo passive observer.

Exact device fingerprint matching, additive package only, HA Core check,
one HA restart, read-only registration verification. No thermostat commands.
"""
import base64,hashlib,importlib.util,json,os,pathlib,re,sys,time
DIR=pathlib.Path("gateway/heating_hallway")
source=(DIR/"jns_hallway_observer.yaml.template").read_bytes()
sourcehash=hashlib.sha256(source).hexdigest()
spec=importlib.util.spec_from_file_location("jns_heating_bridge",pathlib.Path("gateway/heating_presence/deploy.py"))
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)

STAGE=r"""
import base64,hashlib,json,os,pathlib,stat,sys,tempfile,yaml
R=pathlib.Path('/config')
P=R/'packages/jns_hallway_observer.yaml'
template=base64.b64decode(sys.argv[1]);expected=sys.argv[2]
flag=sys.argv[3];runid=sys.argv[4]
assert hashlib.sha256(template).hexdigest()==expected
assert runid.isdecimal()
assert P.parent.is_dir() and not P.exists(),'Observer package already exists; never overwrite'
dev=json.loads((R/'.storage/core.device_registry').read_text())['data']['devices']
reg=json.loads((R/'.storage/core.entity_registry').read_text())['data']['entities']
entries=json.loads((R/'.storage/core.config_entries').read_text())['data']['entries']
enabled={e['entity_id'] for e in reg if not e.get('disabled_by')}
def candidates(device):
 return sorted(set(e['entity_id'] for e in reg if e.get('device_id')==device and
  not e.get('disabled_by') and e.get('entity_id','').startswith('sensor.') and
  ((e.get('device_class') or e.get('original_device_class'))=='temperature' or
    e.get('entity_id','').endswith('_temperature'))))
HALL_ID='3fc0d19af1ae3fad19d67ae05b4ccb0f'
FIRE_IEEE='0xa4c138818d33ffff'
assert len([d for d in dev if d.get('id')==HALL_ID])==1
hall=candidates(HALL_ID)
firedev=set()
for d in dev:
 if any(FIRE_IEEE in str(z).lower() for pair in (d.get('identifiers') or []) for z in pair):
  firedev.add(d.get('id'))
for e in reg:
 if FIRE_IEEE in str(e.get('unique_id','')).lower() and e.get('device_id'):firedev.add(e['device_id'])
fire=sorted({ident for device in firedev for ident in candidates(device)})
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
assert len(hall)==1 and sha(hall[0]).startswith('0765c6b32aae'),'Hallway source mismatch'
assert len(fire)==1 and sha(fire[0]).startswith('6e57b33c6d86'),'Fireplace source mismatch'
assert hall[0]!=fire[0]
assert 'weather.ha_general' in enabled,'Open-Meteo forecast source unavailable'
we=[e for e in reg if e.get('entity_id')=='weather.ha_general']
dom={e['entry_id']:e.get('domain') for e in entries}
assert len(we)==1 and dom.get(we[0].get('config_entry_id'))=='open_meteo','Wrong weather provider'
assert 'sensor.thermostat_thermostat_outdoor_temperature' in enabled,'Outdoor reference unavailable'
assert 'climate.thermostat_thermostat' in enabled,'Honeywell not registered'
for name in ('sensor.jns_hallway_house_temperature','sensor.jns_fireplace_temperature',
             'sensor.jns_hallway_hourly_open_meteo','sensor.jns_hallway_weather_input_status',
             'binary_sensor.jns_fireplace_heat_detected','binary_sensor.jns_fireplace_override_safe'):
 assert name not in enabled,'Observer entity already present: '+name
replacement=(template.decode().replace('__HALLWAY_TEMP_ENTITY__',hall[0])
                   .replace('__FIREPLACE_TEMP_ENTITY__',fire[0]))
assert '__HALLWAY_TEMP_ENTITY__' not in replacement and '__FIREPLACE_TEMP_ENTITY__' not in replacement
assert 'climate.set_temperature' not in replacement and 'climate.set_hvac_mode' not in replacement
parsed=yaml.safe_load(replacement)
assert isinstance(parsed.get('template'),list)
actions=[a for v in parsed['template'] for a in v.get('actions',[])]
assert len(actions)==1 and actions[0]['action']=='weather.get_forecasts'
binary=[x for v in parsed['template'] for x in v.get('binary_sensor',[])]
assert any(x['name']=='JNS Fireplace Override Safe' and x['state']=='false' for x in binary)
payload=replacement.encode()
report={'old_status':'no observer package','new_sha256':hashlib.sha256(payload).hexdigest(),
        'vm':905,'mode':flag,'hallway_device_verified':True,'fireplace_device_verified':True,
        'hourly_provider':'Open-Meteo','climate_write_services':0,'safe_gate_hard_off':True}
print('JNS_HALLWAY_OBSERVER_STAGE_PLAN '+json.dumps(report,sort_keys=True),flush=True)
if flag!='--apply':sys.exit(0)
st=P.parent.stat()
fd,tmp=tempfile.mkstemp(prefix='.jns-hallway-observer-',dir=str(P.parent))
try:
 with os.fdopen(fd,'wb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,0o644)
 assert not P.exists(),'Concurrent observer deployment detected'
 os.replace(tmp,P)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
assert hashlib.sha256(P.read_bytes()).hexdigest()==report['new_sha256']
print('JNS_HALLWAY_OBSERVER_STAGED '+json.dumps(report,sort_keys=True),flush=True)
"""
RESTORE=r"""
import hashlib,pathlib,sys
p=pathlib.Path('/config/packages/jns_hallway_observer.yaml')
assert p.is_file() and not p.is_symlink()
assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[1]
p.unlink()
assert not p.exists()
print('JNS_HALLWAY_OBSERVER_ROLLBACK_COMPLETE')
"""
VERIFY=r"""
import hashlib,json,pathlib,sys,yaml
R=pathlib.Path('/config');p=R/'packages/jns_hallway_observer.yaml'
assert p.is_file()
d=yaml.safe_load(p.read_text())
sensor_names=[x.get('name') for v in d['template'] for x in v.get('sensor',[])]
reg=json.loads((R/'.storage/core.entity_registry').read_text())['data']['entities']
valid={r['entity_id'] for r in reg if not r.get('disabled_by')}
wanted=['sensor.jns_hallway_house_temperature','sensor.jns_fireplace_temperature',
        'sensor.jns_hallway_hourly_open_meteo','sensor.jns_hallway_weather_input_status',
        'binary_sensor.jns_fireplace_heat_detected','binary_sensor.jns_fireplace_override_safe']
missing=[x for x in wanted if x not in valid]
print('JNS_HALLWAY_OBSERVER_VERIFY '+json.dumps({
 'installed':True,'registered':len(wanted)-len(missing),'expected':len(wanted),
 'missing':missing,'climate_unchanged':True,
 'status':'ready' if not missing else 'registration_pending'
},sort_keys=True),flush=True)
assert not missing
"""
def core(src,params,seconds=120):
 r=bridge.core(src,params,seconds=seconds)
 if r.get('exitcode')!=0:raise RuntimeError('HA native observer guest action refused')
 return r.get('out-data') or ''
def main():
 runid=os.environ.get('GITHUB_RUN_ID','')
 if not runid.isdecimal():raise RuntimeError('GitHub execution identity required')
 if 'running' not in bridge.ssh_host('nodeb',['qm','status','905']):raise RuntimeError('HA905 stopped')
 before=bridge.docker_started()
 if not before.startswith('true '):raise RuntimeError('HA Core not ready')
 args=[base64.b64encode(source).decode(),sourcehash,'--dry-run',runid]
 dry=core(STAGE,args)
 if 'JNS_HALLWAY_OBSERVER_STAGE_PLAN ' not in dry:raise RuntimeError('Preflight report missing')
 print('JNS_HALLWAY_OBSERVER_PREFLIGHT_PASSED',flush=True)
 if '--apply' not in sys.argv:return
 args[2]='--apply'
 applied=core(STAGE,args)
 m=re.search(r'(?m)^JNS_HALLWAY_OBSERVER_STAGED (\{[^\n]+\})',applied)
 if not m:raise RuntimeError('Stage result missing; do not retry blindly')
 digest=json.loads(m.group(1))['new_sha256']
 print('JNS_HALLWAY_OBSERVER_FILE_VERIFIED',flush=True)
 try:
  marker=bridge.start_ha_command('check','ha core check',245)
  if not bridge.await_check(marker):raise RuntimeError('HA configuration check failed')
 except BaseException:
  restore=core(RESTORE,[digest])
  if 'JNS_HALLWAY_OBSERVER_ROLLBACK_COMPLETE' not in restore:raise RuntimeError('Rollback unverified')
  print('JNS_HALLWAY_OBSERVER_ROLLED_BACK',flush=True)
  raise
 print('JNS_HALLWAY_OBSERVER_CORE_CHECK_PASSED',flush=True)
 bridge.start_ha_command('restart','ha core restart',125)
 for i in range(34):
  time.sleep(6)
  try:
   now=bridge.docker_started()
   if now.startswith('true ') and now!=before:
    print('JNS_HALLWAY_OBSERVER_RESTART_CONFIRMED',flush=True)
    break
  except Exception:pass
 else:raise RuntimeError('No confirmed HA Core restart; inspect before retry')
 for i in range(24):
  time.sleep(5)
  r=bridge.core(VERIFY,seconds=75)
  if r.get('exitcode')==0 and 'JNS_HALLWAY_OBSERVER_VERIFY ' in (r.get('out-data') or ''):
   print((r.get('out-data') or '').strip(),flush=True)
   print('JNS_HALLWAY_OBSERVER_DEPLOYED',flush=True)
   return
 raise RuntimeError('Core started but observer entity registration still pending')
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_HALLWAY_OBSERVER_RELEASE_BLOCKED '+type(e).__name__+': '+str(e)[:200],flush=True)
  sys.exit(2)
