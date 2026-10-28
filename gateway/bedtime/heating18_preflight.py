#!/usr/bin/env python3
"""JNS read-only VM905 bedtime/thermostat integration assessment."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
PROBE=r'''
import json,pathlib,yaml,re,hashlib
root=pathlib.Path('/config')
target=root/'packages/jns_bedtime_controller.yaml'
pkg=yaml.safe_load(target.read_text())
reg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
wanted=['climate.thermostat_thermostat','input_boolean.general_bedtime_mode','script.jns_bedtime_shutdown']
found=[{'id':e.get('entity_id'),'platform':e.get('platform'),'disabled':e.get('disabled_by'),'original_name':e.get('original_name')} for e in reg if e.get('entity_id') in wanted]
autos=[]
for a in pkg.get('automation',[]):
 if isinstance(a,dict) and re.search('bedtime|morning|wake|sunrise',str(a.get('alias','')),re.I):
  autos.append({'id':a.get('id'),'alias':a.get('alias'),'triggers':a.get('triggers',a.get('trigger')),'actions':str(a.get('actions',a.get('action')))[:450]})
s=pkg['script'].get('jns_bedtime_shutdown')
seq=s.get('sequence',[]) if isinstance(s,dict) else []
actions=[]
for item in seq:
 if isinstance(item,dict):
  actions.append({'keys':list(item.keys()),'action':item.get('action'),'target':item.get('target')})
references=[]
for p in [root/'automations.yaml',*(root/'packages').glob('*.yaml')]:
 try:
  data=p.read_text()
 except Exception:continue
 if re.search('climate\.thermostat_thermostat|general_bedtime_mode|jns_bedtime_shutdown',data):
  matches=[(i,line[:220]) for i,line in enumerate(data.splitlines(),1) if re.search('climate\.thermostat_thermostat|general_bedtime_mode|jns_bedtime_shutdown|climate.set_temperature',line)]
  references.append({'path':str(p.relative_to(root)),'matches':matches[:22]})
print('JNS_HEATING_BEDTIME_READONLY',json.dumps({'bedtime_package_hash':hashlib.sha256(target.read_bytes()).hexdigest(),'registered':found,'package_bedtime_automations':autos[:18],'shutdown_action_steps':actions[:18],'heating_control_references':references[:30]},default=str))
'''
def guest(a,seconds=55):
    r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*a]))
    end=time.monotonic()+seconds
    while not r.get('exited'):
        if not isinstance(r.get('pid'),int):raise RuntimeError('QGA async status unknown')
        if time.monotonic()>end:raise RuntimeError('QGA probe timeout')
        time.sleep(2)
        r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
    return r
print('JNS_HA905_BEDTIME_HEATING_PREFLIGHT_START',flush=True)
print('VM905_STATUS',ssh_host('nodeb',['qm','status','905']).strip(),flush=True)
cmd="exec(__import__('base64').b64decode("+repr(base64.b64encode(PROBE.encode()).decode())+"))"
r=guest(['docker','exec','homeassistant','python3','-c',cmd])
print('JNS_HA905_BEDTIME_HEATING_PREFLIGHT_RESULT',(r.get('out-data') or '')[-14500:],flush=True)
if r.get('exitcode')!=0:raise RuntimeError('Read-only bedside check failed '+str(r.get('err-data') or '')[-300:])
