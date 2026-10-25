#!/usr/bin/env python3
"""Probe authenticated Home Assistant WS registry API via internal Supervisor proxy. Read-only."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
CODE=r'''
import os,json,websocket
token=os.environ.get('SUPERVISOR_TOKEN')
assert token,'no supervisor token available'
targets=['0xa4c13833916ae7d1','0xa4c1383917c90309','0xa4c1386faf69d5e0','0xa4c138cf0342f0d9']
endpoints=['ws://supervisor/core/websocket','ws://supervisor/core/api/websocket','ws://127.0.0.1:8123/api/websocket']
results=[]
for url in endpoints:
  sock=None
  try:
    sock=websocket.create_connection(url,timeout=5,header=['Authorization: Bearer '+token],enable_multithread=True)
    hello=json.loads(sock.recv())
    if hello.get('type')=='auth_required':
      sock.send(json.dumps({'type':'auth','access_token':token}))
      hello=json.loads(sock.recv())
    if hello.get('type')!='auth_ok':
      results.append({'endpoint':url,'status':'authentication_not_accepted','type':hello.get('type')})
      continue
    sock.send(json.dumps({'id':1,'type':'config/device_registry/list'}))
    msg=json.loads(sock.recv())
    while msg.get('id')!=1: msg=json.loads(sock.recv())
    if not msg.get('success'):
      results.append({'endpoint':url,'status':'device_registry_read_failed','error_code':msg.get('error',{}).get('code')})
      continue
    matched=[{'id':d.get('id'),'name':d.get('name'),'name_by_user':d.get('name_by_user'),
        'model':d.get('model'),'identifiers':d.get('identifiers')}
      for d in msg.get('result',[]) if any(t in str(d.get('identifiers')).lower() for t in targets)]
    results.append({'endpoint':url,'status':'usable','matches':matched,'device_count':len(msg.get('result',[]))})
    break
  except Exception as e:
    results.append({'endpoint':url,'status':'blocked','error_type':type(e).__name__})
  finally:
    if sock:
      try:sock.close()
      except:pass
print('JNS_SENSOR_NAME_API_PROBE '+json.dumps(results,ensure_ascii=False))
'''
arg="exec(__import__('base64').b64decode("+repr(base64.b64encode(CODE.encode()).decode())+"))"
data=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',arg]))
pid=data.get('pid')
for _ in range(40):
    if data.get('exited'):break
    if not isinstance(pid,int):raise RuntimeError("guest PID missing")
    time.sleep(1)
    data=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
if not data.get('exited') or data.get('exitcode')!=0:raise RuntimeError('HA sensor name API probe unsuccessful')
print((data.get('out-data') or '')[:9000])
