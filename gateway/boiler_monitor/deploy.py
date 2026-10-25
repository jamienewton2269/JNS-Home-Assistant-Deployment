#!/usr/bin/env python3
"""Scoped HA905 additive boiler monitoring transaction via established JNS SSH/QGA."""
import base64, hashlib, json, os, pathlib, sys, time
sys.path.insert(0, 'gateway/arrival_lighting')
from readiness_probe import ssh_host

HERE = pathlib.Path('gateway/boiler_monitor')

def guest(args, seconds=80):
    r = json.loads(ssh_host('nodeb', ['qm', 'guest', 'exec', '905', '--', *args]))
    until = time.monotonic() + seconds
    while not r.get('exited'):
        if not isinstance(r.get('pid'), int):
            raise RuntimeError('Guest command status unknown; no blind retry')
        if time.monotonic() > until:
            raise RuntimeError('Guest command unfinished; no blind retry')
        time.sleep(2)
        r = json.loads(ssh_host('nodeb', ['qm', 'guest', 'exec-status', '905', str(r['pid'])]))
    return r

def core(source, *args):
    code = 'exec(__import__("base64").b64decode(' + repr(base64.b64encode(source.encode()).decode()) + '))'
    r = guest(['docker', 'exec', 'homeassistant', 'python3', '-c', code, *args])
    if r.get('exitcode') != 0:
        print('SCOPED_OPERATION_FAILED', (r.get('err-data') or '')[-900:], flush=True)
        raise RuntimeError('Scoped operation failed')
    return r.get('out-data') or ''

INSTALL = r'''
import pathlib,json,sys,base64,hashlib,os,tempfile,datetime,yaml
root=pathlib.Path('/config')
assert 'packages: !include_dir_named packages' in (root/'configuration.yaml').read_text()
reg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
assert any(e.get('entity_id')=='climate.thermostat_thermostat' and e.get('platform')=='lyric' and not e.get('disabled_by') for e in reg)
assert not any(e.get('entity_id','').startswith(('sensor.jns_boiler_', 'binary_sensor.jns_boiler_')) for e in reg), 'Existing boiler entity conflict'
payload=json.loads(base64.b64decode(sys.argv[1]))
assert set(payload)=={'packages/jns_boiler_monitor.yaml','dashboards/jns_boiler_monitor.yaml'}
for rel,content in payload.items():
 p=root/rel
 assert not p.exists() and not p.is_symlink(), 'Existing file conflict'
 assert not p.parent.is_symlink()
 yaml.safe_load(content)
backup=root/'.jns-backups'/('boiler-runtime-'+sys.argv[2])
backup.mkdir(parents=True,exist_ok=False)
manifest={'files':{rel:hashlib.sha256(content.encode()).hexdigest() for rel,content in payload.items()},'previously_absent':True,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
written=[]
try:
 for rel,content in payload.items():
  p=root/rel
  p.parent.mkdir(parents=True,exist_ok=True)
  fd,tmp=tempfile.mkstemp(prefix='.jns-boiler-',dir=str(p.parent))
  try:
   with os.fdopen(fd,'w') as f:
    f.write(content);f.flush();os.fsync(f.fileno())
   os.chmod(tmp,0o644)
   # Exclusive create: do not replace concurrent edits.
   os.link(tmp,p)
   written.append(p)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
except Exception:
 for p in written:
  rel=str(p.relative_to(root))
  if hashlib.sha256(p.read_bytes()).hexdigest()==manifest['files'][rel]:p.unlink()
 raise
print(json.dumps({'backup':str(backup),'hashes':manifest['files']}))
'''

ROLLBACK = r'''
import pathlib,json,hashlib,sys
b=pathlib.Path(sys.argv[1]);root=pathlib.Path('/config')
assert b.parent==root/'.jns-backups' and b.name.startswith('boiler-runtime-')
m=json.loads((b/'manifest.json').read_text())
assert m['previously_absent']
for rel,sha in m['files'].items():
 p=root/rel
 assert not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==sha,'Concurrent edit; do not clobber'
for rel in m['files']:(root/rel).unlink()
print('BOILER_ORIGINAL_CONFIGURATION_RESTORED')
'''

def background(label, command, seconds):
    runid=os.environ['GITHUB_RUN_ID']
    assert runid.isdecimal() and label in ('check','restart')
    base='/tmp/jns-boiler-'+label+'-'+runid
    shell='test ! -e '+base+'.rc || exit 7; ( timeout '+str(seconds)+' '+command+' >'+base+'.out 2>&1; echo $? >'+base+'.rc ) </dev/null >/dev/null 2>&1 & echo STARTED'
    r=guest(['sh','-c',shell])
    if r.get('exitcode')!=0 or 'STARTED' not in r.get('out-data',''):
        raise RuntimeError('Background operation not confirmed')
    until=time.monotonic()+seconds+30
    while time.monotonic()<until:
        time.sleep(5)
        r=guest(['sh','-c','if test -f '+base+'.rc; then cat '+base+'.rc; else echo PENDING; fi'])
        ans=r.get('out-data','').strip()
        if ans=='PENDING':continue
        if r.get('exitcode')!=0 or not ans.isdecimal():raise RuntimeError('Background operation status unknown')
        print('BOILER_OPERATION',label,'exit',ans,flush=True)
        if int(ans)!=0:
            # Config checker output can contain unrelated private settings; report counts only.
            r=guest(['sh','-c','wc -l < '+base+'.out'])
            print('BOILER_FAILED_OPERATION_LOG_LINES',r.get('out-data','').strip(),flush=True)
        return int(ans)==0
    raise RuntimeError('Background operation timeout; inspect before retry')

VERIFY = r'''
import pathlib,json,sqlite3,time,datetime
root=pathlib.Path('/config')
ids=['binary_sensor.jns_boiler_heating_demand','binary_sensor.jns_boiler_monitoring_available','sensor.jns_boiler_runtime_rate','sensor.jns_boiler_runtime_total','sensor.jns_boiler_runtime_today','sensor.jns_boiler_runtime_this_month']
reg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
registered={e['entity_id'] for e in reg if not e.get('disabled_by')}
assert set(ids)<=registered, 'Expected boiler entities not registered'
con=sqlite3.connect('file:/config/home-assistant_v2.db?mode=ro',uri=True,timeout=4)
rows={}
for eid in ids:
 row=con.execute('SELECT state,shared_attrs,last_updated_ts FROM states s JOIN states_meta USING(metadata_id) LEFT JOIN state_attributes a ON s.attributes_id=a.attributes_id WHERE entity_id=? ORDER BY last_updated_ts DESC LIMIT 1',(eid,)).fetchone()
 assert row, 'Expected recorded entity missing'
 attrs=json.loads(row[1] or '{}')
 rows[eid]={'state':row[0],'unit':attrs.get('unit_of_measurement'),'state_class':attrs.get('state_class')}
 if eid.startswith('sensor.'):
  assert row[0] not in ('unknown','unavailable'), 'Runtime sensor not active'
  float(row[0])
  if eid!='sensor.jns_boiler_runtime_rate':
   assert attrs.get('unit_of_measurement')=='h','Runtime hours unit missing'
   assert attrs.get('state_class') in ('total','total_increasing'),'Long term statistics missing'
con.close()
assert (root/'dashboards/jns_boiler_monitor.yaml').is_file()
print('BOILER_LIVE_VERIFIED',json.dumps(rows,sort_keys=True))
'''

def main():
    assert 'running' in ssh_host('nodeb',['qm','status','905'])
    runid=os.environ['GITHUB_RUN_ID']
    assert runid.isdecimal()
    payload={'packages/jns_boiler_monitor.yaml':(HERE/'package.yaml').read_text(),'dashboards/jns_boiler_monitor.yaml':(HERE/'dashboard.yaml').read_text()}
    record=json.loads(core(INSTALL,base64.b64encode(json.dumps(payload).encode()).decode(),runid))
    print('BOILER_FILES_ADDED',json.dumps(record),flush=True)
    try:
        # Native Core checker avoids the previously failing Supervisor check call.
        if not background('check','docker exec homeassistant python3 -m homeassistant --script check_config --config /config',210):
            raise RuntimeError('Home Assistant configuration rejected addition')
    except Exception:
        print(core(ROLLBACK,record['backup']),flush=True)
        raise
    print('BOILER_CONFIG_VALIDATED',flush=True)
    if not background('restart','ha core restart',180):
        raise RuntimeError('Core restart not confirmed; no automatic retry')
    print('BOILER_CORE_RESTART_COMPLETED',flush=True)
    # Allow restored helpers, one-minute integration update and recorder flush.
    for i in range(18):
        time.sleep(10)
        try:
            output=core(VERIFY)
            print(output,flush=True)
            print('BOILER_DEPLOYMENT_VERIFIED',flush=True)
            return
        except Exception:
            print('BOILER_WAITING_FOR_RECORDED_ENTITIES',i+1,flush=True)
    raise RuntimeError('Post restart monitoring verification failed; inspect before changes')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('BOILER_DEPLOYMENT_BLOCKED',type(e).__name__,str(e)[:180],flush=True)
        sys.exit(2)
