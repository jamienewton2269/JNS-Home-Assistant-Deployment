#!/usr/bin/env python3
"""VM905 Temperature Trends display-only telemetry expansion; no Core restart."""
import base64,importlib.util,json,os,pathlib
spec=importlib.util.spec_from_file_location("jns_bridge",pathlib.Path("gateway/heating_presence/deploy.py"))
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
INNER=r"""
import hashlib,json,os,pathlib,stat,sys,tempfile,yaml
p=pathlib.Path('/config/dashboards/testing.yaml')
before=p.read_bytes();cfg=yaml.safe_load(before);views=cfg.get('views',[])
v=[v for v in views if v.get('path')=='temperature-trends']
assert len(v)==1,'Temperature trends missing or duplicated'
cards=v[0]['cards']
matching=[c for c in cards if c.get('title')=='Current thermometers and forecast' and c.get('type')=='entities']
assert len(matching)==1,'Expected existing native temperature list missing'
required=[
 {'entity':'sensor.jns_hallway_house_temperature','name':'Hallway (authoritative model input)'},
 {'entity':'sensor.jns_fireplace_temperature','name':'Fireplace monitored temperature'},
 {'entity':'binary_sensor.jns_fireplace_heat_detected','name':'Fireplace sustained heat'},
 {'entity':'binary_sensor.jns_fireplace_override_safe','name':'Automatic suppression protection (blocked until trained)'},
 {'entity':'sensor.jns_hallway_weather_input_status','name':'Open-Meteo hourly forecast health'},
 {'entity':'sensor.jns_hallway_hourly_open_meteo','name':'Hourly weather feed'},
 {'entity':'sensor.jns_hallway_adaptive_warmup_minutes','name':'Measured hallway warmup lead time'},
 {'entity':'input_number.jns_hallway_warmup_observations','name':'Accepted hallway heating cycles'},
 {'entity':'sensor.jns_hallway_predicted_60m_while_heating','name':'Forecast hallway +60 min while heating'}]
already={x.get('entity') for x in matching[0]['entities'] if isinstance(x,dict)}
assert not any(x['entity'] in already for x in required),'Source status card already updated'
registered={e['entity_id'] for e in
 json.loads(pathlib.Path('/config/.storage/core.entity_registry').read_text())['data']['entities']
 if not e.get('disabled_by')}
assert all(x['entity'] in registered for x in required),'Some observer entities not registered; postpone view'
text=before.decode()
start=text.index('  path: temperature-trends')
end=text.find('\n- title:',start)
if end<0:end=len(text)
region=text[start:end]
title='  title: Current thermometers and forecast'
title_at=region.find(title)
assert title_at>=0,'Expected native card title missing'
pos=region.find('    entities:',title_at)
assert pos>=0
insert=start+pos+len('    entities:')
# Add after exact card entities key, and before existing entries.
lines=''.join('\n    - entity: '+x['entity']+'\n      name: '+x['name'] for x in required)
newdata=(text[:insert]+lines+text[insert:]).encode()
new=yaml.safe_load(newdata)
assert len(new['views'])==len(views)
for i in range(len(views)):
 if views[i].get('path')!='temperature-trends':
  assert new['views'][i]==views[i],'Other view modified'
changed=[c for c in new['views'][views.index(v[0])]['cards'] if c.get('title')=='Current thermometers and forecast']
assert len(changed)==1
assert all(x in changed[0]['entities'] for x in required)
h=lambda x:hashlib.sha256(x).hexdigest()
print('JNS_TRENDS_INPUTS_PLAN '+json.dumps({
 'before_sha256':h(before),'after_sha256':h(newdata),'views':len(views),
 'new_entities':len(required),'no_thermostat_changes':True},sort_keys=True),flush=True)
if '--apply' not in sys.argv:sys.exit(0)
runid=sys.argv[2];assert runid.isdecimal()
bdir=pathlib.Path('/config/.jns-backups')/('hallway-weather-trends-'+runid)
bdir.mkdir(mode=0o700,parents=True,exist_ok=False)
backup=bdir/'testing.yaml';backup.write_bytes(before);backup.chmod(0o600)
assert h(backup.read_bytes())==h(before) and p.read_bytes()==before
st=p.stat();fd,tmp=tempfile.mkstemp(prefix='.jns-hallway-ui-',dir=str(p.parent))
try:
 with os.fdopen(fd,'wb') as f:f.write(newdata);f.flush();os.fsync(f.fileno())
 os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode))
 assert p.read_bytes()==before
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
assert h(p.read_bytes())==h(newdata)
print('JNS_TRENDS_INPUTS_APPLIED '+json.dumps({
 'views_preserved':len(views),'new_entities':len(required),
 'sha256':h(newdata),'no_core_restart':True},sort_keys=True),flush=True)
"""
def main():
 runid=os.environ.get('GITHUB_RUN_ID','')
 if not runid.isdecimal():raise RuntimeError('Runner identity missing')
 for flag in ('--dry-run','--apply'):
  r=bridge.core(INNER,[flag,runid],seconds=100)
  if r.get('exitcode')!=0:raise RuntimeError('HA trends card guard rejected')
  out=r.get('out-data') or ''
  label='JNS_TRENDS_INPUTS_APPLIED ' if flag=='--apply' else 'JNS_TRENDS_INPUTS_PLAN '
  if label not in out:raise RuntimeError('Trends report missing')
  print(next(x for x in out.splitlines() if x.startswith(label)),flush=True)
if __name__=='__main__':main()
