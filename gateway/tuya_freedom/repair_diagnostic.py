#!/usr/bin/env python3
"""VM905 token-free Tuya repair and transport diagnostic. Read-only except private report.

Never prints Tuya IDs, keys, account data, entities, IPs, names or logs into
the PUBLIC GitHub Actions run. No integrations reloaded and no devices probed.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

GUEST = r'''
import collections,datetime,ipaddress,json,os,pathlib,re,socket,stat,struct
root=pathlib.Path("/config")
private=root/".jns_tuya_freedom"
if private.is_symlink() or not private.is_dir():
    raise RuntimeError("private_dir_unavailable")
now=datetime.datetime.now(datetime.timezone.utc)
report=private/"latest-live.json"
if report.is_symlink() or not report.is_file():raise RuntimeError("observer_missing")
live=json.loads(report.read_text())
timestamp=datetime.datetime.fromisoformat(live.get("generated_utc"))
age=(now-timestamp).total_seconds()
if not 0<=age<=900:raise RuntimeError("observer_stale")
def load(name,key):
    return json.loads((root/".storage"/name).read_text())["data"][key]
entries=load("core.config_entries","entries")
devices=load("core.device_registry","devices")
entities=load("core.entity_registry","entities")
byid={x.get("entry_id"):x for x in entries}
bydevice=collections.defaultdict(list)
for e in entities:
    if e.get("device_id"):bydevice[e["device_id"]].append(e)
local={str(e.get("data",{}).get("device_id","")).lower():e for e in entries if e.get("domain")=="tuya_local"}
cloud=collections.defaultdict(list)
for d in devices:
    if not ({d.get("config_entry_id")} | set(d.get("config_entries",[]))) & {e["entry_id"] for e in entries if e.get("domain")=="tuya"}:continue
    for name,value in d.get("identifiers",[]):
        if str(name).lower()=="tuya" and len(str(value))>=12:
            cloud[str(value).lower()].append(d)
def host_ips(host):
    if not isinstance(host,str) or not host.strip():return []
    try:return sorted({t[4][0] for t in socket.getaddrinfo(host,None,family=socket.AF_INET,type=socket.SOCK_STREAM)})
    except OSError:return []
def active_peers():
    peers=set()
    for fname in ("/proc/net/tcp",):
        try:
            with open(fname) as f:
                for line in f:
                    fields=line.split()
                    if len(fields)<4 or fields[3]!="01":continue
                    if ":" not in fields[2]:continue
                    host,port=fields[2].split(":")
                    if int(port,16) not in (6666,6667,6668):continue
                    ip=socket.inet_ntoa(struct.pack("<I",int(host,16)))
                    peers.add(ip)
        except (OSError,ValueError):pass
    return peers
peers=active_peers()
summary=collections.Counter()
device_rows=[]
saw_bad=0
for physical in live.get("physical_devices",[]):
    nid=str(physical.get("native_device_id","")).lower()
    related=cloud.get(nid,[])
    models=sorted({str(d.get("model")) for d in related if d.get("model")})
    names=sorted({str(d.get("name_by_user") or d.get("name")) for d in related if d.get("name_by_user") or d.get("name")})
    cloud_entities=sorted(set(e.get("entity_id") for d in related for e in bydevice.get(d.get("id"),[]) if e.get("platform")=="tuya"))
    cfg=local.get(nid)
    key_status="not_configured"
    host=None
    resolved=[]
    conn=False
    entry={"name":names[0] if names else "Unlabelled device",
           "device_id":nid,"models":models,
           "cloud_entity_ids":cloud_entities,
           "local_configured":bool(cfg),
           "live_local_entities":physical.get("local_entity_states",{}),
           "available_local_entities":physical.get("available_local_entities",0),
           "enabled_local_entities":physical.get("enabled_local_entities",0)}
    if cfg:
        conf=cfg.get("data",{})
        host=conf.get("host")
        resolved=host_ips(host)
        conn=bool(set(resolved)&peers)
        has_key=bool(conf.get("local_key"))
        key_status="stored" if has_key else "missing"
        entry.update({"local_entry_id":cfg.get("entry_id"),
                      "local_host":host,
                      "local_resolved_ipv4":resolved,
                      "local_key_stored":has_key,
                      "local_config_data_keys":sorted(conf.keys()),
                      "local_config_options_keys":sorted(cfg.get("options",{}).keys()),
                      "local_entry_source":cfg.get("source"),
                      "local_entry_disabled_by":cfg.get("disabled_by"),
                      "entry_type_name":conf.get("type"),
                      "connection_active_existing":conn})
        summary["local_total"]+=1
        summary["local_addresses_resolve"]+=int(bool(resolved))
        summary["local_existing_tcp_connection"]+=int(conn)
        summary["local_key_present"]+=int(has_key)
        good=int(physical.get("available_local_entities") or 0)
        enabled=int(physical.get("enabled_local_entities") or 0)
        if good==0:summary["local_zero_available"]+=1;saw_bad+=1
        elif good<enabled:summary["local_partial_availability"]+=1
        else:summary["local_fully_available"]+=1
        if isinstance(host,str):
            try:
                ipaddress.ip_address(host)
                summary["local_host_is_ip_literal"]+=1
            except ValueError:summary["local_host_is_dns_name"]+=1
    else:
        summary["local_onboarding_needed"]+=1
        entry["likely_transport"]="UNCONFIRMED"
        # Model/category alone is not sufficient to prove Wi-Fi vs Zigbee.
        summary["cloud_onboarding_entities"]+=len(cloud_entities)
    device_rows.append(entry)
# Log excerpt kept local only, never show in public Actions. Match tuya_local lines and
# nearby error text; don't store adjacent lines with other integration credentials.
logs=[]
ha_log=root/"home-assistant.log"
if ha_log.is_file():
    with ha_log.open("rb") as f:
        size=f.seek(0,os.SEEK_END)
        f.seek(max(0,size-1500000))
        textlog=f.read().decode("utf-8","replace")
    for line in textlog.splitlines():
        if "tuya_local" in line.lower() and any(
          t in line.lower() for t in ("failed","unavailable","error","timeout","connect",
                                      "retry","protocol","key","offline","unsupported","exception")
        ):
            logs.append(line[:300])
    summary["recent_tuya_local_error_lines"]=len(logs)
doc={"schema":1,"mode":"private_diagnostic","generated_utc":now.isoformat(),
     "observer_report_age_seconds":int(age),"counts":dict(summary),
     "devices":device_rows,
     "recent_tuya_local_error_excerpts_private":logs[-40:],
     "decision":"NO_REMOTE_CHANGE_APPROVED_IN_THIS_READ_ONLY_AUDIT",
     "notes":["Local entity unavailable is not proof of bad key; host address can be stale.",
              "Local key must not be printed or logged.",
              "Some Tuya devices limit simultaneous LAN connections; avoid parallel protocol scans.",
              "No devices or config entries were modified by this diagnostic."]}
output=private/("diagnosis-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
fd=os.open(str(output),os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o600)
with os.fdopen(fd,"w") as stream:
    json.dump(doc,stream,sort_keys=True,indent=2)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
print(json.dumps({"status":"AUDIT_COMPLETE_NO_CHANGES",
                  "observer_age_seconds":int(age),"counts":dict(summary),
                  "private_report_saved":True,
                  "changed_config_entries":0,
                  "changed_ha_entities":0},sort_keys=True))
'''

def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("vm905_not_running")
    guest="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",guest]))
    pid=r.get("pid")
    expiry=time.monotonic()+95
    while not r.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>expiry:
            raise RuntimeError("guest_timeout_or_missing_pid")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:
        raise RuntimeError("diagnostic_failed_without_changes")
    return json.loads(r.get("out-data",""))
if __name__=="__main__":
    try:print("JNS_TUYA_REPAIR_DIAGNOSTIC",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as exc:
        print("JNS_TUYA_REPAIR_DIAGNOSTIC_BLOCKED",type(exc).__name__,str(exc)[:85],flush=True)
        raise SystemExit(1)
