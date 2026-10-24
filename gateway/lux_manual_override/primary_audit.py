#!/usr/bin/env python3
"""Read-only HA902 dashboard layout, VM905 eligible lights and exact lux branches."""
import base64,json,time,sys
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
SCAN=r"""
from pathlib import Path
import json,yaml,re
root=Path('/config');st=root/'.storage'
es=json.loads((st/'core.entity_registry').read_text())['data']['entities']
ds={d.get('id'):d for d in json.loads((st/'core.device_registry').read_text())['data']['devices']} if (st/'core.device_registry').exists() else {}
labels={l.get('label_id') or l.get('id'):l.get('name') for l in json.loads((st/'core.label_registry').read_text())['data']['labels']} if (st/'core.label_registry').exists() else {}
if VM==905:
 a=yaml.safe_load((root/'automations.yaml').read_text())
 entry=[x for x in a if str(x.get('id'))=='1791918795028']
 assert len(entry)==1
 x=entry[0]
 print('LUX_MAIN',yaml.safe_dump(x,sort_keys=False,allow_unicode=True,width=170)[:35000])
 print('LUX_LABEL_ENTITIES')
 for e in es:
  eid=e.get('entity_id','')
  if not eid.startswith(('light.','switch.')):continue
  d=ds.get(e.get('device_id'),{})
  ls=[labels.get(v,v) for v in e.get('labels',[]) or []]
  ls+= [labels.get(v,v) for v in d.get('labels',[]) or []]
  if any(q in ls for q in ('Lighting: Lux Controlled','Purpose: Standard Light')):
   print(json.dumps({'entity_id':eid,'labels':ls,'device':d.get('name_by_user') or d.get('name'),
                    'disabled':e.get('disabled_by')}))
 print('LUX_CORE_DASHBOARD')
 p=root/'dashboards/testing.yaml'
 if p.exists():
  v=yaml.safe_load(p.read_text())
  print('views',[(x.get('title'),x.get('path')) for x in v.get('views',[])])
else:
 cfg=(root/'configuration.yaml').read_text()
 print('PRIMARY_CONFIGURATION_DASHBOARD_LINES')
 for line in cfg.splitlines():
  if re.search('lovelace|dashboards:|remote_homeassistant|remote_home_assistant|panel_',line):
   print(line[:170])
 print('PRIMARY_DASHBOARDS')
 for p in sorted((root/'dashboards').glob('*.yaml')) if (root/'dashboards').exists() else []:
  try:
   v=yaml.safe_load(p.read_text())
   if isinstance(v,dict): print(p.name,[(x.get('title'),x.get('path')) for x in v.get('views',[])][:15])
  except Exception as ex:print(p.name,'unreadable',type(ex).__name__)
 try:
  js=json.loads((st/'lovelace_dashboards').read_text())
  for entry in js.get('data',{}).get('items',[]):
   print('PRIMARY_LOVELACE_DASHBOARD',json.dumps({'url_path':entry.get('url_path'),'mode':entry.get('mode'),'title':entry.get('title')},sort_keys=True))
 except Exception as ex:print('PRIMARY_LOVELACE_REGISTRY',type(ex).__name__)
 print('PRIMARY_MAIN_UI_STORAGE')
 for path in sorted(st.glob('lovelace*')):
  print(path.name,path.stat().st_size)
 print('PRIMARY_REMOTE_ENTITIES')
 for e in es:
  eid=e.get('entity_id','')
  if 'jns_lux' in eid or ('remote' in (e.get('platform') or '')):
   print(eid,e.get('platform'),e.get('disabled_by'))
"""
def scan(vm,node):
 s=SCAN.replace("VM==905",str(vm)+"==905")
 arg="exec(__import__('base64').b64decode("+repr(base64.b64encode(s.encode()).decode())+"))"
 r=json.loads(ssh_host(node,['qm','guest','exec',str(vm),'--','docker','exec','homeassistant','python3','-c',arg]));pid=r.get('pid')
 for _ in range(60):
  if r.get('exited'):break
  if not isinstance(pid,int):raise RuntimeError('missing guest pid')
  time.sleep(1);r=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(pid)]))
 if not r.get('exited') or r.get('exitcode')!=0:raise RuntimeError('Guest read failed '+(r.get('err-data') or '')[-350:])
 return r.get('out-data','')
for vm,node in [(905,'nodeb'),(902,'nodea')]:
 try:print('VM'+str(vm)+'_CONTROL_AUDIT\n'+scan(vm,node)[:61000])
 except Exception as ex:print('VM'+str(vm)+'_CONTROL_BLOCKED',type(ex).__name__,str(ex)[:150])
