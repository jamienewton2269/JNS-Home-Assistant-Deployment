#!/usr/bin/env python3
"""Protected Hallway warm-up observer release, VM905.
Append-only package, no thermostat or security commands. Exact source hash,
Core config check, one restart, fail on unknown/duplicate source and rollback
of staged package before restart if config validation fails.
"""
import base64,hashlib,importlib.util,json,os,pathlib,re,sys,time
ROOT=pathlib.Path("gateway/heating_hallway")
source=(ROOT/"jns_hallway_adaptive_learning.yaml").read_bytes()
digest=hashlib.sha256(source).hexdigest()
spec=importlib.util.spec_from_file_location("bridge",pathlib.Path("gateway/heating_presence/deploy.py"))
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
STAGE=r"""
import base64,hashlib,json,os,pathlib,stat,sys,tempfile,yaml
R=pathlib.Path('/config');P=R/'packages/jns_hallway_adaptive_learning.yaml'
payload=base64.b64decode(sys.argv[1]);expected=sys.argv[2];flag=sys.argv[3]
assert hashlib.sha256(payload).hexdigest()==expected
assert P.parent.is_dir() and not P.exists(),'Native learner already installed'
package=yaml.safe_load(payload)
assert set(['automation','template','input_number','input_boolean','input_datetime']).issubset(package)
raw=payload.decode()
assert 'action: climate.' not in raw and 'action: alarm_control_panel.' not in raw
assert 'sensor.jns_hallway_house_temperature' in raw
assert 'weather.ha_general' not in raw or 'sensor.jns_hallway_weather_input_status' in raw
assert 'hallway-precision-v1' in raw and 'input_boolean.jns_heating_manual_setpoint_hold' not in raw
assert len(package['automation'])==2
reg=json.loads((R/'.storage/core.entity_registry').read_text())['data']['entities']
enabled={x.get('entity_id') for x in reg if not x.get('disabled_by')}
required=['sensor.jns_hallway_house_temperature','sensor.jns_fireplace_temperature',
 'binary_sensor.jns_fireplace_heat_detected','sensor.jns_hallway_weather_input_status',
 'binary_sensor.lyric_home_heating_heating_call','climate.thermostat_thermostat']
assert all(x in enabled for x in required),'Native Hallway observer or Honeywell heating call missing'
plan={'vm':905,'digest':expected,'mode':flag,'heating_commands':0,
 'ready_for_learning':True,'fireplace_suppression_unchanged':True}
print('JNS_HALLWAY_WARMUP_STAGE_PLAN '+json.dumps(plan,sort_keys=True),flush=True)
if flag!='--apply':sys.exit(0)
st=P.parent.stat();fd,tmp=tempfile.mkstemp(prefix='.jns-hallway-warmup-',dir=str(P.parent))
try:
 with os.fdopen(fd,'wb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,0o644)
 assert not P.exists()
 os.replace(tmp,P)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
assert hashlib.sha256(P.read_bytes()).hexdigest()==expected
print('JNS_HALLWAY_WARMUP_STAGED',flush=True)
"""
RESTORE=r"""
import hashlib,pathlib,sys
p=pathlib.Path('/config/packages/jns_hallway_adaptive_learning.yaml')
assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[1]
p.unlink();assert not p.exists()
print('JNS_HALLWAY_WARMUP_ROLLBACK_OK')
"""
VERIFY=r"""
import hashlib,json,pathlib,sys
R=pathlib.Path('/config')
P=R/'packages/jns_hallway_adaptive_learning.yaml'
assert hashlib.sha256(P.read_bytes()).hexdigest()==sys.argv[1]
reg=json.loads((R/'.storage/core.entity_registry').read_text())['data']['entities']
have={e.get('entity_id') for e in reg if not e.get('disabled_by')}
required=['sensor.jns_hallway_adaptive_warmup_minutes',
'sensor.jns_hallway_predicted_60m_while_heating',
'input_number.jns_hallway_warmup_minutes_per_c',
'input_number.jns_hallway_warmup_observations',
'input_boolean.jns_hallway_warmup_tracking',
'input_datetime.jns_hallway_warmup_started']
missing=[x for x in required if x not in have]
aid={e.get('unique_id') for e in reg if e.get('platform')=='automation' and not e.get('disabled_by')}
need=['jns_hallway_observe_warmup_start_v1','jns_hallway_observe_warmup_end_v1']
missingauto=[x for x in need if x not in aid]
print('JNS_HALLWAY_WARMUP_VERIFY '+json.dumps({'missing':missing,
 'missing_automations':missingauto,'source_epoch':'hallway-precision-v1',
 'no_climate_commands':True},sort_keys=True),flush=True)
assert not missing and not missingauto
"""
def core(src,args,seconds=100):
 r=bridge.core(src,args,seconds=seconds)
 if r.get('exitcode')!=0:raise RuntimeError('VM905 learning package command rejected')
 return r.get('out-data') or ''
def main():
 runid=os.environ.get('GITHUB_RUN_ID','')
 if not runid.isdecimal():raise RuntimeError('Runner identity missing')
 if 'running' not in bridge.ssh_host('nodeb',['qm','status','905']):
  raise RuntimeError('HA-General unavailable')
 before=bridge.docker_started()
 if not before.startswith('true '):raise RuntimeError('HA Core not running')
 args=[base64.b64encode(source).decode(),digest,'--dry-run']
 if 'JNS_HALLWAY_WARMUP_STAGE_PLAN ' not in core(STAGE,args):
  raise RuntimeError('Preflight unconfirmed')
 print('JNS_HALLWAY_WARMUP_PREFLIGHT_PASSED',flush=True)
 if '--apply' not in sys.argv:return
 args[2]='--apply'
 if 'JNS_HALLWAY_WARMUP_STAGED' not in core(STAGE,args):
  raise RuntimeError('Stage did not confirm; manual inspection required')
 print('JNS_HALLWAY_WARMUP_PACKAGE_STAGED',flush=True)
 try:
  marker=bridge.start_ha_command('check','ha core check',245)
  if not bridge.await_check(marker):raise RuntimeError('Core configuration rejected')
 except Exception:
  if 'JNS_HALLWAY_WARMUP_ROLLBACK_OK' not in core(RESTORE,[digest]):
   raise RuntimeError('Pre-restart rollback unverified')
  print('JNS_HALLWAY_WARMUP_CORE_CHECK_ROLLBACK',flush=True)
  raise
 print('JNS_HALLWAY_WARMUP_CORE_CHECK_PASSED',flush=True)
 bridge.start_ha_command('restart','ha core restart',125)
 for i in range(34):
  time.sleep(6)
  try:
   now=bridge.docker_started()
   if now.startswith('true ') and now!=before:
    print('JNS_HALLWAY_WARMUP_CORE_RESTART_CONFIRMED',flush=True)
    break
  except Exception:pass
 else:raise RuntimeError('Core restart unconfirmed; no blind repeat')
 for i in range(24):
  time.sleep(5)
  r=bridge.core(VERIFY,[digest],seconds=75)
  if r.get('exitcode')==0 and 'JNS_HALLWAY_WARMUP_VERIFY ' in (r.get('out-data') or ''):
   print((r.get('out-data') or '').strip(),flush=True)
   print('JNS_HALLWAY_WARMUP_DEPLOYED',flush=True)
   return
 raise RuntimeError('Core started, learner entities not registered; read-only recheck required')
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('JNS_HALLWAY_WARMUP_RELEASE_BLOCKED '+type(e).__name__+': '+str(e)[:250],flush=True)
  sys.exit(2)
