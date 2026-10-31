#!/usr/bin/env python3
"""JNS manual Honeywell setpoint preservation, VM905, one-shot release.

Exact old/new bytes, deterministic restore, no dashboard/MPD/security edit.
Check Home Assistant configuration before one guarded Core restart.
"""
import base64, hashlib, importlib.util, json, os, pathlib, re, sys, time

REPO=pathlib.Path("gateway/heating_presence")
OLD="3f4dc62b3a3143bafc5d4c7d72bf81f1a06af0ebe12f17a1e027b7a56f4ac108"
data=(REPO/"jns_predictive_schedule.yaml").read_bytes()
NEW=hashlib.sha256(data).hexdigest()
spec=importlib.util.spec_from_file_location("jns_heating_bridge",REPO/"deploy.py")
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)

STAGE=r"""
from pathlib import Path
import base64,hashlib,json,os,stat,sys,tempfile,yaml
p=Path('/config/packages/jns_heating_predictive_schedule.yaml')
oldsha,newsha,b64,mode,runid=sys.argv[1:6]
payload=base64.b64decode(b64)
sha=lambda b:hashlib.sha256(b).hexdigest()
assert p.is_file() and not p.is_symlink(),'Missing or linked heating package'
before=p.read_bytes()
assert sha(before)==oldsha,'Installed schedule hash changed; refuse overwrite'
assert sha(payload)==newsha,'Candidate package digest changed'
existing=yaml.safe_load(before);proposed=yaml.safe_load(payload)
assert [x['id'] for x in existing['automation']]==[
 'jns_heating_learn_bedtime_v1','jns_heating_alarm_predictive_target_v1']
assert [x['id'] for x in proposed['automation']]==[
 'jns_heating_learn_bedtime_v1','jns_heating_alarm_predictive_target_v1',
 'jns_heating_capture_honeywell_manual_target_v1',
 'jns_heating_clear_old_manual_hold_on_away_v1',
 'jns_heating_clear_manual_hold_on_bedtime_v1']
assert 'JNS_MANUAL_HIGH_HEAT_PRESERVED_V1' in payload.decode()
assert 'climate.thermostat_thermostat' in payload.decode()
assert 'jns_heating_manual_setpoint_hold' in proposed['input_boolean']
assert 'jns_heating_manual_target' in proposed['input_number']
assert 'jns_heating_last_auto_command_time' in proposed['input_datetime']
assert runid.isdecimal(),'Invalid workflow identity'
print('JNS_MANUAL_SETPOINT_STAGE_PLAN '+json.dumps({
  'old_sha':oldsha,'new_sha':newsha,'old_automations':2,
  'new_automations':5,'mode':mode,'scope':'heating package only'
},sort_keys=True),flush=True)
if mode!='--apply':sys.exit(0)
bd=Path('/config/.jns-backups')/('manual-honeywell-priority-'+runid)
bd.mkdir(mode=0o700,parents=True,exist_ok=False)
backup=bd/p.name
backup.write_bytes(before);os.chmod(backup,0o600)
assert sha(backup.read_bytes())==oldsha,'Backup verification failed'
assert p.read_bytes()==before,'Schedule changed concurrently'
st=p.stat()
fd,tmp=tempfile.mkstemp(prefix='.jns-honeywell-',dir=str(p.parent))
try:
 with os.fdopen(fd,'wb') as f:
  f.write(payload);f.flush();os.fsync(f.fileno())
 os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode))
 assert p.read_bytes()==before,'Schedule changed before swap'
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
assert sha(p.read_bytes())==newsha,'New schedule verification failed'
print('JNS_MANUAL_SETPOINT_STAGED '+json.dumps({
  'backup':str(backup),'old_sha':oldsha,'new_sha':newsha
},sort_keys=True),flush=True)
"""
RESTORE=r"""
import hashlib,os,pathlib,stat,sys,tempfile
p=pathlib.Path('/config/packages/jns_heating_predictive_schedule.yaml')
backup=pathlib.Path(sys.argv[1]);newsha=sys.argv[2];oldsha=sys.argv[3]
sha=lambda b:hashlib.sha256(b).hexdigest()
assert backup.parent.name.startswith('manual-honeywell-priority-')
assert backup.parent.parent==pathlib.Path('/config/.jns-backups')
assert backup.name==p.name and backup.is_file()
original=backup.read_bytes()
assert sha(original)==oldsha and sha(p.read_bytes())==newsha,'Changed by other writer; refuse rollback'
st=p.stat();fd,tmp=tempfile.mkstemp(prefix='.jns-honeywell-rollback-',dir=str(p.parent))
try:
 with os.fdopen(fd,'wb') as f:f.write(original);f.flush();os.fsync(f.fileno())
 os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode))
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
assert sha(p.read_bytes())==oldsha,'Rollback checksum mismatch'
print('JNS_MANUAL_SETPOINT_BACKUP_RESTORED',flush=True)
"""
VERIFY=r"""
import hashlib,json,pathlib,yaml
p=pathlib.Path('/config/packages/jns_heating_predictive_schedule.yaml')
sha=hashlib.sha256(p.read_bytes()).hexdigest()
assert sha==__import__('sys').argv[1],'Schedule digest mismatched after Core restart'
d=yaml.safe_load(p.read_text())
assert len(d['automation'])==5,'Missing thermostat observer automation'
reg=json.loads(pathlib.Path('/config/.storage/core.entity_registry').read_text())['data']['entities']
present={e.get('entity_id') for e in reg if not e.get('disabled_by')}
required=('input_boolean.jns_heating_manual_setpoint_hold',
          'input_number.jns_heating_manual_target',
          'input_number.jns_heating_last_automatic_target',
          'input_datetime.jns_heating_last_auto_command_time',
          'sensor.jns_heating_active_requested_target')
missing=[x for x in required if x not in present]
assert not missing,'Required helpers not registered: '+','.join(missing)
autos={e.get('unique_id') for e in reg if e.get('platform')=='automation' and not e.get('disabled_by')}
expected=('jns_heating_capture_honeywell_manual_target_v1',
          'jns_heating_clear_old_manual_hold_on_away_v1',
          'jns_heating_clear_manual_hold_on_bedtime_v1')
assert all(a in autos for a in expected),'New automation identities not enabled'
print('JNS_MANUAL_SETPOINT_LIVE_VERIFIED '+json.dumps({
 'package_sha':sha,'helpers_ready':True,'automations_ready':True,'scope':'VM905 heating only'
},sort_keys=True),flush=True)
"""
def run_core(source,args,timeout=120):
    response=bridge.core(source,args,seconds=timeout)
    if response.get('exitcode')!=0:raise RuntimeError('Guest heating command failed; see controlled rollback')
    return response.get('out-data') or ''
def rollback(backup):
    result=run_core(RESTORE,[backup,NEW,OLD])
    if 'JNS_MANUAL_SETPOINT_BACKUP_RESTORED' not in result:
        raise RuntimeError('Heating schedule rollback unverified')
    print('JNS_MANUAL_SETPOINT_ROLLBACK_VERIFIED',flush=True)
def main():
    runid=os.environ.get('GITHUB_RUN_ID','')
    if not runid.isdecimal():raise RuntimeError('GitHub runner identity absent')
    if 'running' not in bridge.ssh_host('nodeb',['qm','status','905']):
        raise RuntimeError('VM905 is stopped')
    before_core=bridge.docker_started()
    if not before_core.startswith('true '):raise RuntimeError('Home Assistant Core not running')
    # Restrict to already-known bedside package; do not touch its automations.
    dry=run_core(STAGE,[OLD,NEW,base64.b64encode(data).decode(),'--dry-run',runid])
    if 'JNS_MANUAL_SETPOINT_STAGE_PLAN' not in dry:raise RuntimeError('Preflight missing')
    print('JNS_MANUAL_SETPOINT_PREFLIGHT_PASSED',flush=True)
    if '--apply' not in sys.argv:return
    result=run_core(STAGE,[OLD,NEW,base64.b64encode(data).decode(),'--apply',runid])
    match=re.search(r'(?m)^JNS_MANUAL_SETPOINT_STAGED (\{[^\n]+\})',result)
    if not match:raise RuntimeError('Install report missing; inspect VM905 before repeating')
    backup=json.loads(match.group(1))['backup']
    print('JNS_MANUAL_SETPOINT_BACKUP_CONFIRMED',flush=True)
    try:
        marker=bridge.start_ha_command('check','ha core check',245)
        if not bridge.await_check(marker):
            raise RuntimeError('HA Core config validation failed')
    except Exception:
        rollback(backup)
        raise
    print('JNS_MANUAL_SETPOINT_CORE_CHECK_PASSED',flush=True)
    # No redundant reboot. Asynchronous HAOS command then observe container.
    bridge.start_ha_command('restart','ha core restart',125)
    for i in range(36):
        time.sleep(6)
        try:
            current=bridge.docker_started()
            if current.startswith('true ') and current!=before_core:
                print('JNS_MANUAL_SETPOINT_RESTART_CONFIRMED',flush=True)
                break
        except Exception:pass
    else:
        raise RuntimeError('Core restart not observed; no blind repeat')
    for i in range(16):
        time.sleep(5)
        try:
            response=bridge.core(VERIFY,[NEW],seconds=45)
            if response.get('exitcode')==0 and 'JNS_MANUAL_SETPOINT_LIVE_VERIFIED' in (response.get('out-data') or ''):
                print('JNS_MANUAL_SETPOINT_DEPLOYED_AND_VERIFIED',flush=True)
                return
        except Exception:pass
    raise RuntimeError('Core restart confirmed but helper/automation registration unverified')
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('JNS_MANUAL_SETPOINT_RELEASE_BLOCKED '+type(exc).__name__+': '+str(exc)[:220],flush=True)
        sys.exit(2)
