#!/usr/bin/env python3
"""Read-only live VM905 Lux staging/priority/dashboard audit via JNS trusted Node C gateway."""
import sys,json,base64,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
INSPECT=r'''
import json,hashlib,pathlib,yaml,re
R=pathlib.Path("/config")
a=R/"automations.yaml"; p=R/"packages/jns_lux_manual_off_v1.yaml";dash=R/"dashboards/testing.yaml"
autom=yaml.safe_load(a.read_bytes())
lux=[x for x in autom if str(x.get('id'))=="1791918795028"]
assert len(lux)==1,"shared Lux automation missing or duplicate"
reg=json.loads((R/'.storage/core.entity_registry').read_text())['data']['entities']
labelreg=json.loads((R/'.storage/core.label_registry').read_text()).get('data',{}).get('labels',[])) if (R/'.storage/core.label_registry').exists() else []
light=[{'id':e.get('entity_id'),'area':e.get('area_id'),'labels':e.get('labels'),'disabled':e.get('disabled_by'),'name':e.get('name') or e.get('original_name')} for e in reg if str(e.get('entity_id','')).startswith(('light.','switch.')) and not e.get('disabled_by')]
d=yaml.safe_load(dash.read_bytes())
views={v.get('path'):v for v in d.get('views',[]) if v.get('path') in ('lighting-settings','evening-lighting','controls')}
packagefiles={}
for pp in sorted((R/'packages').glob('*.yaml')):
 if re.search(r'lux|dusk|lighting',pp.name,re.I):
  packagefiles[pp.name]={'sha':hashlib.sha256(pp.read_bytes()).hexdigest(),'head':pp.read_text()[:340]}
obj={'controller':lux[0],
     'hashes':{'automations':hashlib.sha256(a.read_bytes()).hexdigest(),'dashboard':hashlib.sha256(dash.read_bytes()).hexdigest(),'manual_off':hashlib.sha256(p.read_bytes()).hexdigest()},
     'manual_off':yaml.safe_load(p.read_bytes()),
     'labels':[{'id':x.get('label_id'), 'name':x.get('name')} for x in labelreg],
     'light_entities':light[:200],
     'views':views,
     'lux_package_files':packagefiles}
print("JNS_LUX_PRIORITY_INSPECT "+json.dumps(obj,sort_keys=True,default=str))
'''
def guest(argv):
 r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*argv]))
 deadline=time.monotonic()+85
 while not r.get('exited'):
  if not isinstance(r.get('pid'),int):raise RuntimeError('QGA missing PID')
  if time.monotonic()>deadline:raise RuntimeError('VM905 QGA check incomplete')
  time.sleep(2)
  r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r['pid'])]))
 return r
print("JNS_LUX_AUDIT_VM905",ssh_host('nodeb',['qm','status','905']).strip(),flush=True)
prog="exec(__import__('base64').b64decode("+repr(base64.b64encode(INSPECT.encode()).decode())+"))"
r=guest(['docker','exec','homeassistant','python3','-c',prog])
print((r.get('out-data') or '')[-49000:],flush=True)
if r.get('exitcode')!=0:raise RuntimeError('read only Lux inspection failed: '+(r.get('err-data') or '')[-250:])
