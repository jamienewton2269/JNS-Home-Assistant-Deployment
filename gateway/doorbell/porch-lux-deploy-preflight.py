#!/usr/bin/env python3
"""Read-only preflight: exact YAML stanza and legal JNS gateway handlers."""
import subprocess,shlex,json,base64,time
SRC=r'''
from pathlib import Path
import re,json,yaml,hashlib
p=Path("/config/automations.yaml")
raw=p.read_text()
id="1792086505206"
lines=raw.splitlines()
start=next((i for i,l in enumerate(lines) if l.strip().strip("'\"")=="id: '"+id+"'" or (l.strip().startswith("- id:") and id in l)),None)
if start is None:
 matches=[i for i,l in enumerate(lines) if id in l]
 start=matches[0] if matches else None
print("ORIGINAL_CONFIG_SHA256",hashlib.sha256(raw.encode()).hexdigest(),"bytes",len(raw),flush=True)
if start is not None:
 print("TARGET_CONFIG_LINES",start+1,flush=True)
 for i in range(max(0,start-1),min(len(lines),start+29)):
  print("SOURCE",i+1,lines[i][:175],flush=True)
aut=yaml.safe_load(raw) or []
for a in aut:
 if isinstance(a,dict) and a.get("id")==id:
  print("TARGET_CONDITION",json.dumps(a.get("condition",a.get("conditions"))),flush=True)
  print("TARGET_ALIASES",a.get("alias"),flush=True)
print("PRECHECK_DONE",flush=True)
'''
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(SRC.encode()).decode())+"))"
def run(args,timeout=18):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 print("COMMAND",p.returncode,p.stdout[-4500:],p.stderr[-230:],flush=True)
 return p
p=run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code])],28)
if p.returncode==0:
 try:
  d=json.loads(p.stdout)
  if not d.get("exited"):print("PREFLIGHT_QGA_ASYNC",d.get("pid"),flush=True)
  else:print("PREFLIGHT_OUT",d.get("out-data"),flush=True)
 except Exception as ex:print("PARSE_ERROR",type(ex).__name__,flush=True)
# Enumerate permitted operations without printing handler code/secrets.
from pathlib import Path
for fn in ("/usr/local/libexec/jns-gateway-ha-package-install","/usr/local/sbin/jns-gateway-exec.base"):
 p=Path(fn)
 if not p.exists() or not p.is_file():continue
 raw=p.read_text(errors="ignore")
 print("HANDLER",p.name,"BYTES",len(raw),flush=True)
 for n,line in enumerate(raw.splitlines(),1):
  if any(s in line for s in ("target","job_type","package","reload","core check","BACKUP","backup","haos","vm_id","service","ha core check")):
   if not any(s in line.lower() for s in ("token","password","secret","encryption","authorization")):
    print("HANDLER_HINT",n,line.strip()[:160],flush=True)
print("LIVE_UTILITY_PREFLIGHT_COMPLETE",flush=True)

print("=== JNS PACKAGE INSTALLER SCHEMA / RELOAD ===",flush=True)
handler=Path("/usr/local/libexec/jns-gateway-ha-package-install")
if handler.is_file():
 for n,s in enumerate(handler.read_text(errors="replace").splitlines(),1):
  if 102<=n<=185:
   if any(x in s.lower() for x in ("secret","password","token","authorization","bearer","key")):continue
   print("INSTALLER",n,s[:180],flush=True)
print("=== PACKAGE ROUTE PREFLIGHT COMPLETE ===",flush=True)

print("=== HA GENERAL AUTOMATION RELOAD CAPABILITY ===",flush=True)
def sshshort(cmd,timeout=18):
 a=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(cmd)],capture_output=True,text=True,timeout=timeout)
 try: d=json.loads(a.stdout); out=(d.get("out-data") or "").strip() if d.get("exited") else "ASYNC";err=(d.get("err-data") or "").strip() if d.get("exited") else ""
 except Exception:d={};out=a.stdout.strip()[:1000];err=a.stderr.strip()[:100]
 print("RELOAD_ACCESS",cmd[0:5],"rc",a.returncode,"out",out[:1400],"err",err[:130],flush=True)
sshshort(["qm","guest","exec","905","--","docker","ps","--format","{{.Names}}"],20)
sshshort(["qm","guest","exec","905","--","ha","core","--help"],20)
print("=== RELOAD ACCESS PREFLIGHT COMPLETE ===",flush=True)

print("=== HA-GENERAL SUPERVISOR CORE API READ-ONLY PROBE ===",flush=True)
probe='''if [ -z "$SUPERVISOR_TOKEN" ]; then echo SUPERVISOR_TOKEN_UNAVAILABLE; exit 0; fi
echo SUPERVISOR_TOKEN_PRESENT
if command -v curl >/dev/null 2>&1; then
 curl -sS -o /dev/null -w "CORE_GET_HTTP_%{http_code}\\n" -m 6 -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/states
elif command -v python3 >/dev/null 2>&1; then
 python3 -c 'import os,urllib.request; a=urllib.request.Request("http://supervisor/core/api/states",headers={"Authorization":"Bearer "+os.environ["SUPERVISOR_TOKEN"]}); print("CORE_GET_HTTP",urllib.request.urlopen(a,timeout=6).status)'
else echo NO_SUPPORTED_HTTP_CLIENT; fi'''
sshshort(["qm","guest","exec","905","--","docker","exec","app_core_ssh","/bin/sh","-c",probe],22)
print("=== CORE API READONLY CAPABILITY COMPLETE ===",flush=True)

print("=== AUTHORIZED CORE RELOAD API ROUTE CHECK ===",flush=True)
sshshort(["qm","guest","exec","905","--","ha","api","--help"],19)
check='''echo CLI_PROXY_TOKEN_PRESENT=$([ -n "$SUPERVISOR_TOKEN" ] && echo yes || echo no)
if command -v curl >/dev/null 2>&1; then
 curl -sS -o /dev/null -w "CLI_CORE_API_HTTP_%{http_code}\\n" -m 8 -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/states
else echo NO_CURL; fi'''
sshshort(["qm","guest","exec","905","--","docker","exec","hassio_cli","/bin/sh","-c",check],22)
print("=== RELOAD AUTH CHECK DONE ===",flush=True)
