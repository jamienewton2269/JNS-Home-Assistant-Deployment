#!/usr/bin/env python3
"""Read-only live verification; no changes, credentials, SSIDs or location states in logs."""
import base64,json,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host

PROBE=r"""
import json,hashlib
from pathlib import Path
b=Path('/config'); cfg=(b/'configuration.yaml').read_text()
entries=json.loads((b/'.storage/core.config_entries').read_text())['data']['entries']
es=json.loads((b/'.storage/core.entity_registry').read_text())['data']['entities']
def block(key):
 lines=cfg.splitlines(); out=[]; capture=False
 for line in lines:
  if line.startswith(key+':'):capture=True;continue
  if capture:
   if line and not line[0].isspace() and not line.startswith('#'): break
   out.append(line)
 return out
def whitelisted(lines,keys):
 return [line.strip() for line in lines if line.strip().split(':',1)[0] in keys]
area=(b/'custom_components/jns_native_area_sync/__init__.py')
last=[]
p=b/'home-assistant.log'
if p.exists():
 try:
  with p.open(errors='replace') as f:
   # No raw data printed, just aggregate counts of matching diagnostics
   from collections import deque
   lines=deque(f,maxlen=4000)
  last=[l for l in lines if 'jns_native_area_sync' in l or 'mqtt_statestream' in l]
 except Exception:pass
print(json.dumps({
 'statestream_exists':bool(block('mqtt_statestream')),
 'statestream_options':whitelisted(block('mqtt_statestream'),('base_topic','publish_attributes','publish_timestamps')),
 'statestream_included_entities':[x.strip()[2:] for x in block('mqtt_statestream') if x.lstrip().startswith('- ') and ('device_tracker.' in x or 'sensor.' in x)],
 'area_sync_options':whitelisted(block('jns_native_area_sync'),('node','apply')),
 'area_component_sha256':hashlib.sha256(area.read_bytes()).hexdigest() if area.exists() else None,
 'area_component_exists':area.exists(),
 'mqtt_config_entries':len([x for x in entries if x.get('domain')=='mqtt']),
 'area_sync_log_mentions':len(last),
 'area_sync_log_error_mentions':sum(1 for l in last if ('ERROR' in l or 'WARNING' in l)),
 'welcome_package_exists':(b/'packages/jns_welcome_home.yaml').exists(),
 'welcome_automations':[x.get('entity_id') for x in es if x.get('platform')=='automation' and 'welcome_home' in str(x.get('entity_id'))]
},sort_keys=True))
"""
def inspect(vm,node):
 arg="exec(__import__('base64').b64decode('"+base64.b64encode(PROBE.encode()).decode()+"'))"
 r=json.loads(ssh_host(node,['qm','guest','exec',str(vm),'--','docker','exec','homeassistant','python3','-c',arg]))
 pid=r.get('pid')
 for i in range(45):
  if r.get('exited'): break
  if not isinstance(pid,int):raise RuntimeError('missing QGA pid')
  time.sleep(1)
  r=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(pid)]))
 if not r.get('exited') or r.get('exitcode')!=0:
  raise RuntimeError('VM'+str(vm)+' HA config inspect error '+(r.get('err-data') or '')[-300:])
 return json.loads(r.get('out-data') or '{}')
for vm,node in [(902,'nodea'),(905,'nodeb')]:
 try:print('JNS_MQTT_AREA_STATUS_VM'+str(vm),json.dumps(inspect(vm,node),sort_keys=True),flush=True)
 except Exception as e:print('JNS_MQTT_AREA_STATUS_VM'+str(vm)+'_BLOCKED',str(e)[:200],flush=True)
# Only read broker topic reports and topic names. Never disclose phone state payloads.
for topic in ['jns/site/areas/sync/ha-primary','jns/ha-primary/device_tracker/sm_s721b/state','jns/ha-primary/sensor/sm_s721b_wi_fi_connection/state']:
 try:
  option=['-F','%t']
  if topic=='jns/site/areas/sync/ha-primary':option=[]
  remote=['pct','exec','212','--','timeout','7','mosquitto_sub','-h','mqtt-infra-a.home.arpa','-p','1883','-W','5','-C','1','-t',topic]+option
  output=ssh_host('nodeb',remote).strip()
  if topic=='jns/site/areas/sync/ha-primary':
   try:
    j=json.loads(output)
    output=json.dumps({k:j.get(k) for k in ['schema','node','mode','created','already_present','missing','conflicts']},sort_keys=True)
   except Exception:output='report-not-json'
  else:output='topic_present' if output.endswith(topic) else 'topic_unconfirmed'
  print('JNS_BROKER_TOPIC',topic,output,flush=True)
 except Exception as e:print('JNS_BROKER_TOPIC',topic,'blocked_or_absent '+type(e).__name__,flush=True)
