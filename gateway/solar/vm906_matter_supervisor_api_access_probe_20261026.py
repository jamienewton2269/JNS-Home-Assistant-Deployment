#!/usr/bin/env python3
"""Read-only probe of HAOS authenticated Supervisor API transport, no token values."""
import subprocess,shlex,json,time
def ssh(argv,timeout=30):
 try:r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
 "-o","ConnectTimeout=5","nodea",shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return r.stdout if r.returncode==0 else None
def qga(argv):
 raw=ssh(["qm","guest","exec","906","--",*argv],35)
 if not raw:return {"status":"unavailable"}
 try:j=json.loads(raw)
 except ValueError:return {"status":"invalid"}
 for _ in range(50):
  if j.get("exited"):break
  if j.get("pid") is None:break
  time.sleep(.3)
  raw=ssh(["qm","guest","exec-status","906",str(j["pid"])],12)
  if not raw:break
  try:j=json.loads(raw)
  except ValueError:break
 return {"status":"ok" if j.get("exited") and j.get("exitcode")==0 else "failed",
         "out":j.get("out-data",""),"err":j.get("err-data","")}
out={}
a=qga(["ha","apps","--help"])
out["cli_help_status"]=a["status"]
out["cli_subcommands"]=[l.strip()[:100] for l in a["out"].splitlines()
 if l.startswith("  ") and len(l)<130 and not l.startswith("    ")][:38]
code=r'''
import json,os,shutil
print("JNS_ENV_TRANSPORT="+json.dumps({
 "SUPERVISOR_TOKEN":bool(os.environ.get("SUPERVISOR_TOKEN")),
 "HASSIO_TOKEN":bool(os.environ.get("HASSIO_TOKEN")),
 "SUPERVISOR_API_TOKEN":bool(os.environ.get("SUPERVISOR_API_TOKEN")),
 "python":True,
 "curl":bool(shutil.which("curl")),
 "wget":bool(shutil.which("wget")),
}))
'''
a=qga(["docker","exec","homeassistant","python3","-c",code])
out["core_probe"]=a["status"]
if a["status"]=="ok":
 for l in a["out"].splitlines():
  if l.startswith("JNS_ENV_TRANSPORT="):
   try:out["core_transport"]=json.loads(l.split("=",1)[1])
   except ValueError:pass
shell=r'''env | grep -q '^SUPERVISOR_TOKEN=.' && a=1 || a=0
env | grep -q '^HASSIO_TOKEN=.' && b=1 || b=0
env | grep -q '^SUPERVISOR_API_TOKEN=.' && c=1 || c=0
command -v curl >/dev/null 2>&1 && d=1 || d=0
command -v wget >/dev/null 2>&1 && e=1 || e=0
printf 'JNS_CAPS=%s,%s,%s,%s,%s\n' "$a" "$b" "$c" "$d" "$e"'''
for service in ("hassio_cli","addon_core_ssh","hassio_supervisor"):
 q=qga(["docker","exec",service,"sh","-c",shell])
 out[service+"_exec"]=q["status"]
 if q["status"]=="ok":
  for l in q["out"].splitlines():
   if l.startswith("JNS_CAPS="):
    out[service+"_token_and_http_clients"]=l.split("=",1)[1].split(",")
print("JNS_MATTER_API_TRANSPORT="+json.dumps(out,sort_keys=True),flush=True)
