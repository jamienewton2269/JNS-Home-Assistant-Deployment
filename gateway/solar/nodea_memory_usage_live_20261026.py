#!/usr/bin/env python3
"""JNS Solar Node A memory inventory, READ ONLY.
Outputs current memory, ZFS ARC, running Proxmox guest PVE memory usage,
QEMU RSS and top host processes without command lines, secrets or addresses.
"""
import base64,json,shlex,subprocess
REMOTE=r'''
import json,subprocess,re,time,os
def run(argv,timeout=14):
 try:
  p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p if p.returncode==0 else None
def gib(n):
 return round(n/1073741824,3) if isinstance(n,(int,float)) else None
def parse_meminfo():
 d={}
 try:
  for line in open("/proc/meminfo"):
   m=re.match(r"^([A-Za-z_()]+):\s+(\d+) kB",line)
   if m and m.group(1) in {"MemTotal","MemFree","MemAvailable","Buffers","Cached","SReclaimable","SUnreclaim","Slab","Shmem","SwapTotal","SwapFree","KReclaimable","AnonPages","Mapped","PageTables","Unevictable"}:
    d[m.group(1)+"_GiB"]=gib(int(m.group(2))*1024)
 except OSError:pass
 return d
def arcstats():
 keys={"size","c","c_min","c_max","arc_meta_used","data_size","metadata_size"}
 d={}
 try:
  for line in open("/proc/spl/kstat/zfs/arcstats"):
   parts=line.split()
   if len(parts)>=3 and parts[0] in keys and parts[2].isdigit():
    d[parts[0]+"_GiB"]=gib(int(parts[2]))
 except OSError:d["available"]=False
 return d
def pve_status(kind,vm):
 base=["pvesh","get","/nodes/nodea/"+kind+"/"+str(vm)+"/status/current","--output-format","json"]
 r=run(base,15)
 if not r:return {"id":vm,"status":"unavailable"}
 try:j=json.loads(r.stdout)
 except ValueError:return {"id":vm,"status":"unparsable"}
 d={"id":vm,"status":j.get("status","unknown"),"name":j.get("name","unknown")}
 for k in ("mem","maxmem","swap","maxswap","disk","maxdisk"):
  if isinstance(j.get(k),(int,float)):
   d[k+"_GiB"]=gib(j[k])
 if isinstance(j.get("cpu"),(int,float)):d["cpu_fraction"]=round(j["cpu"],3)
 return d
def list_ids(kind):
 r=run(["pct" if kind=="lxc" else "qm","list"],15)
 out=[]
 if r:
  for row in r.stdout.splitlines()[1:]:
   bits=row.split()
   if bits and bits[0].isdigit():out.append(int(bits[0]))
 return sorted(set(out))
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":
 raise SystemExit(70)
out={"host":"nodea","utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
 "meminfo":parse_meminfo(),"zfs_arc":arcstats()}
f=run(["free","-b"])
if f:
 for line in f.stdout.splitlines():
  bits=line.split()
  if bits and bits[0] in ("Mem:","Swap:"):
   out[bits[0].rstrip(":")+"_free_command_GiB"]={k:gib(int(v)) for k,v in zip(["total","used","free","shared","buff_cache","available"] if bits[0]=="Mem:" else ["total","used","free"],bits[1:])}
out["running_vms"]=[]
out["running_containers"]=[]
out["stopped_guest_ids"]={"vm":[],"lxc":[]}
for kind in ("qemu","lxc"):
 for vm in list_ids(kind):
  info=pve_status(kind,vm)
  if info.get("status")=="running":
   out["running_vms" if kind=="qemu" else "running_containers"].append(info)
  elif info.get("status")=="stopped":
   out["stopped_guest_ids"]["vm" if kind=="qemu" else "lxc"].append(vm)
  else:
   out.setdefault("unknown_guest_status",[]).append({"id":vm,"type":kind,"status":info.get("status")})
p=run(["ps","-eo","pid=,comm=,rss=,args=","--sort=-rss"],18)
if p:
 result=[]
 for row in p.stdout.splitlines():
  parts=row.split(maxsplit=3)
  if len(parts)<3:continue
  pid,comm,rss=parts[:3]
  if not pid.isdigit() or not rss.isdigit():continue
  if int(rss)<18000:break
  item={"comm":comm[:45],"rss_GiB":gib(int(rss)*1024)}
  cmd=parts[3] if len(parts)>=4 else ""
  if comm in ("kvm","qemu-system-x86","qemu-system-x86_64") or "qemu-system" in comm:
   m=re.search(r"(?:^|\s)-id\s+(\d+)(?:\s|$)",cmd)
   if m:item["vmid"]=int(m.group(1))
  result.append(item)
  if len(result)>=27:break
 out["top_process_rss"]=result
p=run(["cat","/proc/pressure/memory"])
if p:
 out["memory_pressure"]={}
 for row in p.stdout.splitlines():
  if row.startswith(("some ","full ")):
   t=row.split()
   out["memory_pressure"][t[0]]={k:float(v) for k,v in (x.split("=",1) for x in t[1:] if "=" in x) if k in ("avg10","avg60","avg300")}
print("JNS_NODEA_MEMORY_REPORT="+json.dumps(out,sort_keys=True))
'''
def main():
 encoded=base64.b64encode(REMOTE.encode()).decode()
 argv=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
       "nodea",shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
 try:p=subprocess.run(argv,capture_output=True,text=True,timeout=140)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_NODEA_MEMORY_AUDIT_BLOCKED=ssh_timeout");raise SystemExit(1)
 if p.returncode:
  print("JNS_NODEA_MEMORY_AUDIT_BLOCKED=remote_rc_"+str(p.returncode));raise SystemExit(1)
 rows=[x for x in p.stdout.splitlines() if x.startswith("JNS_NODEA_MEMORY_REPORT=")]
 if len(rows)!=1:
  print("JNS_NODEA_MEMORY_AUDIT_BLOCKED=missing_result");raise SystemExit(1)
 print(rows[0])
if __name__=="__main__":main()
