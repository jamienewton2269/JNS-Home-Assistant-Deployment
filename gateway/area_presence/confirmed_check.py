#!/usr/bin/env python3
"""Read-only current MQTT integration, targeted YAML, existing areas on HA-Primary."""
import base64,json,time,sys
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
CODE=r"""
import json
from pathlib import Path
root=Path('/config'); store=root/'.storage'
es=json.loads((store/'core.entity_registry').read_text())['data']['entities']
entries=json.loads((store/'core.config_entries').read_text())['data']['entries']
areas=json.loads((store/'core.area_registry').read_text())['data']['areas']
d={
  'mqtt':[{'source':x.get('source'),'disabled_by':x.get('disabled_by'),'entry_id_present':bool(x.get('entry_id'))} for x in entries if x.get('domain')=='mqtt'],
  'areas':[{'id':x.get('id'),'name':x.get('name')} for x in areas],
  'config_root_keys':[l.strip().split(':')[0] for l in (root/'configuration.yaml').read_text().splitlines() if l and not l[0].isspace() and not l.startswith('#')][:70],
  'presence_entitites':[{'entity':x.get('entity_id'),'disabled_by':x.get('disabled_by')} for x in es if x.get('entity_id') in ('device_tracker.sm_s721b','sensor.sm_s721b_wi_fi_connection')],
  'area_sync_custom_exists':(root/'custom_components/jns_native_area_sync').exists(),
  'welcome_package_exists':(root/'packages/jns_welcome_home.yaml').exists(),
  'statestream_exists':'mqtt_statestream:' in (root/'configuration.yaml').read_text(),
  'mqtt_manifest_name':next((x.get('title') for x in entries if x.get('domain')=='mqtt'),None),
}
print(json.dumps(d,sort_keys=True))
"""
arg="exec(__import__('base64').b64decode("+repr(base64.b64encode(CODE.encode()).decode())+"))"
r=json.loads(ssh_host('nodea',['qm','guest','exec','902','--','docker','exec','homeassistant','python3','-c',arg]));pid=r.get('pid')
for _ in range(50):
 if r.get('exited'):break
 if not isinstance(pid,int):raise RuntimeError('missing guest PID')
 time.sleep(1)
 r=json.loads(ssh_host('nodea',['qm','guest','exec-status','902',str(pid)]))
if r.get('exitcode')!=0 or not r.get('exited'):raise RuntimeError('read-only inspect failed '+(r.get('err-data') or '')[-280:])
print('JNS_PRIMARY_MQTT_CURRENT',r.get('out-data','').strip(),flush=True)
