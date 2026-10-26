#!/usr/bin/env python3
"""Disable unused HA-Security Matter Server through authenticated Supervisor.

No Docker service manipulation, no integration/database edits or deletion.
Changes only core_matter_server startup auto->manual and stops the app.
Run from authorised Node C Actions runner via Node A QEMU guest agent.
"""
import base64,json,shlex,subprocess,time,sys
PAYLOAD=r'''
import os,json,urllib.request,urllib.error,socket,time,re,pathlib
APP="core_matter_server"
ENDPOINT="http://supervisor/addons/"+APP
token=os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
def emit(key,data):
 print(key+"="+json.dumps(data,sort_keys=True),flush=True)
def fail(reason):
 emit("JNS_MATTER_DISABLE_BLOCKED",{"reason":reason})
 raise SystemExit(1)
if not token or len(token)<30:fail("supervisor_auth_not_available")
headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"}
def request(method,path,data=None):
 raw=json.dumps(data).encode() if data is not None else None
 req=urllib.request.Request(ENDPOINT+"/"+path,data=raw,headers=headers,method=method)
 try:
  with urllib.request.urlopen(req,timeout=35) as res:
   body=res.read(256000)
  obj=json.loads(body)
  if obj.get("result") not in ("ok",None):
   return {"ok":False,"error":"supervisor_result_not_ok"}
  return {"ok":True,"data":obj.get("data",obj)}
 except urllib.error.HTTPError as err:
  return {"ok":False,"http":err.code}
 except (OSError,ValueError,TimeoutError):
  return {"ok":False,"error":"transport_or_response_failure"}
def info():
 r=request("GET","info")
 if not r["ok"]:fail("addon_info_unavailable")
 v=r["data"]
 if not isinstance(v,dict) or v.get("slug")!=APP:fail("wrong_addon_identity")
 return v
def rows(path,key):
 try:
  v=json.loads(path.read_text()).get("data",{}).get(key,[])
  return v if isinstance(v,list) else []
 except (OSError,ValueError,TypeError):fail("registry_unavailable")
base=pathlib.Path("/config/.storage")
entries=rows(base/"core.config_entries","entries")
entities=rows(base/"core.entity_registry","entities")
devices=rows(base/"core.device_registry","devices")
matter_entries=[v for v in entries if v.get("domain")=="matter"]
matter_entities=[v for v in entities if v.get("platform")=="matter" and not v.get("disabled_by")]
matter_devices=[v for v in devices if any(isinstance(id,(list,tuple)) and id and id[0]=="matter" for id in v.get("identifiers",[]))]
esphome_entries=[v for v in entries if v.get("domain")=="esphome" and v.get("disabled_by") is None]
esphome_entities=[v for v in entities if v.get("platform")=="esphome" and not v.get("disabled_by")]
if len(matter_entries)!=1 or matter_entities or matter_devices:fail("matter_entries_or_devices_have_changed")
if len(esphome_entries)!=1 or len(esphome_entities)<30:fail("security_esphome_registry_not_healthy")
host=esphome_entries[0].get("data",{}).get("host")
if not isinstance(host,str) or not host or len(host)>256:fail("esphome_endpoint_missing")
def esphome():
 try:
  with socket.create_connection((host,6053),timeout=5):return True
 except OSError:return False
if not esphome():fail("esphome_unreachable_before_change")
original=info()
old_boot=original.get("boot")
old_state=original.get("state")
if old_boot not in ("auto","manual") or old_state not in ("started","stopped"):
 fail("unexpected_initial_addon_state")
emit("JNS_MATTER_DISABLE_PRECHECK",{
 "addon":APP,"old_boot":old_boot,"old_state":old_state,
 "matter_entities":len(matter_entities),"matter_devices":len(matter_devices),
 "esphome_entities":len(esphome_entities),
 "esphome_native_api_reachable":True,
 "system_managed":bool(original.get("system_managed",False)),
 "target_boot":"manual","target_state":"stopped",
 "database_writes":False})
changed_boot=False
stopped=False
def rollback(reason):
 # Restore original startup policy and service if needed.
 if changed_boot and old_boot=="auto":
  request("POST","options",{"boot":"auto"})
 if old_state=="started" and info().get("state")!="started":
  request("POST","start",{})
 latest=info()
 emit("JNS_MATTER_DISABLE_ROLLBACK",{
  "reason":reason,"boot":latest.get("boot"),"state":latest.get("state"),
  "esphome_6053_reachable":esphome()})
 raise SystemExit(2)
if old_boot!="manual":
 r=request("POST","options",{"boot":"manual"})
 if not r["ok"]:fail("supervisor_rejected_manual_boot_"+str(r.get("http",r.get("error",""))))
 changed_boot=True
if info().get("boot")!="manual":rollback("boot_policy_not_persisted")
if old_state!="stopped":
 r=request("POST","stop",{})
 if not r["ok"]:rollback("supervisor_stop_failed")
 stopped=True
# Check stable stopped; if auto-managed restarts report failed, never fight the supervisor.
samples=[]
for attempt in range(12):
 time.sleep(3)
 state=info().get("state")
 samples.append(state)
 if state=="started":
  rollback("matter_restarted_by_supervisor_or_integration")
 if state not in ("stopped","stopping","unknown"):
  rollback("unexpected_post_state")
 if not esphome():rollback("esphome_lost_connectivity")
new_entries=rows(base/"core.config_entries","entries")
new_esphome=rows(base/"core.entity_registry","entities")
if len([x for x in new_entries if x.get("domain")=="esphome" and x.get("disabled_by") is None]) != len(esphome_entries):
 rollback("esphome_integration_change")
if len([x for x in new_esphome if x.get("platform")=="esphome" and not x.get("disabled_by")]) != len(esphome_entities):
 rollback("esphome_entities_change")
after=info()
if after.get("boot")!="manual" or after.get("state")!="stopped":rollback("post_boot_or_state_mismatch")
emit("JNS_MATTER_MANAGED_DISABLE_COMPLETE",{
 "app":APP,"boot":"manual","state":"stopped",
 "stable_state_samples":len(samples),
 "esphome_api_reachable":True,"esphome_entities_unchanged":True,
 "matter_devices":0,"matter_entities":0,
 "matter_addon_uninstalled":False,"matter_config_retained":True,
 "homeassistant_core_still_running":True,
 "databases_untouched":True})
'''
def ssh(argv,timeout=36):
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6",
                       "nodea",shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def command(argv,timeout=40):
 raw=ssh(["qm","guest","exec","906","--",*argv],35)
 if not raw:return {"status":"qga_unavailable"}
 try:v=json.loads(raw)
 except ValueError:return {"status":"malformed_qga"}
 for _ in range(250):
  if v.get("exited"):break
  if v.get("pid") is None:break
  time.sleep(.45)
  result=ssh(["qm","guest","exec-status","906",str(v["pid"])],17)
  if not result:break
  try:v=json.loads(result)
  except ValueError:break
 return {"status":"complete" if v.get("exited") else "timeout",
         "exitcode":v.get("exitcode"),
         "lines":(v.get("out-data") or "").splitlines()}
def main():
 vm=ssh(["qm","status","906"])
 if not vm or vm.strip()!="status: running":
  print("JNS_MATTER_GATE_BLOCKED=vm906_not_running");raise SystemExit(1)
 # Read-only host web endpoint preflight
 source=r'''import socket
with socket.create_connection(("ha-security.home.arpa",80),timeout=5): pass
print("JNS_HA_SECURITY_PORT80_OK")
'''
 p=ssh(["python3","-c",source],20)
 if not p or "JNS_HA_SECURITY_PORT80_OK" not in p:
  print("JNS_MATTER_GATE_BLOCKED=security_endpoint_unreachable_before_change")
  raise SystemExit(1)
 enc=base64.b64encode(PAYLOAD.encode()).decode()
 out=command(["docker","exec","homeassistant","python3","-c",
              "exec(__import__('base64').b64decode('"+enc+"'))"],200)
 for line in out.get("lines",[]):
  if line.startswith(("JNS_MATTER_DISABLE_","JNS_MATTER_MANAGED_DISABLE_COMPLETE=")):
   print(line,flush=True)
 if out["status"]!="complete" or out["exitcode"]!=0:
  print("JNS_MATTER_MANAGED_DISABLE_GATE_FAILED="+out["status"],flush=True)
  raise SystemExit(1)
 # Independent after-check from node A.
 vm=ssh(["qm","status","906"])
 if not vm or vm.strip()!="status: running":raise SystemExit("security_vm_unexpected_state")
 p=ssh(["python3","-c",source],20)
 if not p or "JNS_HA_SECURITY_PORT80_OK" not in p:
  raise SystemExit("JNS_HA_SECURITY_ENDPOINT_POSTCHECK_FAILED")
 print("JNS_MATTER_PRODUCTION_POSTCHECK=ha_security_up_and_http_reachable",flush=True)
if __name__=="__main__":main()
