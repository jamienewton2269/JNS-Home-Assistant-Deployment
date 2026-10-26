#!/usr/bin/env python3
"""Read-only HA-Security Matter management contract. No tokens/config values."""
import subprocess,shlex,json,time,re
def ssh(args,t=35):
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
  "nodea",shlex.join(args)],capture_output=True,text=True,timeout=t)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def qga(args):
 raw=ssh(["qm","guest","exec","906","--",*args],30)
 if not raw:return {"status":"unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"invalid"}
 for _ in range(30):
  if j.get("exited"):break
  if not j.get("pid"):break
  time.sleep(.3)
  r=ssh(["qm","guest","exec-status","906",str(j["pid"])],12)
  if not r:break
  try:j=json.loads(r)
  except ValueError:break
 if not j.get("exited"):return {"status":"timeout"}
 return {"status":"ok" if j.get("exitcode")==0 else "failed","lines":(j.get("out-data") or "").splitlines()}
out={"read_only":True,"vm":906}
ps=qga(["docker","ps","--format","{{json .}}"])
matches=[]
if ps["status"]=="ok":
 for line in ps["lines"]:
  try:x=json.loads(line)
  except ValueError:continue
  name=str(x.get("Names","")).lower().strip("/")
  if name=="matter_server" or name.endswith("_matter_server"):
   matches.append(name)
out["matter_container_count"]=len(matches)
out["matter_container_owner_type"]=("haos_system" if matches and matches[0].startswith("hassio_") else
 "supervisor_addon" if matches and matches[0].startswith("addon_") else
 "standalone_or_other" if matches else "not_found")
p=qga(["docker","inspect",matches[0],"--format","{{json .HostConfig.RestartPolicy}}"]) if len(matches)==1 else {"status":"no_unique_match"}
out["docker_inspect_status"]=p["status"]
if p["status"]=="ok":
 for l in p["lines"]:
  try:
   x=json.loads(l)
   if isinstance(x,dict) and x.get("Name") in ("always","no","unless-stopped","on-failure"):
    out["restart_policy"]=x.get("Name")
  except ValueError:pass
p=qga(["ha","addons","list","--raw-json"])
out["addons_list_status"]=p["status"]
if p["status"]=="ok":
 try:
  data=json.loads("".join(p["lines"]))
  addons=data.get("addons",[]) if isinstance(data,dict) else data
  match=[]
  for item in addons if isinstance(addons,list) else []:
   if not isinstance(item,dict):continue
   slug=str(item.get("slug",""))
   if "matter" in slug.lower():
    match.append({"slug":slug if re.fullmatch(r"[a-z0-9_-]{1,60}",slug) else "restricted",
                  "state":str(item.get("state",""))[:30],
                  "boot":str(item.get("boot",""))[:30],
                  "installed":True})
  out["matter_addons"]=match
 except ValueError:out["addons_list_format"]="not_json"
for name,args in (("options_help",["ha","addons","options","--help"]),("stop_help",["ha","addons","stop","--help"])):
 q=qga(args);out[name+"_status"]=q["status"]
 if q["status"]=="ok":
  txt=" ".join(q["lines"]).lower()
  out[name+"_supports_boot"]=bool(re.search(r"--boot\b",txt))
  out[name+"_mentions_slug"]=bool(re.search(r"\bslug\b",txt))
print("JNS_VM906_MATTER_MANAGEMENT="+json.dumps(out,sort_keys=True))
