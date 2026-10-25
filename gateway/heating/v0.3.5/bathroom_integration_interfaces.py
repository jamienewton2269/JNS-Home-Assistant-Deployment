#!/usr/bin/env python3
"""Read-only inspect minimal HA905 heating coordinator and sensor Python interfaces.

Outputs source snippets only for explicitly allowlisted integration files that
have no secrets or config values. Never reads HA tokens, registry or Store.
"""
import base64,json,re,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST = r'''
import ast,hashlib,json,pathlib,re
root=pathlib.Path("/config/custom_components/jns_heating_zones")
out={}
for name in ("coordinator.py","sensor.py","__init__.py","const.py"):
 path=root/name
 blob=path.read_bytes()
 text=blob.decode()
 ast.parse(text)
 if len(blob)>45000:raise RuntimeError("component unexpectedly large")
 # Exclude suspicious strings explicitly; this prints code only.
 if re.search(r"(?i)(BEGIN PRIVATE KEY|access_token\\s*=|client_secret\\s*=|password\\s*=)",text):
  raise RuntimeError("component contains secret-like literal; no export")
 out[name]={"sha":hashlib.sha256(blob).hexdigest(),"code":text}
print(json.dumps(out,sort_keys=True))
'''
cmd="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",cmd]))
end=time.monotonic()+100
while not r.get("exited"):
 if not isinstance(r.get("pid"),int) or time.monotonic()>end:raise RuntimeError("readonly component audit timed out")
 time.sleep(1)
 r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
if r.get("exitcode")!=0:raise RuntimeError("readonly component audit blocked")
result=json.loads(r.get("out-data") or "{}")
print("JNS_HEATING_COMPONENT_SOURCE_READONLY",json.dumps(result,sort_keys=True))
