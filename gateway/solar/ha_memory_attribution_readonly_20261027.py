#!/usr/bin/env python3
"""JNS HA cross-role memory attribution. READ-ONLY.
Invoked by Node C GitHub runner. Authorised SSH -> QEMU guest-agent only.
Emits aggregate MiB, process role, counts of integration domains; never
prints private addresses, names, identifiers, file contents, tokens or logs.
No shutdown, restart, migration, config change or service action.
"""
import base64, json, re, shlex, subprocess, time
ROLES=(("primary",902,"nodea"),("general",905,"nodeb"),("security",906,"nodea"))
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
     "-o","ConnectTimeout=6"]
INNER=r'''
import json,os,re,pathlib
from collections import Counter
out={}
def val(name):
 try: return pathlib.Path(name).read_text()
 except (OSError,PermissionError):return ""
def mib(n):return round(n/1048576,1)
out["pid1_comm"]=val("/proc/1/comm").strip()[:40]
status={}
for line in val("/proc/1/status").splitlines():
 m=re.match(r"^(VmRSS|VmSize|VmSwap|RssAnon|RssFile|RssShmem):\s+(\d+)\s+kB",line)
 if m:status[m.group(1)+"_MiB"]=round(int(m.group(2))/1024,1)
out["pid1_status"]=status
rollup={}
for line in val("/proc/1/smaps_rollup").splitlines():
 m=re.match(r"^(Rss|Pss|Pss_Anon|Pss_File|Pss_Shmem|Shared_Clean|Shared_Dirty|Private_Clean|Private_Dirty|Anonymous|Swap|SwapPss):\s+(\d+)\s+kB",line)
 if m:rollup[m.group(1)+"_MiB"]=round(int(m.group(2))/1024,1)
out["pid1_smaps_rollup"]=rollup
group=val("/proc/self/cgroup")
match=re.search(r"0::(/[^\n]*)",group)
base=pathlib.Path("/sys/fs/cgroup") / match.group(1).lstrip("/") if match else pathlib.Path("/sys/fs/cgroup")
stat={}
for line in val(str(base/"memory.stat")).splitlines():
 bits=line.split()
 if len(bits)==2 and bits[1].isdecimal() and bits[0] in (
     "anon","file","kernel","kernel_stack","pagetables","sock",
     "shmem","file_mapped","inactive_file","active_file",
     "slab","slab_reclaimable","slab_unreclaimable","anon_thp"):
  stat[bits[0]+"_MiB"]=mib(int(bits[1]))
out["core_cgroup_breakdown"]=stat
for k in ("memory.current","memory.swap.current"):
 s=val(str(base/k)).strip()
 if s.isdecimal():out[k.replace(".","_")+"_MiB"]=mib(int(s))
entries=[]
try:
 entries=json.loads(pathlib.Path("/config/.storage/core.config_entries").read_text()).get("data",{}).get("entries",[])
except (OSError,ValueError,TypeError):pass
counts=Counter()
enabled=Counter()
for item in entries:
 dom=item.get("domain")
 if isinstance(dom,str) and re.fullmatch(r"[a-z][a-z0-9_]{1,50}",dom):
  counts[dom]+=1
  if not item.get("disabled_by"):enabled[dom]+=1
out["integrations_domains"]=dict(sorted(counts.items()))
out["integrations_enabled_domains"]=dict(sorted(enabled.items()))
out["integrations_total"]=len(entries)
print("JNS_SAFE_HA_CORE_PROFILE="+json.dumps(out,sort_keys=True))
'''
def ssh(node,argv,timeout=30):
 try:
  p=subprocess.run(SSH+[node,shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
  return p.stdout if p.returncode==0 else None
 except (OSError,subprocess.TimeoutExpired):return None
def qga(node,vm,argv,timeout=60):
 raw=ssh(node,["qm","guest","exec",str(vm),"--",*argv],min(timeout,35))
 if raw is None:return {"status":"unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"invalid_response"}
 for _ in range(45):
  if j.get("exited"):break
  if not j.get("pid"):break
  time.sleep(.3)
  raw=ssh(node,["qm","guest","exec-status",str(vm),str(j["pid"])],16)
  if raw is None:break
  try:j=json.loads(raw)
  except ValueError:break
 if not j.get("exited"):return {"status":"timeout"}
 if j.get("exitcode")!=0:return {"status":"command_failed"}
 return {"status":"ok","stdout":j.get("out-data","")}
def role(name):
 n=str(name).lower()
 if n=="homeassistant":return "core"
 for role in ("supervisor","matter","piper","samba","ssh","observer","multicast","audio","dns","cli","go2rtc","esphome","mosquitto","zigbee"):
  if role in n:return role
 return "unclassified"
def docker_mem(text):
 out={}
 total=0
 for line in text.splitlines():
  try:x=json.loads(line)
  except ValueError:continue
  m=re.match(r"([\d.]+)\s*(B|KiB|MiB|GiB|MB|GB)",str(x.get("MemUsage","")).split("/")[0].strip())
  if not m:continue
  mult={"B":1/1048576,"KiB":1/1024,"MiB":1,"GiB":1024,"MB":1000000/1048576,"GB":1000000000/1048576}
  v=float(m.group(1))*mult[m.group(2)]
  r=role(x.get("Name",""))
  out[r]=round(out.get(r,0)+v,1)
  total+=v
 return {"docker_mem_mib_by_role":out,"docker_mem_sum_mib":round(total,1)}
def meminfo(text):
 keep={"MemAvailable","MemFree","Cached","Buffers","AnonPages","SwapTotal","SwapFree","Shmem","SReclaimable","SUnreclaim","Slab"}
 out={}
 for line in text.splitlines():
  m=re.match(r"^([A-Za-z]+):\s+(\d+)\s+kB",line)
  if m and m.group(1) in keep:out[m.group(1)+"_MiB"]=round(int(m.group(2))/1024,1)
 return out
def audit(label,vm,node):
 output={"role":label,"host":node,"vm":vm}
 s=ssh(node,["qm","status",str(vm)],15)
 output["vm_status"]=s.strip().removeprefix("status: ") if s else "unavailable"
 if output["vm_status"]!="running":return output
 raw=ssh(node,["pvesh","get",f"/nodes/{node}/qemu/{vm}/status/current","--output-format","json"],20)
 try:
  j=json.loads(raw) if raw else {}
  for k in ("mem","maxmem"):
   if isinstance(j.get(k),(int,float)):output["pve_"+k+"_MiB"]=round(j[k]/1048576,1)
 except ValueError:pass
 stats=qga(node,vm,["docker","stats","--no-stream","--format","{{json .}}"],65)
 if stats["status"]=="ok":output.update(docker_mem(stats["stdout"]))
 else:output["docker_stats_status"]=stats["status"]
 m=qga(node,vm,["cat","/proc/meminfo"],35)
 if m["status"]=="ok":output["guest_meminfo"]=meminfo(m["stdout"])
 else:output["guest_meminfo_status"]=m["status"]
 src=base64.b64encode(INNER.encode()).decode()
 core=qga(node,vm,["docker","exec","homeassistant","python3","-c",
                    "exec(__import__('base64').b64decode('"+src+"'))"],65)
 if core["status"]=="ok":
  rows=[x.split("=",1)[1] for x in core["stdout"].splitlines() if x.startswith("JNS_SAFE_HA_CORE_PROFILE=")]
  if len(rows)==1:
   try:output["core"]=json.loads(rows[0])
   except ValueError:output["core_status"]="invalid_json"
  else:output["core_status"]="missing_data"
 else:output["core_status"]=core["status"]
 return output
print("JNS_HA_MEM_ATTRIBUTION_BEGIN")
for label,vm,node in ROLES:
 print("JNS_HA_MEM_ATTRIBUTION="+json.dumps(audit(label,vm,node),sort_keys=True),flush=True)
print("JNS_HA_MEM_ATTRIBUTION_END")
