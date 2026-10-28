#!/usr/bin/env python3
"""Read-only, independent post-restart check of HA-General bedtime thermostat action."""
import base64,json,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
P=r'''
import json,pathlib,hashlib,yaml,urllib.request,urllib.error
root=pathlib.Path('/config');p=root/'packages/jns_bedtime_controller.yaml'
d=yaml.safe_load(p.read_text())
a=[x for x in d.get('automation',[]) if x.get('id')=='jns_bedtime_trigger_on_mode']
assert len(a)==1
actions=a[0]['actions']
assert len(actions)==2
assert actions[0]=={'action':'climate.set_temperature','target':{'entity_id':'climate.thermostat_thermostat'},'data':{'temperature':18},'continue_on_error':True}
assert actions[1]=={'action':'script.jns_bedtime_shutdown'}
reg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
climate=[x for x in reg if x.get('entity_id')=='climate.thermostat_thermostat' and not x.get('disabled_by')]
autos=[{'entity_id':x.get('entity_id'),'disabled':x.get('disabled_by'),'unique_id':x.get('unique_id')} for x in reg if x.get('platform')=='automation' and (x.get('unique_id')=='jns_bedtime_trigger_on_mode' or 'jns_bedtime_dashboard_or_hallway_activation' in str(x.get('entity_id')))]
results=[]
for port in (80,8123):
 try:
  req=urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/',method='GET')
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with opener.open(req,timeout=3) as r:status=r.status
 except urllib.error.HTTPError as e:status=e.code
 except Exception as e:status=type(e).__name__
 results.append({'port':port,'http_status':status})
print('JNS_HEATING18_LIVE_VERIFY',json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'target_celsius':18,'bedtime_script_preserved':True,'climate_enabled':len(climate)==1,'bedtime_automations':autos[:5],'core_api_status':results}))
'''
def guest(args):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 for i in range(30):
  if r.get('exited'):return r
  if not isinstance(r.get('pid'),int):raise RuntimeError('No QGA PID')
  time.sleep(1)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 raise RuntimeError('Read-only inspection timed out')
def run(label,args):
 r=guest(args)
 print('JNS_HEAT18_VERIFY_'+label,json.dumps({'rc':r.get('exitcode'),'stdout':(r.get('out-data') or '')[-3500:],'error':(r.get('err-data') or '')[-180:]}),flush=True)
 if r.get('exitcode')!=0:raise RuntimeError('Read-only '+label+' failed')
print('JNS_HEAT18_INDEPENDENT_POSTCHECK_START',flush=True)
print('VM905',ssh_host('nodeb',['qm','status','905']).strip(),flush=True)
run('CONTAINER_START',['docker','inspect','--format','{{.State.Running}} {{.State.StartedAt}}','homeassistant'])
run('CORE_INFO',['ha','core','info'])
encoded=base64.b64encode(P.encode()).decode()
run('BEDTIME_RUNTIME',['docker','exec','homeassistant','python3','-c',"exec(__import__('base64').b64decode("+repr(encoded)+"))"])
print('JNS_HEATING18_POSTCHECK_COMPLETE',flush=True)
