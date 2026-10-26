#!/usr/bin/env python3
"""Read-only Docker stats of named noncore services in HAOS via QGA.
Print ONLY allowlisted roles and MiB of RAM, no container names/images.
"""
import json,re,subprocess,shlex,time
for vm,node in ((902,"nodea"),(905,"nodeb")):
 def ssh(args,seconds=18):
  try:r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",node,shlex.join(args)],capture_output=True,text=True,timeout=seconds)
  except (OSError,subprocess.TimeoutExpired):return None
  return r.stdout if r.returncode==0 else None
 raw=ssh(["qm","guest","exec",str(vm),"--","docker","stats","--no-stream","--format","{{json .}}"],28)
 if raw is None:
  print("VM"+str(vm)+"_ADDON_MEM="+json.dumps({"status":"unavailable"}));continue
 try:j=json.loads(raw)
 except ValueError:
  print("VM"+str(vm)+"_ADDON_MEM="+json.dumps({"status":"invalid"}));continue
 for _ in range(30):
  if j.get("exited"):break
  if not j.get("pid"):break
  time.sleep(.3)
  raw=ssh(["qm","guest","exec-status",str(vm),str(j["pid"])],10)
  if raw is None:break
  try:j=json.loads(raw)
  except ValueError:break
 if j.get("exitcode")!=0:
  print("VM"+str(vm)+"_ADDON_MEM="+json.dumps({"status":"failed"}));continue
 data={}
 for line in (j.get("out-data") or "").splitlines():
  try:x=json.loads(line)
  except ValueError:continue
  name=x.get("Name","").lower()
  cat=next((key for key in ("piper","samba","ssh") if name.endswith("_"+key) or name==key),"other")
  if cat=="other":continue
  part=x.get("MemUsage","").split("/",1)[0].strip()
  m=re.fullmatch(r"([0-9.]+)\s*([A-Za-z]+)",part)
  if not m:continue
  multipliers={"MiB":1,"GiB":1024,"KiB":1/1024,"B":1/1048576,"MB":1000/1048.576,"GB":1000000/1048.576}
  val=float(m.group(1))*multipliers.get(m.group(2),0)
  data[cat]=round(data.get(cat,0)+val,1)
 print("VM"+str(vm)+"_ADDON_MEM="+json.dumps({"status":"ok","mem_mib":data},sort_keys=True))
