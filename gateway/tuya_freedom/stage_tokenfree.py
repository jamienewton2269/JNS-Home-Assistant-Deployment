#!/usr/bin/env python3
"""Stage a read-only native HA observer privately, with no HA reload or restart.

The observer runs inside HA Core (so can see hass.states directly without
requiring a long-lived access token) *after* a separately guarded activation.
This script merely stages source files. No HA settings or entities are changed.
"""
import base64
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

GUEST=r'''
import base64, hashlib, json, os
from pathlib import Path

payload=json.loads(base64.b64decode(PAYLOAD))
root=Path("/config/.jns_tuya_freedom")
if root.is_symlink() or not root.is_dir():
    raise RuntimeError("Private Tuya Freedom directory missing")
os.chmod(root,0o700)
stage=root/"staged_observer"/"jns_tuya_freedom"
stage.mkdir(parents=True,mode=0o700,exist_ok=True)
os.chmod(stage.parent,0o700)
os.chmod(stage,0o700)
paths={}
for name in ("__init__.py","manifest.json"):
    content=base64.b64decode(payload[name])
    if name=="__init__.py":
        compile(content,str(stage/name),"exec")
    else:
        manifest=json.loads(content)
        if manifest.get("domain")!="jns_tuya_freedom":
            raise RuntimeError("Unexpected domain")
    path=stage/name
    if path.is_symlink():
        raise RuntimeError("Unsafe staged symlink")
    temp=stage/("."+name+".stage")
    flags=os.O_CREAT|os.O_WRONLY|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(str(temp),flags,0o600)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp,path)
        os.chmod(path,0o600)
    finally:
        if temp.exists():temp.unlink()
    paths[name]=hashlib.sha256(content).hexdigest()
print(json.dumps({"status":"STAGED_ONLY_NOT_ENABLED",
                  "token_required":False,
                  "module_compiled":True,
                  "manifest_valid":True,
                  "private_stage":True,
                  "configuration_yaml_modified":False,
                  "ha_restart_attempted":False,
                  "integrations_changed":False}))
'''

def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("VM905 is not running")
    here=Path(__file__).resolve().parent/"component"
    payload={
        name:base64.b64encode((here/name).read_bytes()).decode()
        for name in ("__init__.py","manifest.json")
    }
    src=GUEST.replace("PAYLOAD",repr(base64.b64encode(
        json.dumps(payload).encode()).decode()))
    command="exec(__import__('base64').b64decode('"+base64.b64encode(src.encode()).decode()+"'))"
    q=["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",command]
    result=json.loads(ssh_host("nodeb",q))
    deadline=time.monotonic()+75
    while not result.get("exited"):
        if time.monotonic()>deadline or not isinstance(result.get("pid"),int):
            raise RuntimeError("Guest agent returned no result")
        time.sleep(1)
        result=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(result["pid"])]))
    if result.get("exitcode")!=0:
        raise RuntimeError("VM905 private code stage failed")
    return json.loads(result.get("out-data",""))

if __name__=="__main__":
    try:
        print("JNS_TUYA_TOKENFREE_STAGE",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as exc:
        print("JNS_TUYA_TOKENFREE_STAGE_BLOCKED",type(exc).__name__,str(exc)[:100],flush=True)
        raise SystemExit(1)
