#!/usr/bin/env python3
"""Read-only, log-safe audit of existing HAOS app Core-API permissions on VM905.
Never reads/touches app tokens or asks another app to use privileged credentials.
Only official 'ha addons' CLI, running through the established Node C/QGA gateway.
"""
import json,os,shlex,subprocess,time

SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
def ssh(host,args,timeout=25):
 try:return subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None

def qga(host,vm,args,timeout=65):
 p=ssh(host,["qm","guest","exec",str(vm),"--",*args],35)
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except ValueError:return None
 until=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<until:
  if not j.get("pid"):return None
  time.sleep(.4)
  p=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],20)
  if not p or p.returncode:return None
  try:j=json.loads(p.stdout)
  except ValueError:return None
 return j if j.get("exited") and j.get("exitcode")==0 and not j.get("out-truncated") else None

def cli(*args):
 j=qga("nodeb",905,["ha",*args,"--raw-json"],timeout=55)
 if j is None:return None
 try:return json.loads(j.get("out-data") or "")
 except (ValueError,TypeError):return None

def unpack(j):
 if not isinstance(j,dict):return None
 if j.get("result")!="ok":return None
 return j.get("data")

def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_VM905_APP_PERMISSION_AUDIT_BLOCKED=wrong_runner");return 1
 s=ssh("nodeb",["qm","status","905"],20)
 if not s or s.returncode or s.stdout.strip()!="status: running":
  print("JNS_VM905_APP_PERMISSION_AUDIT_BLOCKED=vm905_offline");return 1
 d=unpack(cli("addons","list"))
 if not isinstance(d,dict) or not isinstance(d.get("addons"),list):
  print("JNS_VM905_APP_PERMISSION_AUDIT_BLOCKED=cli_inventory_unavailable");return 1
 items=d["addons"]
 checked=[]
 unavailable=0
 for a in items:
  if not isinstance(a,dict):continue
  slug=a.get("slug")
  if not isinstance(slug,str) or len(slug)>110 or not slug.replace("_","").replace("-","").isalnum():continue
  v=unpack(cli("addons","info",slug))
  if not isinstance(v,dict):
   unavailable+=1;continue
  # Info is metadata only, no user/app secrets.
  checked.append({
    "running":v.get("state") in ("started","running"),
    "installed":bool(v.get("installed")),
    "core_api":v.get("homeassistant_api") is True,
    "supervisor_api":v.get("hassio_api") is True,
    "role":str(v.get("hassio_role","unspecified")),
    "ssh_named":("ssh" in (v.get("name","") or "").lower()),
    "local_app":slug.startswith("local_")
  })
 print("JNS_VM905_EXISTING_APP_API_PERMISSIONS="+json.dumps({
   "app_inventory_count":len(items),"app_details_readable":len(checked),
   "details_unavailable":unavailable,
   "core_api_permitted":sum(v["core_api"] for v in checked),
   "core_api_permitted_and_running":sum(v["core_api"] and v["running"] for v in checked),
   "core_api_permitted_local_apps":sum(v["core_api"] and v["local_app"] for v in checked),
   "ssh_app_core_api_permitted":sum(v["core_api"] and v["ssh_named"] for v in checked),
   "unrestricted_supervisor_roles":sum(v["role"] in ("admin","manager") for v in checked),
   "permissions_inspected_only":True,
   "no_tokens_read":True,"ha_config_changed":False},sort_keys=True),flush=True)
 print("JNS_VM905_APP_PERMISSION_AUDIT_READONLY=yes",flush=True)
 return 0
if __name__=="__main__":raise SystemExit(main())
