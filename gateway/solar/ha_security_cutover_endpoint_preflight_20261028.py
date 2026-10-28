#!/usr/bin/env python3
"""Non-disclosing preflight for native manual alarm secret and ESPHome APIs.
No configuration writes, no alarms/locks/sirens/actions. Source VM906 remains active.
"""
import base64,json,os,shlex,subprocess,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
GUEST=r'''
import json,os,pathlib,re,urllib.request
p=pathlib.Path("/config/secrets.yaml")
o={"vm_role":os.environ.get("JNS_ROLE","unknown"),"secrets_file_present":p.is_file()}
if p.is_file():
 try:
  keys=set(re.findall(r"(?m)^([a-zA-Z0-9_.-]+)\s*:",p.read_text(errors="replace")))
  o["secret_key_count"]=len(keys)
 except OSError:pass
token=os.environ.get("SUPERVISOR_TOKEN","")
o["supervisor_token_available_in_core_container"]=bool(token)
o["supervisor_proxy_auth_works"]=False
if token:
 try:
  req=urllib.request.Request("http://supervisor/core/api/",headers={"Authorization":"Bearer "+token})
  with urllib.request.urlopen(req,timeout=5) as res:o["supervisor_proxy_auth_works"]=res.status==200
 except Exception:pass
try:import websockets
except ImportError:o["websockets_available"]=False
else:o["websockets_available"]=True
print("JNS_SECURITY_API_READINESS="+json.dumps(o,sort_keys=True))
'''
SRC=r'''
import json,os,pathlib,re,socket
p=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
m=json.loads((p/"manifest.json").read_text())
source=[]
for row in m.get("files",[]):
 if row.get("original_basename")=="configuration.yaml":
  source=(p/"files"/row["staged_basename"]).read_text()
  break
a=re.search(r"(?ms)^alarm_control_panel\s*:\s*\n(.*?)(?=^[A-Za-z][\w]*\s*:|\Z)",source)
names=re.findall(r"!secret\s+([A-Za-z0-9_.-]+)",a.group(1) if a else "")
d=json.loads((p/"esphome-enrolment-private.json").read_text()).get("data",{})
host=d.get("host") or d.get("ip_address")
port=d.get("port",6053)
reachable=False
if isinstance(host,str) and isinstance(port,int):
 try:
  with socket.create_connection((host,port),timeout=3):reachable=True
 except OSError:pass
print("JNS_SECURITY_ENROLMENT_READINESS="+json.dumps({
 "manual_alarm_block_present":bool(a),
 "unique_alarm_secret_refs":len(set(names)),
 "esphome_host_defined":isinstance(host,str),
 "esphome_port_defined":isinstance(port,int),
 "esphome_tcp_reachable_from_nodeb":reachable,
 "esphome_encryption_key_staged":any("key" in k.lower() or "noise" in k.lower() for k in d)},sort_keys=True))
'''
def ssh(host,args,timeout=24):
 try:p=subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def qga(host,vm,args):
 s=ssh(host,["qm","guest","exec",str(vm),"--",*args],35)
 if not s:return None
 try:j=json.loads(s)
 except ValueError:return None
 for _ in range(50):
  if j.get("exited"):return j
  if not j.get("pid"):break
  time.sleep(.4)
  s=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],20)
  if not s:break
  try:j=json.loads(s)
  except ValueError:break
 return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 src=base64.b64encode(SRC.encode()).decode()
 v=ssh("nodeb",["python3","-c","exec(__import__('base64').b64decode('"+src+"'))"],35)
 for l in (v or "").splitlines():
  if l.startswith("JNS_SECURITY_ENROLMENT_READINESS="):print(l,flush=True)
 for role,host,vm in (("source","nodea",906),("target","nodeb",905)):
  code=base64.b64encode(GUEST.replace('os.environ.get("JNS_ROLE","unknown")',repr(role)).encode()).decode()
  j=qga(host,vm,["docker","exec","homeassistant","python3","-c","exec(__import__('base64').b64decode('"+code+"'))"])
  if j and j.get("exitcode")==0:
   for line in str(j.get("out-data","")).splitlines():
    if line.startswith("JNS_SECURITY_API_READINESS="):print(line,flush=True)
  else:print("JNS_SECURITY_API_READINESS="+json.dumps({"vm_role":role,"available":False}),flush=True)
 print("JNS_SECURITY_PRECHECK_NO_CHANGES=yes",flush=True)
if __name__=="__main__":main()
