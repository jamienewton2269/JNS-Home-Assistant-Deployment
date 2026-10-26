#!/usr/bin/env python3
"""Read-only Supervisor CLI contract for Matter; output metadata only."""
import json,time,shlex,subprocess,re
def ssh(args):
 try:r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
 "nodea",shlex.join(args)],capture_output=True,text=True,timeout=36)
 except (OSError,subprocess.TimeoutExpired):return None
 return r.stdout if r.returncode==0 else None
def qga(args):
 v=ssh(["qm","guest","exec","906","--",*args])
 if not v:return {"status":"unavailable"}
 try:x=json.loads(v)
 except ValueError:return {"status":"invalid"}
 for _ in range(35):
  if x.get("exited"):break
  if not x.get("pid"):break
  time.sleep(.25)
  t=ssh(["qm","guest","exec-status","906",str(x["pid"])])
  if not t:break
  try:x=json.loads(t)
  except ValueError:break
 return {"status":"ok" if x.get("exited") and x.get("exitcode")==0 else "failed",
         "out":x.get("out-data",""),"err":x.get("err-data","")}
result={}
for name,cmd in [
 ("matter_info",["ha","addons","info","core_matter_server","--raw-json"]),
 ("addons_options_help",["ha","addons","options","--help"]),
 ("addons_stop_help",["ha","addons","stop","--help"])]:
 x=qga(cmd)
 result[name+"_status"]=x["status"]
 if name=="matter_info" and x["status"]=="ok":
  try:
   v=json.loads(x["out"])
   d=v.get("data",v)
   if isinstance(d,dict):
    result["matter_info"]={k:d.get(k) for k in ("slug","name","boot","state","version",
       "startup","protected","watchdog","update_available") if k in d}
    result["info_has_data_wrapper"]="data" in v
  except (ValueError,TypeError):result["matter_info_parse"]="failed"
 else:
  result[name+"_boot_option"]=bool(re.search(r"--boot\b",x["out"]+x["err"]))
  result[name+"_usage"]=[l.strip()[:190] for l in (x["out"]+x["err"]).splitlines()
       if "Usage:" in l or "--boot" in l or "manual" in l][:7]
print("JNS_MATTER_SUPERVISOR_CONTRACT="+json.dumps(result,sort_keys=True),flush=True)
