#!/usr/bin/env python3
"""Verify native MQTT/Area API signatures from existing HA-General Core, no writes."""
import base64,json,time,sys
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
PY=r"""
import json
from homeassistant.components import mqtt
from homeassistant.helpers import area_registry
from homeassistant.util import slugify
out={
 'native_mqtt_async_publish':callable(getattr(mqtt,'async_publish',None)),
 'native_mqtt_async_subscribe':callable(getattr(mqtt,'async_subscribe',None)),
 'native_mqtt_wait_for_client':callable(getattr(mqtt,'async_wait_for_mqtt_client',None)),
 'native_area_registry_async_get':callable(getattr(area_registry,'async_get',None)),
 'native_area_registry_async_create':callable(getattr(area_registry.AreaRegistry,'async_create',None)),
 'native_area_registry_get_by_name':callable(getattr(area_registry.AreaRegistry,'async_get_area_by_name',None)),
 'slugify_cases':{name:slugify(name) for name in ['Dogs Run','Summer House','Downstairs WC']},
}
print(json.dumps(out,sort_keys=True))
"""
arg="exec(__import__('base64').b64decode('"+base64.b64encode(PY.encode()).decode()+"'))"
resp=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',arg]))
pid=resp.get('pid')
for i in range(32):
 if resp.get('exited'):break
 if not isinstance(pid,int):raise RuntimeError('QGA PID missing')
 time.sleep(1)
 resp=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
if not resp.get('exited') or resp.get('exitcode')!=0:
 raise RuntimeError('HA-native capability failed '+(resp.get('err-data') or '')[-250:])
print('JNS_MQTT_NATIVE_AREA_API',resp.get('out-data','').strip(),flush=True)
