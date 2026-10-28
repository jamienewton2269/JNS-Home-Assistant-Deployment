#!/usr/bin/env python3
"""Read-only predictive-heating engine and alarm state ownership audit."""
import base64,json,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
INSPECT=r'''
import pathlib,json,re,yaml
root=pathlib.Path('/config')
files=['custom_components/jns_heating_zones/coordinator.py','custom_components/jns_heating_zones/thermal.py',
       'custom_components/jns_heating_zones/const.py','custom_components/jns_heating_zones/config_flow.py','custom_components/jns_heating_zones/__init__.py']
out={'files':{},'heat_config_entries':[], 'alarm_registry':[],'dashboard_controls':[]}
for name in files:
 p=root/name
 if p.is_file():
  lines=p.read_text().splitlines()
  if name.endswith('config_flow.py'):lines=[x[:200] for x in lines if 'CONF_' in x or 'schema' in x.lower() or 'target' in x.lower()]
  out['files'][name]='\n'.join(lines[:265])[:15500]
for p in [root/'dashboards/testing.yaml']:
 data=yaml.safe_load(p.read_text())
 for v in data.get('views',[]):
  if v.get('path') in ['controls','house-temperature']:
   out['dashboard_controls'].append({'path':v.get('path'),'first_cards':v.get('cards',[])[:7]})
try:
 d=json.loads((root/'.storage/core.config_entries').read_text())['data']['entries']
 for x in d:
  if x.get('domain')=='jns_heating_zones':
   out['heat_config_entries'].append({'entry_id':str(x.get('entry_id'))[:12],'title':x.get('title'),
      'data':{k:v for k,v in x.get('data',{}).items() if not any(s in k.lower() for s in ['token','secret','password','key'])},
      'options':{k:v for k,v in x.get('options',{}).items() if not any(s in k.lower() for s in ['token','secret','password','key'])}})
except Exception as e:out['config_error']=type(e).__name__
try:
 es=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
 out['alarm_registry']=[{'id':e.get('entity_id'),'disabled':e.get('disabled_by')} for e in es if e.get('entity_id','').startswith('alarm_control_panel.')]
except:pass
print('JNS_HEAT_ENGINE_DETAIL',json.dumps(out,default=str))
'''
def guest(node,vm,source=INSPECT):
 b64=base64.b64encode(source.encode()).decode()
 cmd="exec(__import__('base64').b64decode("+repr(b64)+"))"
 resp=json.loads(ssh_host(node,['qm','guest','exec',str(vm),'--','docker','exec','homeassistant','python3','-c',cmd]))
 for i in range(30):
  if resp.get('exited'):break
  if not isinstance(resp.get('pid'),int):raise RuntimeError('missing pid')
  time.sleep(1)
  resp=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(resp['pid'])]))
 if resp.get('exitcode')!=0:raise RuntimeError('guest check fail '+str(resp.get('err-data') or '')[-250:])
 return resp.get('out-data') or ''
print('JNS_HEAT_ENGINE_OWNER_AUDIT_START',flush=True)
print(guest('nodeb',905)[-42000:],flush=True)
OWNER=r'''
import json,pathlib
p=pathlib.Path('/config/.storage/core.entity_registry')
d=json.loads(p.read_text())['data']['entities']
print('ALARM_ENTITY_OWNER',json.dumps({'alarms':[{'id':e.get('entity_id'),'platform':e.get('platform'),'disabled':e.get('disabled_by')} for e in d if e.get('entity_id','').startswith('alarm_control_panel.')]}))
'''
for node,vm in [('nodec',906),('nodea',902)]:
 try:
  out=guest(node,vm,OWNER)
  print('OTHER_NODE',node,vm,out[-2200:],flush=True)
 except Exception as e:print('OTHER_NODE_UNAVAILABLE',node,vm,type(e).__name__,str(e)[:160],flush=True)
