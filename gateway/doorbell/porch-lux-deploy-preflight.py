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
