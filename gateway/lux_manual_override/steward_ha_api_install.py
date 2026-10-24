#!/usr/bin/env python3
"""Install the allowlisted Steward reload helper into HA-General Core.
No token, Home Assistant restart, automations edit or API call.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, "gateway/arrival_lighting")
from readiness_probe import ssh_host

SOURCE = Path("natural_automation_steward/ops/ha_general_reload_capability.py").read_bytes()
assert SOURCE.startswith(b"#!/usr/bin/env python3\n")
code = r"""
import base64,hashlib,json,os,stat,tempfile
from pathlib import Path
directory=Path("/config/.jns-steward")
content=base64.b64decode(SOURCE_B64)
target=directory/"ha_reload_capability.py"
if directory.exists():
 st=directory.stat()
 if directory.is_symlink() or st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o700:
  raise RuntimeError("Existing steward directory is not root-only 0700")
else:
 directory.mkdir(mode=0o700)
 os.chown(directory,0,0)
if target.exists():
 if target.is_symlink() or target.read_bytes()!=content:
  raise RuntimeError("Existing helper differs; refuse overwrite without audit")
 assert (target.stat().st_uid==0 and stat.S_IMODE(target.stat().st_mode)==0o700)
 print("JNS_STEWARD_HELPER_ALREADY_INSTALLED",hashlib.sha256(content).hexdigest())
else:
 fd,path=tempfile.mkstemp(prefix=".jns-ha-reload-",dir=directory)
 try:
  with os.fdopen(fd,"wb") as fp:
   fp.write(content);fp.flush();os.fsync(fp.fileno())
  os.chown(path,0,0);os.chmod(path,0o700)
  os.replace(path,target)
 finally:
  if os.path.exists(path):os.unlink(path)
 print("JNS_STEWARD_HELPER_INSTALLED",hashlib.sha256(content).hexdigest())
"""
source = "SOURCE_B64="+repr(base64.b64encode(SOURCE).decode())+";exec(compile("+repr(code)+",'<steward-install>','exec'))"
command=["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",source]
r=json.loads(ssh_host("nodeb",command))
pid=r.get("pid")
for _ in range(50):
    if r.get("exited"):break
    if not isinstance(pid,int):raise RuntimeError("missing QGA PID; no retry")
    time.sleep(1)
    r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
if not r.get("exited") or r.get("exitcode")!=0:
    raise RuntimeError("read-only bootstrapping rejected: "+str(r.get("err-data",""))[-250:])
print((r.get("out-data") or "")[-650:],flush=True)
if "JNS_STEWARD_HELPER_" not in (r.get("out-data") or ""):raise RuntimeError("missing attestation")
command=["qm","guest","exec","905","--","docker","exec","homeassistant",
         "python3","/config/.jns-steward/ha_reload_capability.py","status"]
r=json.loads(ssh_host("nodeb",command))
pid=r.get("pid")
for _ in range(40):
    if r.get("exited"):break
    if not isinstance(pid,int):raise RuntimeError("missing verification QGA PID")
    time.sleep(1)
    r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
if not r.get("exited") or r.get("exitcode")!=0:raise RuntimeError("post-install status failed")
print("JNS_STEWARD_HELPER_STATUS "+(r.get("out-data") or "")[-1000:],flush=True)
