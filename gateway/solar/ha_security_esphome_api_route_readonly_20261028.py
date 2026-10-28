#!/usr/bin/env python3
"""Inspect available HAOS SSH app Core API proxy route (status only).
No token values, addon names, URLs, IPs or private data printed.
"""
import base64,json,os,shlex,subprocess,time
SHELL=r'''
import json,subprocess
out={"ssh_app_candidates":0,"supervisor_proxy_authenticated":False,
     "config_flow_available":False,"python3_available":False}
p=subprocess.run(["docker","ps","--format","{{.Names}}"],capture_output=True,text=True,timeout=20)
if p.returncode:raise SystemExit(72)
names=[x.strip() for x in p.stdout.splitlines() if x.strip().startswith("addon_") and "ssh" in x.lower()]
out["ssh_app_candidates"]=len(names)
for name in names:
 code="""if command -v curl >/dev/null && [ -n "$SUPERVISOR_TOKEN" ]; then
 curl -sSL -m 8 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/;
 else echo unknown; fi"""
 r=subprocess.run(["docker","exec",name,"/bin/sh","-c",code],capture_output=True,text=True,timeout=20)
 if r.returncode==0 and r.stdout.strip()=="200":
  out["supervisor_proxy_authenticated"]=True
  other="""curl -sSL -m 8 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/config/config_entries/flow_handlers"""
  z=subprocess.run(["docker","exec",name,"/bin/sh","-c",other],capture_output=True,text=True,timeout=18)
  out["config_flow_available"]=z.returncode==0 and z.stdout.strip()=="200"
  t=subprocess.run(["docker","exec",name,"/bin/sh","-c","command -v python3 >/dev/null"],capture_output=True,timeout=8)
  out["python3_available"]=t.returncode==0
  break
print("JNS_SECURITY_CORE_API_ROUTE="+json.dumps(out,sort_keys=True))
'''
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 b=base64.b64encode(SHELL.encode()).decode()
 cmd=SSH+["nodeb",shlex.join(["qm","guest","exec","905","--","python3","-c",
     "exec(__import__('base64').b64decode('"+b+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
 except (OSError,subprocess.TimeoutExpired):return 1
 try:j=json.loads(p.stdout)
 except ValueError:return 1
 if not j.get("exited") and j.get("pid"):
  q=subprocess.run(SSH+["nodeb",shlex.join(["qm","guest","exec-status","905",str(j["pid"])])],
                   capture_output=True,text=True,timeout=30)
  try:j=json.loads(q.stdout)
  except ValueError:return 1
 for s in str(j.get("out-data","")).splitlines():
  if s.startswith("JNS_SECURITY_CORE_API_ROUTE="):print(s,flush=True)
 print("JNS_SECURITY_API_ROUTE_READONLY=yes",flush=True)
 return 0 if j.get("exitcode")==0 else 1
if __name__=="__main__":raise SystemExit(main())
