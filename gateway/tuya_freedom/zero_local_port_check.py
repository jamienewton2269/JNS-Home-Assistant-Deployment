#!/usr/bin/env python3
"""Single-port availability check for *unavailable* Tuya Local endpoints only.

No Tuya protocol packets or commands. Credentials and target addresses stay
inside VM905. A refused/filtered port is diagnostic, not licence to overwrite
the configuration.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import collections,datetime,json,os,pathlib,socket
root=pathlib.Path("/config")
folder=root/".jns_tuya_freedom"
file=folder/"latest-live.json"
data=json.loads(file.read_text())
now=datetime.datetime.now(datetime.timezone.utc)
created=datetime.datetime.fromisoformat(data["generated_utc"])
if not 0<=(now-created).total_seconds()<=900:
    raise RuntimeError("observer_stale")
entries=json.loads((root/".storage/core.config_entries").read_text())["data"]["entries"]
local={str(e.get("data",{}).get("device_id","")).strip().lower():e
    for e in entries if e.get("domain")=="tuya_local"}
results={}
counts=collections.Counter()
for row in data["physical_devices"]:
    if not row.get("local_configured"):continue
    if int(row.get("available_local_entities") or 0)>0:continue
    nid=str(row.get("native_device_id","")).lower()
    entry=local.get(nid)
    if not entry:continue
    address=entry.get("data",{}).get("host")
    counts["zero_available_devices"]+=1
    status="no_address"
    if isinstance(address,str) and address:
        try:
            resolved=socket.getaddrinfo(address,6668,family=socket.AF_INET,type=socket.SOCK_STREAM)
            destination=resolved[0][4]
            # Connect + close immediately, no Tuya command payload.
            sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            sock.settimeout(1.2)
            try:
                code=sock.connect_ex(destination)
                status="tcp_open" if code==0 else "tcp_not_open"
            finally:
                sock.close()
        except OSError:
            status="not_resolvable_or_network_error"
    counts[status]+=1
    results[nid]={"configured_host":address,"port_6668":status,
                  "no_protocol_payload_sent":True}
stamp=now.strftime("%Y%m%dT%H%M%SZ")
path=folder/("zero-available-port-"+stamp+".json")
fd=os.open(str(path),os.O_WRONLY|os.O_EXCL|os.O_CREAT,0o600)
with os.fdopen(fd,"w") as f:
    json.dump({"utc":now.isoformat(),"private_results":results,"counts":dict(counts),
               "note":"TCP reachability alone does not verify Tuya local key or cloud independence."},
               f,indent=2,sort_keys=True)
    f.write("\n")
print(json.dumps({"mode":"limited_targeted_check","counts":dict(counts),
                  "device_changes":0,"cloud_changes":0,
                  "private_report_saved":True}))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("vm905_not_running")
    source="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
                                  "docker","exec","homeassistant","python3","-c",source]))
    pid=r.get("pid");expiry=time.monotonic()+95
    while not r.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>expiry:raise RuntimeError("qga_timeout")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:raise RuntimeError("port_check_failed")
    return json.loads(r.get("out-data",""))
if __name__=="__main__":
    try:print("JNS_TUYA_ZERO_LOCAL_PORT_CHECK",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:
        print("JNS_TUYA_ZERO_LOCAL_PORT_BLOCKED",type(e).__name__,str(e)[:70],flush=True)
        raise SystemExit(1)
