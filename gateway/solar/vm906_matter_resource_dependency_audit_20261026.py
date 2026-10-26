#!/usr/bin/env python3
"""HA-Security VM906 post-QGA: classify Matter/ESPHome Docker overhead safely.
Never prints raw names, images, entity IDs, config values, credentials or logs.
"""
import json,re,shlex,subprocess,time
HOST="nodea"
def ssh(argv,timeout=25):
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",HOST,shlex.join(argv)]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def qga(cmd):
 first=ssh(["qm","guest","exec","906","--",*cmd],31)
 if not first:return {"status":"no_qga"}
 try:j=json.loads(first)
 except ValueError:return {"status":"bad_guest_reply"}
 for _ in range(40):
  if j.get("exited"):break
  if j.get("pid") is None:break
  time.sleep(.4)
  x=ssh(["qm","guest","exec-status","906",str(j["pid"])],11)
  if not x:break
  try:j=json.loads(x)
  except ValueError:break
 if not j.get("exited"):return {"status":"timeout"}
 return {"status":"ok" if j.get("exitcode")==0 else "command_failed",
         "code":j.get("exitcode"),"lines":(j.get("out-data") or "").splitlines()}
def mb(text):
 part=text.split("/",1)[0].strip()
 m=re.match(r"^([0-9.]+)\s*([A-Za-z]+)$",part)
 if not m:return None
 multiplier={"MiB":1,"GiB":1024,"KiB":1/1024,"B":1/1048576,"MB":1000000/1048576,"GB":1000000000/1048576}
 v=multiplier.get(m.group(2))
 return round(float(m.group(1))*v,1) if v is not None else None
def role(name):
 n=name.lower().strip("/")
 if n=="homeassistant":return "ha_core"
 if n=="matter_server" or "matter_server" in n:return "matter_server"
 if n=="ssh" or n.endswith("_ssh"):return "ssh"
 if n=="hassio_supervisor":return "supervisor"
 if n.startswith("hassio_"):return "haos_"+n.split("_",1)[1]
 if n.startswith("addon_") and "esphome" in n:return "esphome_builder"
 if n.startswith("addon_"):return "other_addon"
 return "other"
p=qga(["docker","ps","-a","--format","{{json .}}"])
s=qga(["docker","stats","--no-stream","--format","{{json .}}"])
out={"read_only":True,"vm":906,"docker_ps_status":p["status"],"docker_stats_status":s["status"]}
if p["status"]=="ok":
 rows=[]
 for l in p.get("lines",[]):
  try:x=json.loads(l)
  except ValueError:continue
  rows.append({"role":role(str(x.get("Names",""))),
               "running":x.get("State")=="running" or str(x.get("Status","")).startswith("Up ")})
 out["docker_roles"]=rows
if s["status"]=="ok":
 mem={}
 for l in s.get("lines",[]):
  try:x=json.loads(l)
  except ValueError:continue
  r=role(str(x.get("Name","")))
  val=mb(str(x.get("MemUsage","")))
  if val is None:continue
  mem[r]=round(mem.get(r,0)+val,1)
 out["memory_mib_by_role"]=mem
# Read integration/registry lists inside Home Assistant Core, output counts only.
PAYLOAD=r'''
import json,pathlib
p=pathlib.Path("/config/.storage")
def values(filename,key):
 try:
  data=json.loads((p/filename).read_text())
  x=data.get("data",{}).get(key,[])
  return x if isinstance(x,list) else []
 except (OSError,ValueError,TypeError):return []
entries=values("core.config_entries","entries")
entities=values("core.entity_registry","entities")
devices=values("core.device_registry","devices")
def cnt(xs,field,name):return sum(x.get(field)==name for x in xs)
print("JNS_RESOURCE_COUNTS="+json.dumps({
 "entries_matter":cnt(entries,"domain","matter"),
 "entries_esphome":cnt(entries,"domain","esphome"),
 "matter_entities":cnt(entities,"platform","matter"),
 "esphome_entities":cnt(entities,"platform","esphome"),
 "matter_device_registrations":sum(any(str(c.get("domain",""))=="matter" for c in x.get("identifiers",[]) if isinstance(c,dict)) for x in devices),
 "config_entry_total":len(entries),"entity_total":len(entities),"device_total":len(devices)
},sort_keys=True))
'''
q=qga(["docker","exec","homeassistant","python3","-c",PAYLOAD])
out["registry_query_status"]=q["status"]
if q["status"]=="ok":
 for line in q["lines"]:
  if line.startswith("JNS_RESOURCE_COUNTS="):
   try:out["registries"]=json.loads(line.split("=",1)[1])
   except ValueError:out["registries_status"]="invalid"
# Supervisor 'ha core info' is read-only; emit only known status string.
h=qga(["ha","core","info"])
out["ha_core_info_command"]=h["status"]
if h["status"]=="ok":
 for l in h["lines"]:
  if l.lower().startswith(("state:","version:","boot:")):
   k,v=l.split(":",1)
   if re.fullmatch(r"[a-z0-9 ._-]{1,40}",v.strip(),re.I):
    out["core_"+k.lower()]=v.strip()
print("JNS_VM906_MATTER_SECURITY_PROFILE="+json.dumps(out,sort_keys=True),flush=True)
