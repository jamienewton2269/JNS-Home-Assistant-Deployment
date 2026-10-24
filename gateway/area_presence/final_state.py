#!/usr/bin/env python3
"""Read-only final deployment state: benign status and retained area report timestamp."""
import base64,json,time,sys
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
SCRIPT=r"""
import json
from pathlib import Path
p=Path('/config');s=p/'.storage'
entities=json.loads((s/'core.entity_registry').read_text())['data']['entities']
out={'presence_automation_registry':[{'id':x.get('entity_id'),'disabled':bool(x.get('disabled_by'))} for x in entities if x.get('platform')=='automation' and 'welcome_home' in x.get('entity_id','')]}
state=s/'core.restore_state'
if state.exists():
 try:
  rows=json.loads(state.read_text())['data']
  if isinstance(rows,dict):rows=rows.get('states',[])
  out['restore_state']={x['state']['entity_id']:x['state']['state'] for x in rows if isinstance(x,dict) and isinstance(x.get('state'),dict) and x['state'].get('entity_id') in ('input_boolean.jns_welcome_home_enabled','timer.jns_welcome_home')}
 except Exception as exc:out['restore_state_error']=type(exc).__name__
print(json.dumps(out))
"""
arg="exec(__import__('base64').b64decode('"+base64.b64encode(SCRIPT.encode()).decode()+"'))"
r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',arg]))
for i in range(35):
 if r.get('exited'):break
 time.sleep(1)
 r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
print('JNS_WELCOME_SAFETY_STATUS',r.get('out-data','').strip() if r.get('exited') and r.get('exitcode')==0 else 'unavailable',flush=True)
report=ssh_host('nodeb',['pct','exec','212','--','timeout','7','mosquitto_sub','-h','mqtt-infra-a.home.arpa','-p','1883','-W','5','-C','1','-t','jns/site/areas/sync/ha-primary'])
data=json.loads(report)
print('JNS_AREA_REPORT_CONFIRMED',json.dumps({k:data.get(k) for k in ('generated_at','schema','mode','created','conflicts','missing','already_present')}),flush=True)
