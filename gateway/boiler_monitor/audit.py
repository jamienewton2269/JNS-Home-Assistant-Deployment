#!/usr/bin/env python3
"""Read-only scoped boiler preflight through existing JNS guest transport."""
import sys,json
import base64,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
def core(src):
 code="exec(__import__('base64').b64decode("+repr(base64.b64encode(src.encode()).decode())+"))"
 r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code]))
 until=time.monotonic()+70
 while not r.get("exited"):
  if not isinstance(r.get("pid"),int): raise RuntimeError("Guest read-only status unavailable")
  if time.monotonic()>until: raise RuntimeError("Guest read-only timeout")
  time.sleep(2)
  r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
 return r
P=r"""
import json,pathlib,sqlite3,os,urllib.request
root=pathlib.Path('/config')
cfg=(root/'configuration.yaml').read_text()
print('PACKAGE_INCLUDE',json.dumps([x.strip() for x in cfg.splitlines() if 'packages:' in x]))
reg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
print('LYRIC_REGISTRY',json.dumps([{k:e.get(k) for k in ('entity_id','platform','disabled_by')} for e in reg if e.get('platform')=='lyric']))
print('EXISTING_BOILER_FILES',json.dumps([p.name for p in (root/'packages').glob('*') if 'boiler' in p.name.lower()]))
db=sqlite3.connect('file:/config/home-assistant_v2.db?mode=ro',uri=True,timeout=3)
row=db.execute("SELECT state,shared_attrs,last_updated_ts FROM states s JOIN states_meta m USING(metadata_id) LEFT JOIN state_attributes a ON s.attributes_id=a.attributes_id WHERE m.entity_id=? ORDER BY s.last_updated_ts DESC LIMIT 1",('climate.thermostat_thermostat',)).fetchone()
attrs=json.loads(row[1] or '{}') if row else {}
print('LYRIC_RECORDED_ACTIVITY',json.dumps({'state':row[0] if row else None,'at':row[2] if row else None,'hvac_action':attrs.get('hvac_action'),'attribute_keys':list(attrs)}))
print('RECORDER_ROOT',any(x.startswith('recorder:') for x in cfg.splitlines()))
print('HTTP_CONFIG_LINES',json.dumps([x.strip() for x in cfg.splitlines() if 'server_port:' in x]))
# Source schema, not auth or user configuration.
import homeassistant.components.lyric.climate as lc,inspect
src=inspect.getsource(lc)
ls=src.splitlines()
for i,line in enumerate(ls):
 if 'def hvac_action' in line:
  print('LYRIC_ACTIVITY_IMPLEMENTATION','\n'.join(ls[i:i+30]))
"""
r=core(P)
print(r.get('out-data',''))
if r.get('exitcode')!=0:
 print('BOILER_PREFLIGHT_FAILED',str(r.get('err-data',''))[-800:])
 raise SystemExit(2)
