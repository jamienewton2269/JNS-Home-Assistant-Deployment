#!/usr/bin/env python3
"""JNS Shark IQ read-only preflight: inspect HA metadata and passive DNS leases.
Never send robot commands, mutate HA state or emit token/MAC/IP values.
"""
import base64
import json
import re
import shlex
import subprocess
import time

SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=5"]
HOSTS = (("nodea", 902), ("nodeb", 905))
PAYLOAD = r'''
from pathlib import Path
import json,re
s = Path("/config/.storage")
def reg(filename,key):
    try: return json.loads((s/filename).read_text()).get("data",{}).get(key,[])
    except (OSError,ValueError,TypeError): return []
devices=reg("core.device_registry","devices")
entities=reg("core.entity_registry","entities")
entries=reg("core.config_entries","entries")
sharkentries={e.get("entry_id") for e in entries if e.get("domain")=="sharkiq"}
vac=[e for e in entities if e.get("platform")=="sharkiq" or e.get("entity_id","").startswith("vacuum.")]
ids={e.get("device_id") for e in vac if e.get("device_id")}
models=[]
for d in devices:
    label=" ".join(str(d.get(k) or "") for k in ("manufacturer","model","name","name_by_user"))
    if d.get("id") in ids or sharkentries.intersection(d.get("config_entries",[])) or re.search(r"shark|vacuum|robot",label,re.I):
        models.append({"manufacturer":str(d.get("manufacturer") or "")[:60],
                       "model":str(d.get("model") or "")[:60],
                       "sw_version_present":bool(d.get("sw_version"))})
out={"sharkiq_config_entry_count":len(sharkentries),
     "vacuum_entity_count":sum(e.get("entity_id","").startswith("vacuum.") for e in vac),
     "possible_robot_models":models[:12]}
print("JNS_SHARK_LOCAL_SAFE="+json.dumps(out,sort_keys=True))
'''

def remote(node, argv, timeout=20):
    try:
        p=subprocess.run(SSH+[node,shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout
    except (OSError,subprocess.TimeoutExpired):
        return None,""

def metadata(node,vm):
    rc,state=remote(node,["qm","status",str(vm)],12)
    if rc!=0: return {"status":"guest_unavailable"}
    if "status: running" not in state: return {"status":"guest_not_running"}
    runner="exec(__import__('base64').b64decode('"+base64.b64encode(PAYLOAD.encode()).decode()+"'))"
    rc,out=remote(node,["qm","guest","exec",str(vm),"--","docker","exec","homeassistant","python3","-c",runner],30)
    if rc!=0: return {"status":"guest_agent_or_container_unavailable"}
    try: d=json.loads(out)
    except ValueError: return {"status":"invalid_qga_response"}
    for _ in range(8):
        if d.get("exited") or not d.get("pid"): break
        time.sleep(1)
        rc,out=remote(node,["qm","guest","exec-status",str(vm),str(d["pid"])],15)
        if rc!=0: return {"status":"qga_exec_status_unavailable"}
        try: d=json.loads(out)
        except ValueError: return {"status":"invalid_qga_exec_status"}
    if not d.get("exited") or d.get("exitcode")!=0: return {"status":"guest_metadata_unavailable"}
    for line in d.get("out-data","").splitlines():
        if line.startswith("JNS_SHARK_LOCAL_SAFE="):
            try: return {"status":"ok",**json.loads(line.split("=",1)[1])}
            except ValueError: break
    return {"status":"safe_marker_missing"}

def leases(node,ct):
    script='for f in /var/lib/misc/dnsmasq.leases /var/lib/dnsmasq/dnsmasq.leases /run/dnsmasq/dnsmasq.leases; do if test -f "$f"; then cat "$f"; fi; done'
    rc,out=remote(node,["pct","exec",str(ct),"--","sh","-c",script],15)
    if rc!=0: return {"status":"lease_source_unavailable"}
    names=set()
    for line in out.splitlines():
        parts=line.split()
        if len(parts)>=4 and re.search(r"shark|robot|vac|rvc",parts[3],re.I):
            names.add(parts[3].lower())
    return {"status":"ok","matching_hostname_count":len(names),"matches_have_dns_names":bool(names)}


def local_endpoint_probe():
    """Harmless TCP handshakes only, and only to the verified known Shark MAC."""
    import socket
    hostname="jns-d7f90e.home.arpa"
    historical_ip="10.10.101.169"
    expected_mac="64:82:14:d7:f9:0e"
    try:
        answers=socket.getaddrinfo(hostname,None,socket.AF_INET,socket.SOCK_STREAM)
        candidates=sorted({a[4][0] for a in answers})
    except OSError:
        candidates=[]
    # Prefer the JNS DNS record. Historical IP is only a guarded fallback.
    if historical_ip not in candidates:
        candidates.append(historical_ip)
    result={"dns_resolved":bool(candidates and (candidates[0]!=historical_ip or len(candidates)>1)),
            "identity_verified":False,"port_states":{},
            "actions_sent":0}
    for address in candidates[:4]:
        subprocess.run(["ping","-n","-c","1","-W","1",address],
                       capture_output=True,timeout=5,check=False)
        p=subprocess.run(["ip","neigh","show",address],
                         capture_output=True,text=True,timeout=5,check=False)
        if expected_mac not in p.stdout.lower():
            continue
        result["identity_verified"]=True
        result["address_source"]="jns_dns" if address in candidates[:-1] else "historical_fallback"
        for port in (443,1883,80,8883):
            try:
                with socket.create_connection((address,port),timeout=1.5):
                    result["port_states"][str(port)]="open"
            except ConnectionRefusedError:
                result["port_states"][str(port)]="closed"
            except OSError:
                result["port_states"][str(port)]="not_open_or_filtered"
        break
    if not result["identity_verified"]:
        result["status"]="identity_unverified_no_port_test"
    else:
        result["status"]="probe_completed"
    return result

def main():
    report={"mode":"read_only","action_commands_sent":0,
            "devices":{f"VM{vm}":metadata(node,vm) for node,vm in HOSTS},
            "leases":{"CT247":leases("nodea",247),"CT248":leases("nodeb",248)},
            "target":local_endpoint_probe()}
    print("JNS_SHARK_LOCAL_PREFLIGHT="+json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
