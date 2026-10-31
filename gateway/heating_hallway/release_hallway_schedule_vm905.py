#!/usr/bin/env python3
"""Guarded VM905 hallway predictive schedule switchover.

Only replaces jns_heating_predictive_schedule.yaml after validated native
hallway observer/learner are installed. Does not alter other HA packages.
"""
import base64,hashlib,importlib.util,json,os,pathlib,re,sys,time
source=pathlib.Path("gateway/heating_presence/jns_predictive_schedule.yaml").read_bytes()
NEW=hashlib.sha256(source).hexdigest()
OLD="af5850afa2282dd64793035c6a24dd4343cef6ff7efa92dcc6f9b7b51360ff42"
spec=importlib.util.spec_from_file_location("bridge",pathlib.Path("gateway/heating_presence/deploy.py"))
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
STAGE=r"""
import base64,hashlib,json,os,pathlib,stat,sys,tempfile,yaml
R=pathlib.Path('/config')
p=R/'packages/jns_heating_predictive_schedule.yaml'
data=base64.b64decode(sys.argv[1]);before_sha,new_sha,flag,runid=sys.argv[2:]
h=lambda b:hashlib.sha256(b).hexdigest()
assert runid.isdecimal()
assert p.is_file() and not p.is_symlink()
old=p.read_bytes()
assert h(old)==before_sha,'Production manual-target package changed; refuse'
assert h(data)==new_sha
original=yaml.safe_load(old);updated=yaml.safe_load(data)
expected=['jns_heating_learn_bedtime_v1','jns_heating_alarm_predictive_target_v1',
 'jns_heating_capture_honeywell_manual_target_v1',
 'jns_heating_clear_old_manual_hold_on_away_v1',
 'jns_heating_clear_manual_hold_on_bedtime_v1']
assert [x['id'] for x in original['automation']]==expected
assert [x['id'] for x in updated['automation']]==expected
assert set(original['input_boolean'])==set(updated['input_boolean'])
assert set(original['input_number'])==set(updated['input_number'])
assert set(original['input_datetime'])==set(updated['input_datetime'])
assert 'JNS_MANUAL_HIGH_HEAT_PRESERVED_V1' in data.decode()
assert 'JNS_HALLWAY_WARMUP_AUTHORITY_V1' in data.decode()
assert "sensor.jns_hallway_adaptive_warmup_minutes" in data.decode()
assert "sensor.lyric_home_heating_thermal_learning" not in data.decode()
assert "is_state('binary_sensor.jns_fireplace_override_safe','on')" in data.decode()
assert "sensor.jns_heating_active_requested_target" in data.decode()
assert "target_time: \\"10:00\\"" in data.decode()
assert "climate.thermostat_thermostat" in data.decode()
reg=json.loads((R/'.storage/core.entity_registry').read_text())['data']['entities']
have={e.get('entity_id') for e in reg if not e.get('disabled_by')}
for name in ['sensor.jns_hallway_house_temperature','sensor.jns_hallway_adaptive_warmup_minutes',
 'sensor.jns_hallway_weather_input_status','binary_sensor.jns_fireplace_override_safe',
 'input_boolean.jns_heating_manual_setpoint_hold','climate.thermostat_thermostat']:
 assert name in have,'Dependent native sensor/thermostat not registered: '+name
assert (R/'packages/jns_hallway_adaptive_learning.yaml').is_file()
assert (R/'packages/jns_hallway_observer.yaml').is_file()
# The existing shadow fire safety output must be hard false, never enabled.
obs=yaml.safe_load((R/'packages/jns_hallway_observer.yaml').read_text())
gates=[x for t in obs['template'] for x in t.get('binary_sensor',[])
  if x.get('name')=='JNS Fireplace Override Safe']
assert len(gates)==1 and gates[0]['state']=='false','Fire safety gate no longer hard disabled'
print('JNS_HALLWAY_SCHEDULE_PLAN '+json.dumps({
 'before_sha':before_sha,'after_sha':new_sha,'mode':flag,
 'manual_controls_preserved':True,'fire_guard_hard_off':True,'fallback_minutes':120,
 'core_restart_required':flag=='--apply'},sort_keys=True),flush=True)
if flag!='--apply':sys.exit(0)
bd=R/'.jns-backups'/('hallway-schedule-'+runid)
bd.mkdir(parents=True,exist_ok=False,mode=0o700)
backup=bd/p.name;backup.write_bytes(old);backup.chmod(0o600)
assert h(backup.read_bytes())==before_sha and p.read_bytes()==old
st=p.stat();fd,tmp=tempfile.mkstemp(prefix='.jns-hallway-switch-',dir=str(p.parent))
try:
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode))
 assert p.read_bytes()==old
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
assert h(p.read_bytes())==new_sha
print('JNS_HALLWAY_SCHEDULE_STAGED '+json.dumps({
 'backup':str(backup),'new_sha':new_sha},sort_keys=True),flush=True)
"""
RESTORE=r"""
from pathlib import Path
import hashlib,os,stat,sys,tempfile
p=Path('/config/packages/jns_heating_predictive_schedule.yaml')
b=Path(sys.argv[1]);newsha=sys.argv[2];oldsha=sys.argv[3]
h=lambda b:hashlib.sha256(b).hexdigest()
assert b.parent.name.startswith('hallway-schedule-') and b.parent.parent==Path('/config/.jns-backups')
assert b.name==p.name and h(b.read_bytes())==oldsha and h(p.read_bytes())==newsha
old=b.read_bytes();st=p.stat()
fd,tmp=tempfile.mkstemp(dir=str(p.parent),prefix='.jns-hallway-rollback-')
try:
 with os.fdopen(fd,'wb') as f:f.write(old);f.flush();os.fsync(f.fileno())
 os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode));os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
assert h(p.read_bytes())==oldsha
print('JNS_HALLWAY_SCHEDULE_RESTORED')
"""
VERIFY=r"""
import hashlib,pathlib,json,sys
P=pathlib.Path('/config/packages/jns_heating_predictive_schedule.yaml')
assert hashlib.sha256(P.read_bytes()).hexdigest()==sys.argv[1]
r=json.loads(pathlib.Path('/config/.storage/core.entity_registry').read_text())['data']['entities']
have={e.get('entity_id') for e in r if not e.get('disabled_by')}
for name in ('sensor.jns_hallway_house_temperature','sensor.jns_hallway_adaptive_warmup_minutes',
 'sensor.jns_hallway_weather_input_status','input_boolean.jns_heating_manual_setpoint_hold',
 'climate.thermostat_thermostat'):
 assert name in have
print('JNS_HALLWAY_SCHEDULE_ACTIVATED '+json.dumps({
 'source':'Hallway','target':'existing Honeywell',
 'user_setpoint_priority':True,'fireplace_guard':'disabled until verified cooling'},sort_keys=True))
"""
def core(payload,args,timeout=115):
 r=bridge.core(payload,args,seconds=timeout)
 if r.get('exitcode')!=0:raise RuntimeError('Core-bound Hallway package guard blocked')
 return r.get('out-data') or ''
def main():
 runid=os.environ.get('GITHUB_RUN_ID','')
 if not runid.isdecimal():raise RuntimeError('Runner identity required')
 before=bridge.docker_started()
 if not before.startswith('true '):raise RuntimeError('HA-General Core unavailable')
 args=[base64.b64encode(source).decode(),OLD,NEW,'--dry-run',runid]
 if 'JNS_HALLWAY_SCHEDULE_PLAN ' not in core(STAGE,args):
  raise RuntimeError('Live package preflight unverified')
 print('JNS_HALLWAY_SCHEDULE_PREFLIGHT_PASSED',flush=True)
 if '--apply' not in sys.argv:return
 args[3]='--apply'
 report=core(STAGE,args)
 m=re.search(r'(?m)^JNS_HALLWAY_SCHEDULE_STAGED (\{[^\n]+\})',report)
 if not m:raise RuntimeError('No staged package report')
 backup=json.loads(m.group(1))['backup']
 print('JNS_HALLWAY_SCHEDULE_BACKUP_VERIFIED',flush=True)
 try:
  marker=bridge.start_ha_command('check','ha core check',245)
  if not bridge.await_check(marker):raise RuntimeError('HA Core config check failed')
 except BaseException:
  if 'JNS_HALLWAY_SCHEDULE_RESTORED' not in core(RESTORE,[backup,NEW,OLD]):
   raise RuntimeError('Rollback failed')
  print('JNS_HALLWAY_SCHEDULE_ROLLED_BACK',flush=True)
  raise
 print('JNS_HALLWAY_SCHEDULE_CONFIG_VALIDATED',flush=True)
 bridge.start_ha_command('restart','ha core restart',125)
 for i in range(34):
  time.sleep(6)
  try:
   now=bridge.docker_started()
   if now.startswith('true ') and now!=before:
    print('JNS_HALLWAY_SCHEDULE_RESTART_CONFIRMED',flush=True)
    break
  except Exception:pass
 else:raise RuntimeError('Core restart unconfirmed; do not repeat')
 for i in range(24):
  time.sleep(5)
  r=bridge.core(VERIFY,[NEW],seconds=70)
  if r.get('exitcode')==0 and 'JNS_HALLWAY_SCHEDULE_ACTIVATED ' in (r.get('out-data') or ''):
   print((r.get('out-data') or '').strip(),flush=True)
   print('JNS_HALLWAY_PREDICTIVE_SOURCE_DEPLOYED',flush=True)
   return
 raise RuntimeError('Updated Core package installed but runtime proof missing')
if __name__=='__main__':
 try:main()
 except Exception as ex:
  print('JNS_HALLWAY_SCHEDULE_BLOCKED '+type(ex).__name__+': '+str(ex)[:190],flush=True)
  sys.exit(2)
