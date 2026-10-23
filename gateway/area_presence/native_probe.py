#!/usr/bin/env python3
"""No-write Home Assistant native WebSocket capability and broker check on VM902."""
import base64,json,sys,time,subprocess
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
INSPECT=r"""
import os,json,asyncio,socket
out={'supervisor_token_present':bool(os.environ.get('SUPERVISOR_TOKEN'))}
try:
 import aiohttp
 out['aiohttp_available']=True
except Exception as e:
 out['aiohttp_available']=False
for host,port in [('mqtt-infra-a.home.arpa',1883)]:
 try:
  socket.create_connection((host,port),timeout=5).close()
  out['broker_tcp_1883']='reachable'
 except Exception as e:out['broker_tcp_1883']=type(e).__name__
async def go():
 if not out.get('supervisor_token_present') or not out.get('aiohttp_available'):return
 try:
  async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=18)) as session:
   async with session.ws_connect('ws://supervisor/core/websocket',timeout=8) as ws:
    msg=await ws.receive_json(timeout=5)
    out['ws_first_message']=msg.get('type')
    await ws.send_json({'type':'auth','access_token':os.environ['SUPERVISOR_TOKEN']})
    auth=await ws.receive_json(timeout=6)
    out['ws_auth_result']=auth.get('type')
    if auth.get('type')!='auth_ok':return
    await ws.send_json({'id':1,'type':'config/area_registry/list'})
    a=await ws.receive_json(timeout=6)
    out['area_registry_list_success']=a.get('success')
    if a.get('success'):
     out['area_registry_count']=len(a.get('result',[]))
    await ws.send_json({'id':2,'type':'config_entries/flow/init','handler':'mqtt','show_advanced_options':False})
    init=await ws.receive_json(timeout=6)
    # Flow init may create a temporary flow; don't configure or submit it.
    out['mqtt_flow_init_success']=init.get('success')
    if init.get('success'):
      val=init.get('result',{})
      out['mqtt_flow_type']=val.get('type')
      out['mqtt_flow_step_id']=val.get('step_id')
      out['mqtt_flow_errors']=val.get('errors')
      out['mqtt_flow_schema_names']=[str(s.get('name')) for s in val.get('data_schema',[]) if isinstance(s,dict)][:15]
 except Exception as e:out['ws_probe_error']=type(e).__name__
asyncio.run(go())
print(json.dumps(out,sort_keys=True))
"""
arg="exec(__import__('base64').b64decode('"+base64.b64encode(INSPECT.encode()).decode()+"'))"
resp=json.loads(ssh_host('nodea',['qm','guest','exec','902','--','docker','exec','homeassistant','python3','-c',arg]))
pid=resp.get('pid')
for i in range(35):
 if resp.get('exited'):break
 if not isinstance(pid,int):raise RuntimeError('missing initial PID')
 time.sleep(1)
 resp=json.loads(ssh_host('nodea',['qm','guest','exec-status','902',str(pid)]))
if not resp.get('exited') or resp.get('exitcode')!=0:raise RuntimeError('qga guest exited: '+(resp.get('err-data') or '')[-500:])
print('JNS_NATIVE_API_PROBE',resp.get('out-data',''),flush=True)
for node in ('nodea','nodeb','nodec'):
 try:
  p=subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=4','root@'+node+'.home.arpa','hostname -s; command -v qm >/dev/null && qm status 906'],capture_output=True,text=True,timeout=15)
  # No need to print addresses or internal access details.
  print('JNS_VM906_HOST_PROBE',node,{'returncode':p.returncode,'vm906_running':('running' in p.stdout),'qm_available':('906' in p.stdout)},flush=True)
 except Exception as e:print('JNS_VM906_HOST_PROBE',node,{'blocked':type(e).__name__},flush=True)
