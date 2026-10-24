#!/usr/bin/env python3
"""JNS Solar Economy: metadata-only HA900/902/905 parity audit.
Read-only; emits only bounded aggregate counts/presence, never entity names,
integration entry payloads, personal locations, addresses, or credentials.
"""
import base64
import json
import shlex
import subprocess
import time

VM_HOST = {900: "nodea", 902: "nodea", 905: "nodeb"}
IN_GUEST = r'''
import json
from collections import Counter
from pathlib import Path

p=Path("/config")
store=p/".storage"
out={"audit":"aggregate-v1","config_found":p.exists()}
def registry(filename, field):
    try:
        d=json.loads((store/filename).read_text(encoding="utf-8"))
        z=d.get("data",{}).get(field,[])
        return z if isinstance(z,list) else []
    except Exception:
        return []
entities=registry("core.entity_registry","entities")
devices=registry("core.device_registry","devices")
entries=registry("core.config_entries","entries")
out["entities_total"]=len(entities)
out["devices_total"]=len(devices)
out["config_entries_total"]=len(entries)
out["automations_registered"]=sum(e.get("platform")=="automation" for e in entities)
out["automations_enabled"]=sum(e.get("platform")=="automation" and not e.get("disabled_by") for e in entities)
out["integrations_selected"]={}
known=["mqtt","zha","esphome","zigbee2mqtt","mobile_app","honeywell","lyric","tapo","onvif","generic","go2rtc","hacs","piper","mpd","jns_deployment","jns_heating_zones"]
domains=Counter(e.get("domain") for e in entries)
out["integrations_selected"]={name:domains[name] for name in known if domains[name]}
out["integration_unique_domain_count"]=len(domains)
out["entities_by_domain"]={domain:sum(e.get("entity_id","").startswith(domain+".") for e in entities) for domain in ["automation","script","camera","light","switch","climate","sensor","binary_sensor","device_tracker","media_player"]}
try:
    import yaml
    with (p/"automations.yaml").open(encoding="utf-8") as fh:
        y=yaml.safe_load(fh)
    if isinstance(y,list):out["automations_yaml_count"]=len(y)
    else:out["automations_yaml_count"]=0
except Exception:
    out["automations_yaml_count"]="unreadable"
out["package_yaml_count"]=len(list((p/"packages").glob("*.yaml"))) if (p/"packages").exists() else 0
out["custom_component_count"]=len([d for d in (p/"custom_components").iterdir() if d.is_dir()]) if (p/"custom_components").is_dir() else 0
out["HA_db_MB"]=round((p/"home-assistant_v2.db").stat().st_size/1048576,1) if (p/"home-assistant_v2.db").exists() else None
out["important_components_present"]={name:(p/"custom_components"/name).is_dir() for name in ["jns_deployment","jns_heating_zones","jns_native_area_sync","hacs"]}
out["configuration_packages_directory"]=((p/"packages").is_dir())
print("JNS_PARITY_JSON="+json.dumps(out,sort_keys=True))
'''

def ssh(node, command, seconds=15):
    args=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
          "-o","ConnectTimeout=5","root@"+node,shlex.join(command)]
    r=subprocess.run(args,capture_output=True,text=True,timeout=seconds)
    if r.returncode:
        return {"ok":False,"error":"ssh_or_remote_command_exit_"+str(r.returncode)}
    return {"ok":True,"text":r.stdout}

def get_guest(vm, node):
    stat=ssh(node,["qm","status",str(vm)],15)
    if not stat["ok"]:
        return {"status":"host_access_blocked"}
    if "running" not in stat["text"]:
        return {"status":"not_running"}
    payload=base64.b64encode(IN_GUEST.encode("utf-8")).decode("ascii")
    cmd=["qm","guest","exec",str(vm),"--","docker","exec","homeassistant",
         "python3","-c","exec(__import__('base64').b64decode('"+payload+"'))"]
    initial=ssh(node,cmd,26)
    if not initial["ok"]:
        return {"status":"guest_agent_or_exec_unavailable"}
    try:
        j=json.loads(initial["text"])
    except (ValueError,KeyError):
        return {"status":"guest_response_unavailable"}
    for i in range(6):
        if j.get("exited"): break
        pid=j.get("pid")
        if pid is None: return {"status":"missing_process_status"}
        time.sleep(1)
        step=ssh(node,["qm","guest","exec-status",str(vm),str(pid)],10)
        if not step["ok"]:return {"status":"guest_status_unavailable"}
        try:j=json.loads(step["text"])
        except ValueError:return {"status":"invalid_process_status"}
    if not j.get("exited"):return {"status":"guest_still_running"}
    if j.get("exitcode")!=0:
        return {"status":"guest_python_unavailable"}
    lines=[a for a in (j.get("out-data") or "").splitlines() if a.startswith("JNS_PARITY_JSON=")]
    if not lines:return {"status":"no_aggregate_payload"}
    try: return {"status":"ok",**json.loads(lines[-1].split("=",1)[1])}
    except ValueError:return {"status":"invalid_aggregate_payload"}

def main():
    print("JNS_SOLAR_PARITY_PREFLIGHT_READ_ONLY",flush=True)
    for vm,node in VM_HOST.items():
        try: result=get_guest(vm,node)
        except (subprocess.TimeoutExpired,OSError):result={"status":"timeout_or_os_error"}
        print("VM_"+str(vm)+" "+json.dumps(result,sort_keys=True),flush=True)
    print("JNS_SOLAR_PARITY_PREFLIGHT_COMPLETE",flush=True)
if __name__=="__main__":main()
