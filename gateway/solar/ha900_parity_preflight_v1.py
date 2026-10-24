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
        err=(j.get("err-data") or "")[:3000]
        import re
        classes=re.findall(r"\b([A-Za-z_]+(?:Error|Exception))\b",err)
        if "No such container" in err: cause="homeassistant_container_not_found"
        elif "not found" in err.lower(): cause="guest_executable_not_found"
        elif "permission denied" in err.lower():cause="guest_permission_denied"
        elif classes:cause="python_exception_"+classes[-1]
        else:cause="unclassified_guest_failure"
        return {"status":"guest_python_unavailable","exitcode":j.get("exitcode"),"failure_category":cause}
    lines=[a for a in (j.get("out-data") or "").splitlines() if a.startswith("JNS_PARITY_JSON=")]
    if not lines:return {"status":"no_aggregate_payload"}
    try: return {"status":"ok",**json.loads(lines[-1].split("=",1)[1])}
    except ValueError:return {"status":"invalid_aggregate_payload"}


def legacy_guest_diagnostic():
    """No reading HA config: prove docker/python access with fixed benign markers."""
    checks={
      "docker_available":["sh","-c","command -v docker >/dev/null && echo JNS_DOCKER_FOUND"],
      "homeassistant_container":["docker","exec","homeassistant","sh","-c","test -d /config && echo JNS_CONFIG_EXISTS"],
      "python_exec":["docker","exec","homeassistant","python3","-c","print('JNS_PYTHON_OK')"],
    }
    result={}
    for label,cmd in checks.items():
        payload=ssh("nodea",["qm","guest","exec","900","--",*cmd],18)
        if not payload["ok"]:
            result[label]={"status":"guest_command_transport_error"}
            continue
        try: j=json.loads(payload["text"])
        except ValueError:
            result[label]={"status":"guest_response_not_json"}
            continue
        for _ in range(4):
            if j.get("exited"):break
            pid=j.get("pid")
            if pid is None:break
            time.sleep(1)
            poll=ssh("nodea",["qm","guest","exec-status","900",str(pid)],8)
            if not poll["ok"]:break
            try:j=json.loads(poll["text"])
            except ValueError:break
        out=(j.get("out-data") or "")
        err=(j.get("err-data") or "")
        result[label]={"exited":j.get("exited",False),"exitcode":j.get("exitcode"),
                       "marker_present":("JNS_" in out),"stdout_chars":len(out),"stderr_chars":len(err)}
    # Do not publish Docker names; classify only the count and HA Core state.
    inventory=ssh("nodea",["qm","guest","exec","900","--","docker","ps","-a","--format","{{.Names}}|{{.Status}}"],20)
    if inventory["ok"]:
        try:
            j=json.loads(inventory["text"])
            for _ in range(4):
                if j.get("exited"):break
                pid=j.get("pid")
                if pid is None:break
                time.sleep(1)
                step=ssh("nodea",["qm","guest","exec-status","900",str(pid)],8)
                if not step["ok"]:break
                j=json.loads(step["text"])
            names=[x.split("|",1) for x in (j.get("out-data") or "").splitlines() if "|" in x]
            matched=[state for name,state in names if name.lower() in ("homeassistant","home-assistant")]
            known_roles=["supervisor","observer","dns","multicast","audio","zigbee","mqtt","matter","ssh","samba","esphome","tts","piper","go2rtc","camera","backup","mariadb","influxdb","node_red","nodered","watchdog","plex","file_editor","adguard"]
            active_roles={role:sum(role in name.lower() and state.startswith("Up ") for name,state in names) for role in known_roles}
            stopped_roles={role:sum(role in name.lower() and not state.startswith("Up ") for name,state in names) for role in known_roles}
            result["container_inventory"]={
              "daemon_available":j.get("exitcode")==0,
              "containers_total":len(names),
              "containers_up":sum(state.startswith("Up ") for name,state in names),
              "homeassistant_core_state":("running" if any(v.startswith("Up ") for v in matched) else "not_running" if matched else "not_named_homeassistant"),
              "known_roles_active":{k:v for k,v in active_roles.items() if v},
              "known_roles_stopped":{k:v for k,v in stopped_roles.items() if v}
            }
        except (ValueError,TypeError,KeyError):
            result["container_inventory"]={"status":"unavailable"}
    return result

def main():
    print("JNS_SOLAR_PARITY_PREFLIGHT_READ_ONLY",flush=True)
    for vm,node in VM_HOST.items():
        try: result=get_guest(vm,node)
        except (subprocess.TimeoutExpired,OSError):result={"status":"timeout_or_os_error"}
        print("VM_"+str(vm)+" "+json.dumps(result,sort_keys=True),flush=True)
        if vm==900 and result.get("status")!="ok":
            try: diag=legacy_guest_diagnostic()
            except (subprocess.TimeoutExpired,OSError):diag={"status":"diagnostic_not_available"}
            print("VM_900_GUEST_DIAGNOSTIC "+json.dumps(diag,sort_keys=True),flush=True)
    print("JNS_SOLAR_PARITY_PREFLIGHT_COMPLETE",flush=True)
if __name__=="__main__":main()
