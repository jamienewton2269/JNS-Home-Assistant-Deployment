#!/usr/bin/env python3
"""Read-only owner and device inventory: VM906 Matter Server.
Never print secrets, integration data or raw container labels/mounts.
"""
import json,shlex,subprocess,time,re
def ssh(argv,timeout=30):
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
    "-o","ConnectTimeout=5","nodea",shlex.join(argv)],text=True,capture_output=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def guest(argv):
 raw=ssh(["qm","guest","exec","906","--",*argv],35)
 if not raw:return {"status":"unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"malformed"}
 for _ in range(50):
  if j.get("exited"):break
  if not j.get("pid"):break
  time.sleep(.3)
  p=ssh(["qm","guest","exec-status","906",str(j["pid"])],15)
  if not p:break
  try:j=json.loads(p)
  except ValueError:break
 if not j.get("exited"):return {"status":"timeout"}
 return {"status":"ok" if j.get("exitcode")==0 else "failed","lines":(j.get("out-data") or "").splitlines()}
out={"read_only":True}
z=guest(["docker","ps","-a","--filter","name=matter_server","--format","{{json .}}"])
out["list_status"]=z["status"]
names=[]
for line in z.get("lines",[]):
 try:x=json.loads(line)
 except ValueError:continue
 name=str(x.get("Names","")).strip("/")
 if name=="matter_server":names.append(name)
out["exact_matter_containers"]=len(names)
if names:
 z=guest(["docker","inspect","matter_server","--format","{{json .}}"])
 if z["status"]=="ok":
  try:
   x=json.loads("".join(z["lines"]))
   cfg=x.get("Config") or {}
   host=x.get("HostConfig") or {}
   labels=cfg.get("Labels") or {}
   out["container"]={
    "running":bool((x.get("State") or {}).get("Running")),
    "restart_policy":(host.get("RestartPolicy") or {}).get("Name"),
    "has_compose_labels":any(k.startswith("com.docker.compose") for k in labels),
    "has_supervisor_labels":any("hassio" in k or "supervisor" in k for k in labels),
    "container_image_category":"matter",
    "created_present":bool(x.get("Created")),
    "mount_count":len(x.get("Mounts") or []),
    "network_mode_present":bool(host.get("NetworkMode")),
   }
  except (ValueError,TypeError,AttributeError):out["inspect_format"]="unknown"
payload=r'''
import json,pathlib
d=pathlib.Path("/config/.storage")
def rows(file,key):
 try:
  a=json.loads((d/file).read_text()).get("data",{}).get(key,[])
  return a if isinstance(a,list) else []
 except (ValueError,OSError,TypeError):return []
entries=rows("core.config_entries","entries")
entities=rows("core.entity_registry","entities")
devices=rows("core.device_registry","devices")
m=[x for x in entries if x.get("domain")=="matter"]
result={
 "matter_entry_count":len(m),
 "matter_entries_disabled":sum(x.get("disabled_by") is not None for x in m),
 "matter_entity_count":sum(x.get("platform")=="matter" for x in entities),
 "matter_devices":sum(any(isinstance(pair,(tuple,list)) and pair and pair[0]=="matter" for pair in d.get("identifiers",[])) for d in devices),
 "esphome_entries_enabled":sum(x.get("domain")=="esphome" and x.get("disabled_by") is None for x in entries),
 "esphome_entities":sum(x.get("platform")=="esphome" and x.get("disabled_by") is None for x in entities),
}
print("JNS_SAFE_MATTER_REGISTRY="+json.dumps(result,sort_keys=True))
'''
z=guest(["docker","exec","homeassistant","python3","-c",payload])
out["registry_status"]=z["status"]
if z["status"]=="ok":
 for l in z.get("lines",[]):
  if l.startswith("JNS_SAFE_MATTER_REGISTRY="):
   try:out["registries"]=json.loads(l.split("=",1)[1])
   except ValueError:pass
z=guest(["ha","core","info","--raw-json"])
out["ha_core_info_status"]=z["status"]
if z["status"]=="ok":
 try:
  p=json.loads("".join(z["lines"]))
  out["core_state"]=p.get("state","unknown") if isinstance(p,dict) else "unknown"
 except ValueError:out["core_state"]="unknown"
print("JNS_MATTER_OWNER_PREFLIGHT="+json.dumps(out,sort_keys=True),flush=True)
