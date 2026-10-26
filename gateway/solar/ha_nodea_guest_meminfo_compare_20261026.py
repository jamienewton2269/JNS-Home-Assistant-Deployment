#!/usr/bin/env python3
"""Read-only guest Linux RAM/cache/swap comparison of VM902 vs VM906 on Node A.

Run only from Node C trusted runner -> Node A existing SSH -> QGA.
Only whitelisted /proc/meminfo keys are emitted, no config/identifiers.
"""
import json,re,time,shlex,subprocess
KEYS=("MemTotal","MemFree","MemAvailable","Buffers","Cached","SwapCached","SwapTotal","SwapFree",
"Active","Inactive","Active(anon)","Inactive(anon)","Active(file)","Inactive(file)",
"AnonPages","Mapped","Shmem","KReclaimable","SReclaimable","SUnreclaim","Slab",
"PageTables","Unevictable","Dirty","Writeback","Committed_AS")
def ssh(cmd,timeout=30):
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
       "nodea",shlex.join(cmd)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def qga(vm,argv):
 raw=ssh(["qm","guest","exec",str(vm),"--",*argv],29)
 if not raw:return {"status":"unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"invalid_json"}
 for _ in range(35):
  if j.get("exited"):break
  if not j.get("pid"):break
  time.sleep(.35)
  r=ssh(["qm","guest","exec-status",str(vm),str(j["pid"])],10)
  if not r:break
  try:j=json.loads(r)
  except ValueError:break
 if not j.get("exited"):return {"status":"timeout"}
 return {"status":"ok" if j.get("exitcode")==0 else "failed","raw":j.get("out-data","")}
def read(vm):
 state=ssh(["qm","status",str(vm)],15)
 out={"vm":vm,"state":state.strip().replace("status: ","") if state else "unavailable"}
 if out["state"]!="running":return out
 data=qga(vm,["cat","/proc/meminfo"])
 out["guest_meminfo_status"]=data["status"]
 if data["status"]=="ok":
  metrics={}
  for line in data["raw"].splitlines():
   m=re.match(r"^([A-Za-z_()]+):\s+(\d+)\s+kB",line)
   if m and m.group(1) in KEYS:metrics[m.group(1)+"_MiB"]=round(int(m.group(2))/1024,1)
  out["meminfo"]=metrics
 pressure=qga(vm,["cat","/proc/pressure/memory"])
 if pressure["status"]=="ok":
  pr={}
  for line in pressure["raw"].splitlines():
   if line.startswith(("some ","full ")):
    bits=line.split()
    row={}
    for x in bits[1:]:
     if "=" in x:
      key,val=x.split("=",1)
      if key in ("avg10","avg60","avg300"):
       try:row[key]=float(val)
       except ValueError:pass
    pr[bits[0]]=row
  out["psi_memory"]=pr
 return out
for vm in (902,906):
 print("JNS_HA_GUEST_MEMORY="+json.dumps(read(vm),sort_keys=True),flush=True)
print("JNS_RAM_AUDIT_READONLY=yes")
