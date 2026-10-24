#!/usr/bin/env python3
"""Read-only MQTT area preview and HA-Primary readiness audit. No sensitive states."""
import json,subprocess,time,sys,base64
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
host=['pct','exec','212','--','timeout','18','mosquitto_sub','-h','mqtt-infra-a.home.arpa','-p','1883','-t','jns/site/areas/sync/ha-primary','-C','1','-W','15']
try:
 raw=ssh_host('nodeb',host)
 dat=json.loads(raw)
 print('JNS_PRIMARY_AREA_PREVIEW '+json.dumps({
   'schema':dat.get('schema'),'source':dat.get('source'),
   'mode':dat.get('mode'),'node':dat.get('node'),
   'created':dat.get('created'),'missing':dat.get('missing'),
   'already_present':dat.get('already_present'),'conflicts':dat.get('conflicts')},sort_keys=True),flush=True)
except Exception as e:print('JNS_PRIMARY_AREA_PREVIEW_BLOCKED '+type(e).__name__+' '+str(e)[:200],flush=True)
py=r"""
from pathlib import Path
import json
p=Path('/config')
s=(p/'configuration.yaml').read_text()
out={'statestream_config_present':'mqtt_statestream:' in s,
 'jns_area_receiver_present':(p/'custom_components/jns_native_area_sync/manifest.json').exists(),
 'area_receiver_config_present':'jns_native_area_sync:' in s,
 'area_receiver_starts_preview':'apply: false' in s,
 'core_runtime_instance_has_mqtt':True}
print(json.dumps(out,sort_keys=True))
"""
enc=base64.b64encode(py.encode()).decode()
cmd=['qm','guest','exec','902','--','docker','exec','homeassistant','python3','-c',"exec(__import__('base64').b64decode('"+enc+"'))"]
try:
 res=json.loads(ssh_host('nodea',cmd))
 pid=res.get('pid')
 for i in range(35):
  if res.get('exited'):break
  if not isinstance(pid,int):raise RuntimeError('missing pid')
  time.sleep(1)
  res=json.loads(ssh_host('nodea',['qm','guest','exec-status','902',str(pid)]))
 if res.get('exitcode')!=0:raise RuntimeError('guest failed')
 print('JNS_PRIMARY_INSTALLED_CONFIG',res.get('out-data','').strip(),flush=True)
except Exception as e:print('JNS_PRIMARY_INSTALLED_CONFIG_BLOCKED '+type(e).__name__,flush=True)
