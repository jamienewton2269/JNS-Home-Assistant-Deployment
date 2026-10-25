#!/usr/bin/env python3
"""Read-only live Zigbee/HA-General entity naming audit. Never logs credentials."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
TARGETS=[
"0xa4c13833916ae7d1","0xa4c1383917c90309",
"0xa4c1386faf69d5e0","0xa4c138cf0342f0d9",
]
INSPECT=r'''
import json,os,importlib.util
from pathlib import Path
TARGETS=['0xa4c13833916ae7d1','0xa4c1383917c90309','0xa4c1386faf69d5e0','0xa4c138cf0342f0d9']
store=Path('/config/.storage')
entities=json.loads((store/'core.entity_registry').read_text())['data']['entities']
devices=json.loads((store/'core.device_registry').read_text())['data']['devices']
devmap={d.get('id'):d for d in devices}
out=[]
for d in devices:
    identifiers=' '.join(str(x) for x in d.get('identifiers',[])).lower()
    search=' '.join(str(d.get(k) or '') for k in ('name','name_by_user','model')).lower()
    links=[e for e in entities if e.get('device_id')==d.get('id')]
    matched=any(t in identifiers or any(t in ' '.join(str(e.get(k) or '') for k in ('entity_id','unique_id','name','original_name')).lower() for e in links) for t in TARGETS)
    if not matched: continue
    out.append({'device':{'name':d.get('name'),'name_by_user':d.get('name_by_user'),'manufacturer':d.get('manufacturer'),'model':d.get('model'),'identifiers':d.get('identifiers')},
      'entities':[{'id':e.get('entity_id'),'unique_id':e.get('unique_id'),'name':e.get('name'),'original_name':e.get('original_name'),
       'platform':e.get('platform'),'category':e.get('entity_category'),'disabled_by':e.get('disabled_by'),'has_custom_id':bool(e.get('id'))}
       for e in links if e.get('entity_id','').startswith(('sensor.','binary_sensor.'))]})
orphan=[{'id':e.get('entity_id'),'unique_id':e.get('unique_id'),'name':e.get('name'),'original_name':e.get('original_name'),'platform':e.get('platform')} for e in entities if e.get('device_id') not in devmap and any(t in str(e.get('entity_id'))+str(e.get('unique_id')) for t in TARGETS)]
print('JNS_SENSOR_NAMES_AUDIT '+json.dumps({'devices':out,'orphan_entities':orphan,
 'api_capabilities':{'supervisor_token_present':bool(os.environ.get('SUPERVISOR_TOKEN')),
 'websocket_client':importlib.util.find_spec('websocket') is not None,
 'websockets':importlib.util.find_spec('websockets') is not None,
 'aiohttp':importlib.util.find_spec('aiohttp') is not None}},ensure_ascii=False))
'''
arg="exec(__import__('base64').b64decode("+repr(base64.b64encode(INSPECT.encode()).decode())+"))"
cmd=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',arg]
response=json.loads(ssh_host('nodeb',cmd))
pid=response.get('pid')
for _ in range(45):
    if response.get('exited'): break
    if not isinstance(pid,int):raise RuntimeError("VM905 guest agent returned no PID")
    time.sleep(1)
    response=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
if not response.get('exited') or response.get('exitcode')!=0:
    raise RuntimeError("VM905 live entity read failed")
print((response.get('out-data') or '')[:20000],flush=True)
