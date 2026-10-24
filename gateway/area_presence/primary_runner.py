#!/usr/bin/env python3
"""Node C -> Node A VM902 QEMU guest: safe area + phone MQTT installation."""
from pathlib import Path
import base64,json,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
DIRECTORY=Path('gateway/area_presence')
CHECK=Path('gateway/arrival_lighting/ha_primary_presence_mqtt_statestream.STAGED.yaml').read_text()
AREA=(DIRECTORY/'ha_primary_native_area_sync.STAGED.yaml').read_text()
COMPONENT=(DIRECTORY/'custom_components/jns_native_area_sync/__init__.py').read_bytes()
MANIFEST=(DIRECTORY/'custom_components/jns_native_area_sync/manifest.json').read_bytes()
PATCH=(DIRECTORY/'patch_primary.py').read_bytes()
SNIPPET="\n"+CHECK.split("mqtt_statestream:\n",1)[-1]
SNIPPET="mqtt_statestream:\n"+SNIPPET.strip('\n')+"\n\n"+AREA.split("jns_native_area_sync:\n",1)[-1]
SNIPPET=SNIPPET.split("\n\n",1)[0]+"\n\njns_native_area_sync:\n"+AREA.split("jns_native_area_sync:\n",1)[1]

def guest(args,limit=180):
 result=json.loads(ssh_host('nodea',['qm','guest','exec','902','--',*args]))
 pid=result.get('pid')
 until=time.monotonic()+limit
 while not result.get('exited'):
  if not isinstance(pid,int):raise RuntimeError('Guest initial PID missing')
  if time.monotonic()>until:raise RuntimeError('Guest PID '+str(pid)+' exceeded time budget; manual review required')
  time.sleep(3)
  result=json.loads(ssh_host('nodea',['qm','guest','exec-status','902',str(pid)]))
 return result
def install(mode):
 env=";".join([
 "COMPONENT_PY="+repr(base64.b64encode(COMPONENT).decode()),
 "COMPONENT_JSON="+repr(base64.b64encode(MANIFEST).decode()),
 "CONFIG_APPEND="+repr(base64.b64encode(SNIPPET.encode()).decode())
 ])
 cmd=env+";exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(PATCH).decode())+"),'<jns-primary-patch>','exec'))"
 res=guest(['docker','exec','homeassistant','python3','-c',cmd,mode],90)
 print('JNS_PRESENCE_PRIMARY_'+mode+' '+(res.get('out-data') or '')[-2800:],flush=True)
 if res.get('exitcode')!=0:raise RuntimeError('Failed '+mode+' '+(res.get('err-data') or '')[-280:])
 return res.get('out-data') or ''
if __name__=='__main__':
 mode='--apply' if '--apply' in sys.argv else '--dry-run'
 install(mode)
