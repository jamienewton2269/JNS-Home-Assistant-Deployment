#!/usr/bin/env python3
"""Read-only live status of one-shot HA905 addon; no credential values."""
import base64,json,os,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
HOST=r'''
import json,os,pathlib,subprocess,time
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
def qga(args,timeout=90):
 try:p=subprocess.run(["qm","guest","exec","905","--",*args],capture_output=True,text=True,timeout=32)
 except (OSError,subprocess.TimeoutExpired):return None
 if p.returncode:return None
 try:j=json.loads(p.stdout)
 except (TypeError,ValueError):return None
 end=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<end:
  if not j.get("pid"):return None
  time.sleep(.8)
  try:p=subprocess.run(["qm","guest","exec-status","905",str(j["pid"])],capture_output=True,text=True,timeout=27)
  except (OSError,subprocess.TimeoutExpired):return None
  if p.returncode:return None
  try:j=json.loads(p.stdout)
  except (TypeError,ValueError):return None
 return j if j.get("exited") else None
def cli(*args):
 j=qga(["ha",*args],75)
 if j is None:return {"qga":"failed"}
 out={"exit":j.get("exitcode"),"truncated":bool(j.get("out-truncated"))}
 try:
  reply=json.loads(j.get("out-data") or "{}")
  out["result"]=reply.get("result")
  data=reply.get("data")
  if args[1]=="list":
   items=data.get("apps",data.get("addons")) if isinstance(data,dict) else data
   out["shape"]="list" if isinstance(items,list) else type(items).__name__
   out["list_size"]=len(items) if isinstance(items,list) else None
   matches=[a for a in (items if isinstance(items,list) else []) if isinstance(a,dict) and
    a.get("slug")=="local_jns_ha905_security_handover"]
   out["matches"]=len(matches)
   if matches:
    a=matches[0]
    out["item_fields"]=sorted(a.keys())
    out["item_state"]=a.get("state")
    out["item_installed"]=a.get("installed")
  elif args[1]=="info":
   out["data_shape"]=type(data).__name__
   if isinstance(data,dict):
    out["state"]=data.get("state")
    out["version"]=data.get("version")
    out["installed"]=data.get("installed")
    out["repository_local"]=data.get("repository")=="local"
   elif reply.get("result")!="ok":
    out["failure_class"]="info_unavailable_or_app_missing"
 except (ValueError,TypeError):
  out["result"]="non_json"
 return out
p="/mnt/data/supervisor/apps/local/jns_ha905_security_handover"
script='''import os,json,pathlib
root=pathlib.Path("/mnt/data/supervisor/apps/local/jns_ha905_security_handover")
share=pathlib.Path("/mnt/data/supervisor/share/jns-security-handover-20261028/enrolment.json")
print("JNS_GUEST_FLAGS="+json.dumps({"source_directory":root.is_dir() and not root.is_symlink(),
"source_files":[(root/f).is_file() for f in ("config.yaml","Dockerfile","run.sh","flow.py")],
"secret_stage_present":share.exists() or share.is_symlink()}))
'''
g=qga(["python3","-c",script],45)
flags={}
if g and g.get("exitcode")==0:
 try:flags=json.loads((g.get("out-data") or "").split("JNS_GUEST_FLAGS=",1)[1].splitlines()[0])
 except (ValueError,IndexError):pass
print("JNS_ESPHOME_APP_RUNTIME="+json.dumps({"inventory":cli("apps","list","--raw-json","--no-progress"),
 "info":cli("apps","info","local_jns_ha905_security_handover","--raw-json","--no-progress"),
 "flags":flags},sort_keys=True))
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 t=subprocess.run(SSH+["nodea","qm status 906"],capture_output=True,text=True,timeout=25)
 if t.returncode or t.stdout.strip()!="status: running":
  print("JNS_ESPHOME_APP_AUDIT_BLOCKED=source_not_running");return 1
 arg=base64.b64encode(HOST.encode()).decode()
 p=subprocess.run(SSH+["nodeb",shlex.join(["python3","-u","-c","exec(__import__('base64').b64decode("+repr(arg)+"))"])],capture_output=True,text=True,timeout=230)
 for line in p.stdout.splitlines():
  if line.startswith("JNS_ESPHOME_APP_RUNTIME="):print(line,flush=True)
 return 0 if p.returncode==0 and "JNS_ESPHOME_APP_RUNTIME=" in p.stdout else 1
if __name__=="__main__":sys.exit(main())
