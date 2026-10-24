#!/usr/bin/env python3
"""Safe VM906 host access verification from the existing Node C GitHub runner."""
import subprocess,os
def check(label,argv):
 try:
  p=subprocess.run(argv,text=True,capture_output=True,timeout=15)
  print(label,"rc",p.returncode,"stdout",p.stdout[-1400:],"stderr",p.stderr[-200:],flush=True)
 except Exception as e:print(label,"EXC",type(e).__name__,str(e)[:180],flush=True)
print("VM906_NODEC_LOCAL_CAPABILITIES",flush=True)
print("UID",os.getuid(),"PATH",os.environ.get("PATH","")[:180],flush=True)
for path in ("/usr/sbin/qm","/usr/bin/qm","/etc/pve","/usr/local/sbin/jns-gateway-exec"):
 print("EXISTS",path,os.path.exists(path),flush=True)
if os.path.isfile("/usr/sbin/qm"):
 check("QM_STATUS_UNPRIVILEGED",["/usr/sbin/qm","status","906"])
 check("QM_STATUS_SUDO_N",["sudo","-n","/usr/sbin/qm","status","906"])
check("GATEWAY_HELP_UNPRIVILEGED",["/bin/sh","-c","test -r /usr/local/sbin/jns-gateway-exec && echo readable || echo restricted"])
print("VM906_LOCAL_PROBE_DONE",flush=True)

print("=== JNS TRUSTED WRAPPER READ-ONLY CAPABILITY SUMMARY ===",flush=True)
allowed=subprocess.run(["sudo","-n","-l","/usr/local/sbin/jns-gateway-exec"],text=True,capture_output=True,timeout=10)
print("WRAPPER_NOSUDO_PASSWORDLESS_ALLOWED",allowed.returncode==0,flush=True)
from pathlib import Path
import re
w=Path("/usr/local/sbin/jns-gateway-exec")
if w.is_file() and os.access(w,os.R_OK):
 lines=w.read_text(errors="replace").splitlines()
 print("WRAPPER_LINE_COUNT",len(lines),flush=True)
 for i,line in enumerate(lines,1):
  s=line.strip()
  if re.search(r"(?i)(job_type|ha[-_]security|vm906|(^[a-z0-9_-]+\\)|qm guest exec|source_handler|^case |^\s*case )",s):
   if not re.search(r"(?i)(token|secret|password|key|authorization)",s):
    print("ALLOWLIST_STRUCTURE",i,s[:135],flush=True)
else:print("WRAPPER_UNREADABLE",flush=True)
print("=== JNS WRAPPER INVENTORY DONE ===",flush=True)

if w.is_file() and os.access(w,os.R_OK):
 for n,s in enumerate(w.read_text(errors="replace").splitlines(),1):
  if n>=21 and n<=42 and not re.search(r"(?i)(token|password|secret|private|identity|credential|key)",s):
   print("WRAPPER_JOB_MAPPING",n,s.strip()[:160],flush=True)

print("=== BASE GATEWAY JOB TYPE ENUMERATION ===",flush=True)
base=Path("/usr/local/sbin/jns-gateway-exec.base")
if base.is_file() and os.access(base,os.R_OK):
 lines=base.read_text(errors="replace").splitlines()
 print("BASE_WRAPPER_LINES",len(lines),flush=True)
 for i,s in enumerate(lines,1):
  v=s.strip()
  if re.search(r"^([a-z0-9_-]+)(\\|[a-z0-9_-]+)*\\)|^case \\$JOB_TYPE|^case \\"\\$JOB_TYPE",v):
   if len(v)<150 and not re.search(r"(?i)(token|secret|password|key)",v):
    print("BASE_JOB_TYPE",i,v,flush=True)
else:print("BASE_UNREADABLE_OR_MISSING",flush=True)
print("=== BASE CAPABILITY CHECK DONE ===",flush=True)
