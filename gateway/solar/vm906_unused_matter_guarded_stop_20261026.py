#!/usr/bin/env python3
"""Stop unused standalone Matter Server on HA-Security VM906 only.
Precondition: zero Matter devices/entities, QGA healthy, Docker restart=no.
No integration removal, no data/DB edits, no docker rm. Roll back if HA
or security's network/ESPHome registry health changes.
"""
import subprocess,shlex,json,re,time,sys
def fail(code):
 print("JNS_MATTER_GUARDED_STOP_BLOCKED="+code,flush=True);raise SystemExit(1)
def ssh(args,timeout=40):
 try:r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5","nodea",shlex.join(args)],
    capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return r.stdout if r.returncode==0 else None
def guest(args):
 raw=ssh(["qm","guest","exec","906","--",*args],35)
 if not raw:return {"status":"not_available"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"bad_reply"}
 for _ in range(45):
  if j.get("exited"):break
  if not j.get("pid"):break
  time.sleep(.35)
  raw=ssh(["qm","guest","exec-status","906",str(j["pid"])],12)
  if not raw:break
  try:j=json.loads(raw)
  except ValueError:break
 if not j.get("exited"):return {"status":"timeout"}
 return {"status":"ok" if j.get("exitcode")==0 else "failed","lines":(j.get("out-data") or "").splitlines()}
def role_counts():
 code=r'''
import json,pathlib
d=pathlib.Path("/config/.storage")
def reg(f,k):
 try:return json.loads((d/f).read_text()).get("data",{}).get(k,[])
 except (OSError,ValueError,TypeError):return []
ents=reg("core.entity_registry","entities")
devices=reg("core.device_registry","devices")
configs=reg("core.config_entries","entries")
print("JNS_MATTER_COUNTS="+json.dumps({
 "matter_entries":sum(x.get("domain")=="matter" for x in configs),
 "matter_entities":sum(x.get("platform")=="matter" for x in ents),
 "matter_devices":sum(any(isinstance(c,(list,tuple)) and c and c[0]=="matter" for c in x.get("identifiers",[])) for x in devices),
 "esphome_entries":sum(x.get("domain")=="esphome" for x in configs),
 "esphome_entities":sum(x.get("platform")=="esphome" for x in ents)
},sort_keys=True))
'''
 result=guest(["docker","exec","homeassistant","python3","-c",code])
 if result["status"]!="ok":fail("unable_to_verify_matter_registry")
 mark=[x.split("=",1)[1] for x in result["lines"] if x.startswith("JNS_MATTER_COUNTS=")]
 if len(mark)!=1:fail("no_safe_counts")
 try:return json.loads(mark[0])
 except ValueError:fail("registry_invalid")
def docker_running():
 j=guest(["docker","ps","--format","{{json .}}"])
 if j["status"]!="ok":fail("docker_inventory_failed")
 active=[]
 for row in j["lines"]:
  try:x=json.loads(row)
  except ValueError:continue
  n=str(x.get("Names","")).strip("/")
  if n=="matter_server" or n.lower().endswith("_matter_server"):active.append(n)
 return active
def docker_meta(name,field):
 q=guest(["docker","inspect",name,"--format",field])
 return q["lines"][-1].strip() if q["status"]=="ok" and q["lines"] else None
def node_status():
 raw=ssh(["qm","status","906"],12)
 return bool(raw and raw.strip()=="status: running")
def http_check():
 src=r'''import socket
with socket.create_connection(("ha-security.home.arpa",80),timeout=5):pass
print("JNS_HTTP=yes")
'''
 raw=ssh(["python3","-c",src],15)
 return bool(raw and "JNS_HTTP=yes" in raw)
if not node_status() or not http_check():fail("security_prehealth_unavailable")
counts=role_counts()
if not(counts.get("matter_entries")==1 and counts.get("matter_entities")==0 and counts.get("matter_devices")==0 and
       counts.get("esphome_entries",0)>0 and counts.get("esphome_entities",0)>=30):
 fail("matter_or_esphome_dependencies_unsafe")
matches=docker_running()
if len(matches)!=1:fail("matter_server_not_unique")
name=matches[0]
if name.startswith("addon_") or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",name):fail("not_standalone_expected")
policy=docker_meta(name,"{{.HostConfig.RestartPolicy.Name}}")
if policy!="no":fail("unexpected_restart_policy")
print("JNS_MATTER_STOP_PREFLIGHT="+json.dumps({
 "matter_devices":0,"matter_entities":0,"esphome_entities":counts["esphome_entities"],
 "docker_restart_policy":"no","security_http_alive":True,"read_only_data_preserved":True},sort_keys=True),flush=True)
stop=guest(["docker","stop","--time","30",name])
if stop["status"]!="ok":fail("docker_stop_rejected")
time.sleep(6)
new_counts=role_counts()
post_ok=node_status() and http_check() and name not in docker_running() and (
 new_counts.get("esphome_entries")==counts.get("esphome_entries") and
 new_counts.get("esphome_entities")==counts.get("esphome_entities"))
if not post_ok:
 print("JNS_MATTER_ROLLBACK_REQUIRED=yes",flush=True)
 rb=guest(["docker","start",name])
 print("JNS_MATTER_ROLLBACK_REQUESTED="+("yes" if rb["status"]=="ok" else "failed"),flush=True)
 fail("post_health_check_failed")
print("JNS_MATTER_STOP_VERIFIED="+json.dumps({
 "matter_server_running":False,"matter_server_container_retained":True,
 "matter_entry_preserved":True,"esphome_entities_unchanged":True,
 "alarm_vm_running":True,"ha_public_http_alive":True,
 "docker_restart_policy":"no","databases_untouched":True,
 "rollback_action":"docker start existing Matter Server container"},sort_keys=True),flush=True)
