#!/usr/bin/env python3
"""Solar read-only preflight for safe Natural Automation/Steward Node B -> C.
No secrets, file contents or network addresses in public workflow logs.
"""
import json,os,pathlib,shlex,subprocess
REMOTE=r'''
import json, pathlib,os,subprocess
p=pathlib.Path("/opt/natural-automation")
files=[p/"natural_automation.py",p/"VERSION",p/"data/steward.db",
       p/"data/knowledge/current_chat_seed.md",p/"data/knowledge/site_state.json"]
folders=[p/"steward",p/"data/knowledge",p/"tools",pathlib.Path("/opt/real-progress")]
out={"status":"ok"}
for x in files:
 try:
  t=x.lstat()
  out[x.name]={"exists":x.is_file(),"symlink":x.is_symlink(),"bytes":t.st_size}
 except OSError:out[x.name]={"exists":False}
for x in folders:
 try:
  total,count,links=0,0,0
  for q in x.rglob("*"):
   if q.is_symlink():links+=1;continue
   if q.is_file():total+=q.stat().st_size;count+=1
  out["dir_"+x.name]={"exists":x.is_dir(),"bytes":total,"files":count,"symlinks":links}
 except (OSError,PermissionError):out["dir_"+x.name]={"status":"unavailable"}
try:
 u=subprocess.run(["systemctl","cat","natural-automation.service"],capture_output=True,text=True,timeout=5)
 out["systemd_unit_readable"]=u.returncode==0
 out["service_uses_apply_gate"]="NA_ENABLE_APPLY=" in u.stdout
except Exception:out["systemd_unit_readable"]=False
print("NODEB_SAFE_EXPORT_PREFLIGHT="+json.dumps(out,sort_keys=True))
'''
def call(host,cmd):
 try:r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",host,shlex.join(cmd)],capture_output=True,text=True,timeout=35)
 except (OSError,subprocess.TimeoutExpired):return {"status":"transport_unavailable"}
 if r.returncode:return {"status":"remote_error"}
 for line in r.stdout.splitlines():
  if line.startswith("NODEB_SAFE_EXPORT_PREFLIGHT="):
   try:return json.loads(line.split("=",1)[1])
   except ValueError:break
 return {"status":"not_found"}
def main():
 print("JNS_STEWARD_NODEC_STAGE_PREFLIGHT_READONLY")
 print("NODEB="+json.dumps(call("nodeb",["python3","-c",REMOTE]),sort_keys=True))
 paths=["/var/lib/jns-steward","/opt/natural-automation"]
 print("NODEC="+json.dumps({"host":os.uname().nodename.split(".")[0],
  "runner_uid_root":os.geteuid()==0,
  "private_home_writable":os.access(pathlib.Path.home(),os.W_OK),
  "protected_steward_exists":pathlib.Path(paths[0]).is_dir(),
  "protected_steward_runner_writable":os.access(paths[0],os.W_OK),
  "natural_automation_path_exists":pathlib.Path(paths[1]).exists(),
  "sudo_noninteractive_allowed":subprocess.run(["sudo","-n","-l"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8).returncode==0},sort_keys=True))
 print("JNS_STEWARD_NODEC_STAGE_PREFLIGHT_COMPLETE")
if __name__=="__main__":main()
