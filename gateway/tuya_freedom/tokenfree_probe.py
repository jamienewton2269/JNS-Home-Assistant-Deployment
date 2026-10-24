#!/usr/bin/env python3
"""No-token, no-change HA-General native runtime capability check."""
import base64, json, sys, time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import json, pathlib, re
root=pathlib.Path("/config")
cfg=(root/"configuration.yaml").read_text(errors="replace")
entries=json.loads((root/".storage/core.config_entries").read_text())["data"]["entries"]
domains={e.get("domain") for e in entries}
def configured(key):
    return re.search(r"(?m)^\s*"+re.escape(key)+r"\s*:",cfg) is not None
def exists(name):
    return (root/"custom_components"/name).is_dir()
existing=(root/"custom_components/jns_tuya_freedom").is_dir()
out={
  "ha_native_observer_already_installed":existing,
  "ha_native_observer_yaml_enabled":configured("jns_tuya_freedom"),
  "pyscript_integration_configured":"pyscript" in domains or configured("pyscript"),
  "pyscript_component_installed":exists("pyscript"),
  "python_script_yaml_configured":configured("python_script"),
  "python_script_dir_exists":(root/"python_scripts").is_dir(),
  "appdaemon_addon_presence_unknown":True,
  "mqtt_statestream_yaml_configured":configured("mqtt_statestream"),
  "private_tuya_dir_exists":(root/".jns_tuya_freedom").is_dir(),
  "existing_tuya_local_config_entries":sum(e.get("domain")=="tuya_local" for e in entries),
  "native_cloud_config_entries":sum(e.get("domain")=="tuya" for e in entries)
}
print(json.dumps(out,sort_keys=True))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("HA-General not running")
    script="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    q=["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",script]
    r=json.loads(ssh_host("nodeb",q))
    deadline=time.monotonic()+70
    while not r.get("exited"):
        if time.monotonic()>deadline or not isinstance(r.get("pid"),int):
            raise RuntimeError("VM905 QGA inspection unavailable")
        time.sleep(1)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
    if r.get("exitcode")!=0:
        raise RuntimeError("Tokenless preflight failed")
    return json.loads(r["out-data"])
if __name__=="__main__":
    try:
        print("JNS_TUYA_TOKENFREE_PREFLIGHT",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as exc:
        print("JNS_TUYA_TOKENFREE_BLOCKED",type(exc).__name__,str(exc)[:70],flush=True)
        raise SystemExit(1)
