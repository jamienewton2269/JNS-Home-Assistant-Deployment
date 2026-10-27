#!/usr/bin/env python3
"""Read-only check if HA-General has loaded the staged security passive helpers.
No HA writes, integration activation, restarts or credential output.
"""
import base64,json,os,shlex,subprocess,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
INNER=r'''
import datetime,json,os,pathlib,re,subprocess
p=pathlib.Path("/config/packages/jns_ha_security_passive_helpers_20261027.yaml")
o={"helper_file_present":p.is_file() and not p.is_symlink()}
if o["helper_file_present"]:
 txt=p.read_text(errors="replace")
 o["helpers_header_present"]="JNS Security passive helper definitions only" in txt
 groups={}
 current=None
 for line in txt.splitlines():
  m=re.match(r"^(input_boolean|input_select|input_text):",line)
  if m:current=m.group(1);groups.setdefault(current,0);continue
  if current and re.match(r"^  [A-Za-z][A-Za-z0-9_]*\s*:",line):groups[current]+=1
 o["helper_counts"]=groups
 o["helper_file_mtime_utc"]=datetime.datetime.fromtimestamp(p.stat().st_mtime,datetime.timezone.utc).isoformat()
else:o["helper_counts"]={}
info=pathlib.Path("/config/.storage/core.entity_registry")
try:
 entities=json.loads(info.read_text()).get("data",{}).get("entities",[])
 o["registered_helpers_by_domain"]={d:sum(isinstance(e,dict) and str(e.get("entity_id","")).startswith(d+".") for e in entities) for d in ("input_boolean","input_select","input_text")}
except (OSError,ValueError,TypeError):o["registered_helpers_by_domain"]={}
print("JNS_SECURITY_HELPER_INSPECTION="+json.dumps(o,sort_keys=True))
'''
def run(argv,timeout=20):
 try:return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def ssh(host,args,timeout=28):
 r=run(SSH+[host,shlex.join(args)],timeout)
 return r.stdout if r and r.returncode==0 else None
def guest(host,vm,args):
 s=ssh(host,["qm","guest","exec",str(vm),"--",*args],35)
 if not s:return None
 try:j=json.loads(s)
 except ValueError:return None
 for _ in range(55):
  if j.get("exited"):return j if j.get("exitcode")==0 else None
  if not j.get("pid"):break
  time.sleep(.4)
  s=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],18)
  try:j=json.loads(s) if s else {}
  except ValueError:break
 return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_SECURITY_ACTIVATION_AUDIT=wrong_runner");return 1
 out={}
 for vm,node in ((905,"nodeb"),(906,"nodea")):
  status=ssh(node,["qm","status",str(vm)])
  out["vm"+str(vm)+"_running"]=bool(status and status.strip()=="status: running")
 if not all(out.values()):
  print("JNS_SECURITY_ACTIVATION_AUDIT="+json.dumps(out,sort_keys=True));return 1
 cfg=ssh("nodeb",["qm","config","905"]) or ""
 out["vm905_configured_2gb"]=bool("memory: 2048" in cfg)
 out["vm905_balloon_disabled"]=bool("balloon: 0" in cfg)
 inspect=guest("nodeb",905,["docker","inspect","homeassistant","--format","{{.State.StartedAt}}"])
 started=None
 if inspect:
  started=(inspect.get("out-data") or "").strip()
 b64=base64.b64encode(INNER.encode()).decode()
 j=guest("nodeb",905,["docker","exec","homeassistant","python3","-c",
       "exec(__import__('base64').b64decode('"+b64+"'))"])
 profile={}
 if j:
  marks=[x.split("=",1)[1] for x in (j.get("out-data") or "").splitlines() if x.startswith("JNS_SECURITY_HELPER_INSPECTION=")]
  if len(marks)==1:
   try:profile=json.loads(marks[0])
   except ValueError:pass
 out["security_helpers"]=profile
 out["core_started_utc"]=started if started and len(started)<50 else None
 needs_restart=None
 if started and profile.get("helper_file_mtime_utc"):
  try:
   from datetime import datetime,timezone
   start=datetime.fromisoformat(started.replace("Z","+00:00"))
   change=datetime.fromisoformat(profile["helper_file_mtime_utc"])
   needs_restart=start<change
  except ValueError:pass
 out["core_started_before_helper_stage"]=needs_restart
 out["no_runtime_changes"]=True
 print("JNS_SECURITY_ACTIVATION_AUDIT="+json.dumps(out,sort_keys=True),flush=True)
 return 0
if __name__=="__main__":
 raise SystemExit(main())
