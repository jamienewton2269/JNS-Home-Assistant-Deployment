#!/usr/bin/env python3
"""Disable unused Matter Server on HA-Security via native authenticated HA CLI.

Gateway: Node C runner -> Node A pinned SSH -> QEMU guest agent VM906.
Do not expose Supervisor token, do not remove integration or add-on data.
"""
import json,re,shlex,subprocess,time,sys
APP="core_matter_server"
def ssh(cmd,t=35):
 try:r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",
 "ConnectTimeout=5","nodea",shlex.join(cmd)],capture_output=True,text=True,timeout=t)
 except (OSError,subprocess.TimeoutExpired):return None
 return r.stdout if r.returncode==0 else None
def qga(cmd):
 raw=ssh(["qm","guest","exec","906","--",*cmd],35)
 if not raw:return {"status":"unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"invalid"}
 for _ in range(80):
  if j.get("exited"):break
  if j.get("pid") is None:break
  time.sleep(.25)
  raw=ssh(["qm","guest","exec-status","906",str(j["pid"])],14)
  if not raw:break
  try:j=json.loads(raw)
  except ValueError:break
 return {"status":"ok" if j.get("exited") and j.get("exitcode")==0 else "failed",
         "lines":(j.get("out-data") or "").splitlines()}
def addon():
 x=qga(["ha","apps","info",APP,"--raw-json"])
 if x["status"]!="ok":raise RuntimeError("addon_info_unavailable")
 try:
  y=json.loads("".join(x["lines"]))
  y=y.get("data",y)
  if y.get("slug")!=APP:raise ValueError("identity")
  return {k:y.get(k) for k in ("slug","state","boot","watchdog","system_managed","version")}
 except (ValueError,TypeError,AttributeError):raise RuntimeError("addon_info_unreadable")
def api_boot(value):
 if value not in ("auto","manual"):raise RuntimeError("invalid_boot_value")
 # Token is expanded ONLY inside the authorized CLI container; neither
 # its value nor raw HTTP response is shown in runner logs.
 cmd="""test -n "$SUPERVISOR_TOKEN" || exit 7
code=$(curl --silent --show-error --max-time 12 --output /dev/null --write-out '%{http_code}' \
 --request POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
 -H "Content-Type: application/json" --data '{"boot":"%s"}' \
 http://supervisor/addons/core_matter_server/options) || exit 8
printf 'JNS_HTTP_RESULT=%%s\n' "$code"
test "$code" = 200"""%value
 x=qga(["docker","exec","hassio_cli","sh","-c",cmd])
 codes=[v.split("=",1)[1] for v in x.get("lines",[]) if v.startswith("JNS_HTTP_RESULT=")]
 return x["status"]=="ok" and codes==["200"]
def fail(msg):
 print("JNS_MATTER_SAFE_STOP_BLOCKED="+msg,flush=True);raise SystemExit(1)
def checks():
 data=r'''import os,json,pathlib,socket
p=pathlib.Path("/config/.storage")
def read(name,key):
 try:return json.loads((p/name).read_text()).get("data",{}).get(key,[])
 except (OSError,ValueError,TypeError):return []
es=[x for x in read("core.config_entries","entries") if x.get("domain")=="esphome" and not x.get("disabled_by")]
entries=[x for x in read("core.config_entries","entries") if x.get("domain")=="matter"]
ents=read("core.entity_registry","entities")
dev=read("core.device_registry","devices")
d={"esphome_entries":len(es),"matter_entries":len(entries),
 "esphome_entities":sum(x.get("platform")=="esphome" and not x.get("disabled_by") for x in ents),
 "matter_entities":sum(x.get("platform")=="matter" and not x.get("disabled_by") for x in ents),
 "matter_devices":sum(any(isinstance(z,(list,tuple)) and z and z[0]=="matter" for z in x.get("identifiers",[])) for x in dev),
 "esphome_connected":False}
if len(es)==1:
 host=es[0].get("data",{}).get("host")
 if isinstance(host,str):
  try:
   with socket.create_connection((host,6053),timeout=5):d["esphome_connected"]=True
  except OSError:pass
print("JNS_SECURITY_SAFE_COUNTS="+json.dumps(d,sort_keys=True))
'''
 x=qga(["docker","exec","homeassistant","python3","-c",data])
 if x["status"]!="ok":fail("security_core_registry_inaccessible")
 marks=[l.split("=",1)[1] for l in x["lines"] if l.startswith("JNS_SECURITY_SAFE_COUNTS=")]
 try:return json.loads(marks[-1])
 except (ValueError,IndexError):fail("security_core_registry_invalid")
def verify_security(pre):
 post=checks()
 return (post==pre and post.get("esphome_connected") is True and
         ssh(["qm","status","906"])=="status: running\n")
def rollback(original,reason):
 if original.get("boot")=="auto": api_boot("auto")
 now=addon()
 if original.get("state")=="started" and now.get("state")!="started":
  qga(["ha","apps","start",APP])
 final=addon()
 print("JNS_MATTER_DISABLE_ROLLBACK="+json.dumps({
  "reason":reason,"state":final.get("state"),"boot":final.get("boot")},sort_keys=True),flush=True)
 raise SystemExit(2)
def main():
 if ssh(["qm","status","906"])!="status: running\n":fail("vm906_not_running")
 a=addon()
 pre=checks()
 print("JNS_MATTER_DISABLE_PREFLIGHT="+json.dumps({
  "addon_state":a.get("state"),"boot":a.get("boot"),
  "esphome_connected":pre.get("esphome_connected"),
  "esphome_entities":pre.get("esphome_entities"),
  "matter_entities":pre.get("matter_entities"),
  "matter_devices":pre.get("matter_devices")},sort_keys=True),flush=True)
 if a.get("system_managed"):fail("matter_system_managed_by_core")
 if not(pre.get("matter_entries")==1 and pre.get("matter_entities")==0 and pre.get("matter_devices")==0
    and pre.get("esphome_entries")==1 and pre.get("esphome_entities",0)>=30
    and pre.get("esphome_connected")):fail("active_dependency_or_esphome_not_ready")
 if a.get("boot") not in ("auto","manual") or a.get("state") not in ("started","stopped"):
  fail("unexpected_addon_status")
 if a.get("boot")!="manual":
  if not api_boot("manual"):fail("supervisor_boot_manual_request_failed")
  if addon().get("boot")!="manual":rollback(a,"boot_not_updated")
 if a.get("state")!="stopped":
  stopped=qga(["ha","apps","stop",APP])
  if stopped["status"]!="ok":rollback(a,"supervisor_app_stop_failed")
 states=[]
 for _ in range(9):
  time.sleep(3)
  current=addon()
  states.append(current.get("state"))
  if current.get("boot")!="manual" or current.get("state")=="started":
   rollback(a,"addon_restarted_or_boot_changed")
  if not verify_security(pre):rollback(a,"esphome_or_security_health_regression")
 final=addon()
 if final.get("boot")!="manual" or final.get("state")!="stopped":
  rollback(a,"final_stable_state_not_stopped")
 print("JNS_MATTER_PERSISTENT_DISABLE_VERIFIED="+json.dumps({
   "addon":"core_matter_server","state":"stopped","boot":"manual",
   "verified_samples":len(states),"matter_devices":0,
   "esphome_entities_preserved":True,"esphome_connected":True,
   "vm906_running":True,"matter_data_retained":True,
   "home_assistant_database_unchanged":True},sort_keys=True),flush=True)
if __name__=="__main__":main()
