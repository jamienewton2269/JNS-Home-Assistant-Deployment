#!/usr/bin/env python3
"""Read-only test Core Admin WS API transport through Supervisor proxy."""
import base64,json,shlex,subprocess,time
SRC=r'''
import asyncio,os,json,aiohttp
async def probe(endpoint,token):
 result={"authenticated":False,"handshake":None,"auth_reply":None}
 if not token:return result
 try:
  timeout=aiohttp.ClientTimeout(total=9,connect=4)
  async with aiohttp.ClientSession(timeout=timeout) as session:
   async with session.ws_connect(endpoint,timeout=5) as ws:
    hello=await ws.receive_json(timeout=4)
    result["handshake"]=hello.get("type")
    if hello.get("type")=="auth_required":
     await ws.send_json({"type":"auth","access_token":token})
     ans=await ws.receive_json(timeout=4)
     result["auth_reply"]=ans.get("type")
     result["authenticated"]=ans.get("type")=="auth_ok"
 except Exception as e:
  result["error_class"]=type(e).__name__
 return result
async def main():
 out={}
 for label,url in (
  ("proxy","ws://supervisor/core/websocket"),
  ("local","ws://127.0.0.1:8123/api/websocket")):
  for key in ("SUPERVISOR_TOKEN","HASSIO_TOKEN"):
   out[label+"_"+key]=await probe(url,os.environ.get(key))
 print("JNS_MATTER_CORE_WS_PREFLIGHT="+json.dumps(out,sort_keys=True))
asyncio.run(main())
'''
def ssh(argv,timeout=36):
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
 "nodea",shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
enc=base64.b64encode(SRC.encode()).decode()
x=ssh(["qm","guest","exec","906","--","docker","exec","homeassistant","python3","-c",
       "exec(__import__('base64').b64decode('"+enc+"'))"],34)
try:j=json.loads(x or "")
except ValueError:raise SystemExit("JNS_MATTER_WS_QGA_START_FAILED")
for _ in range(65):
 if j.get("exited"):break
 if not j.get("pid"):break
 time.sleep(.3)
 p=ssh(["qm","guest","exec-status","906",str(j["pid"])],15)
 if not p:break
 try:j=json.loads(p)
 except ValueError:break
for l in (j.get("out-data") or "").splitlines():
 if l.startswith("JNS_MATTER_CORE_WS_PREFLIGHT="):print(l,flush=True)
if not j.get("exited") or j.get("exitcode")!=0:raise SystemExit("JNS_MATTER_WS_QGA_EXIT_FAILED")
