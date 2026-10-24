#!/usr/bin/env python3
"""Tokenless, passive Tuya Local TCP session inspection on HA-General.

Reads existing Linux /proc/net/tcp tables; DOES NOT initiate device sockets,
open a second Tuya session, send commands, or contact the Tuya cloud.
Detailed hostnames and device identities remain in private 0600 report.
"""
import base64, json, sys, time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

GUEST=r'''
import collections, datetime, ipaddress, json, os, pathlib, socket, struct, time
root=pathlib.Path("/config")
dir_=root/".jns_tuya_freedom"
if dir_.is_symlink() or not dir_.is_dir():
    raise RuntimeError("Private directory unavailable")
config=json.loads((root/".storage/core.config_entries").read_text())["data"]["entries"]
locals_=[e for e in config if e.get("domain")=="tuya_local"]
lookup={}
for c in locals_:
    host=c.get("data",{}).get("host")
    target=c.get("data",{}).get("device_id")
    ips=set()
    if isinstance(host,str) and host.strip():
        try:
            for row in socket.getaddrinfo(host,None,family=socket.AF_INET):
                ips.add(row[4][0])
        except OSError:pass
    if isinstance(target,str) and target.strip():
        lookup[target.strip().lower()]={"host":host,"ips":sorted(ips),"active":False}
def active_peers():
    found=set()
    try:
        with open("/proc/net/tcp",encoding="ascii") as f:
            for line in f:
                col=line.split()
                if len(col)<4 or col[3]!="01" or ":" not in col[2]:
                    continue
                iphex,porthex=col[2].split(":")
                if int(porthex,16) not in (6668,6667):
                    continue
                address=socket.inet_ntoa(struct.pack("<I",int(iphex,16)))
                found.add(address)
    except (OSError,ValueError):
        pass
    return found
samples=[]
for i in range(3):
    samples.append(active_peers())
    if i<2:time.sleep(1)
merged=set().union(*samples)
for v in lookup.values():
    v["active"]=bool(set(v["ips"]) & merged)
out=collections.Counter()
out["configured_local_entries"]=len(locals_)
out["unique_local_ids"]=len(lookup)
out["devices_with_existing_tcp_session"]=sum(x["active"] for x in lookup.values())
out["devices_without_session_observed"]=len(lookup)-out["devices_with_existing_tcp_session"]
out["local_entries_with_resolved_host"]=sum(bool(x["ips"]) for x in lookup.values())
out["other_tuya_local_tcp_peers_observed"]=len(merged-set().union(*(set(x["ips"]) for x in lookup.values())))
now=datetime.datetime.now(datetime.timezone.utc)
path=dir_/("tcp-passive-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,"w",encoding="utf-8") as f:
    json.dump({"schema":1,"created_utc":now.isoformat(),"method":"PASSIVE_TCP_EXISTING_SESSIONS_ONLY",
               "notice":"A socket is not proof of working device control or cloud independence. No socket can also be normal for nonpersistent connections.",
               "aggregate":dict(out),"local_devices":lookup},f,indent=2)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
print(json.dumps({"status":"PASSIVE_NO_TOKEN_NO_DEVICE_PROBES",
                  "aggregate":dict(out),"private_report_written":True}))
'''

def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("HA-General is not running")
    src="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    q=["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",src]
    r=json.loads(ssh_host("nodeb",q))
    deadline=time.monotonic()+75
    while not r.get("exited"):
        if time.monotonic()>deadline or not isinstance(r.get("pid"),int):
            raise RuntimeError("QEMU agent passive query unavailable")
        time.sleep(1)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
    if r.get("exitcode")!=0:
        raise RuntimeError("HA passive session query failed")
    return json.loads(r.get("out-data",""))

if __name__=="__main__":
    try:
        print("JNS_TUYA_PASSIVE_TCP",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as exc:
        print("JNS_TUYA_PASSIVE_TCP_BLOCKED",type(exc).__name__,str(exc)[:80],flush=True)
        raise SystemExit(1)
