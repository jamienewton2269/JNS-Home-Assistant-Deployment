#!/usr/bin/env python3
"""Check real-time Tuya Local health on HA-General using locally held HA token.

No key/token/host/device identity leaves the guest. Purely read-only HA REST.
"""
import base64, json, sys, time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import collections,datetime,json,os,pathlib,stat,urllib.request,urllib.error
root=pathlib.Path("/config")
private=root/".jns_tuya_freedom"
token_file=private/"ha_general_api.token"
if private.is_symlink() or not private.is_dir() or stat.S_IMODE(private.stat().st_mode)!=0o700:
    print(json.dumps({"status":"BLOCKED_PRIVATE_DIR_PERMISSIONS"}))
    raise SystemExit(0)
if not token_file.is_file() or token_file.is_symlink():
    print(json.dumps({"status":"BLOCKED_NO_LOCAL_HA_TOKEN","token_present":False}))
    raise SystemExit(0)
ts=token_file.stat()
if ts.st_uid!=0 or stat.S_IMODE(ts.st_mode)!=0o600 or not 64<=ts.st_size<=4096:
    print(json.dumps({"status":"BLOCKED_UNSAFE_TOKEN_PERMISSIONS"}))
    raise SystemExit(0)
token=token_file.read_text(encoding="utf-8").strip()
if not 64<=len(token)<=4096 or any(ch.isspace() for ch in token):
    print(json.dumps({"status":"BLOCKED_INVALID_LOCAL_TOKEN"}))
    raise SystemExit(0)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
state_records=None
for base in ("http://127.0.0.1/api/states","http://127.0.0.1:8123/api/states"):
    try:
        req=urllib.request.Request(base,headers={"Authorization":"Bearer "+token,"Accept":"application/json"})
        with opener.open(req,timeout=14) as resp:
            if resp.status!=200:continue
            data=resp.read(12000000)
        loaded=json.loads(data)
        if isinstance(loaded,list):
            state_records=loaded
            break
    except (OSError,ValueError,TypeError):
        continue
del token
if state_records is None:
    print(json.dumps({"status":"BLOCKED_HA_API_AUTH_OR_TRANSPORT"}))
    raise SystemExit(0)
state_lookup={s.get("entity_id"):s.get("state") for s in state_records}
del state_records
config=json.loads((root/".storage/core.config_entries").read_text())["data"]["entries"]
devices=json.loads((root/".storage/core.device_registry").read_text())["data"]["devices"]
entities=json.loads((root/".storage/core.entity_registry").read_text())["data"]["entities"]
entry_by_id={e.get("entry_id"):e for e in config}
local_devices={d.get("id"):d for d in devices
    if entry_by_id.get(d.get("config_entry_id"),{}).get("domain")=="tuya_local"}
counts=collections.Counter()
rows=[]
for did,d in local_devices.items():
    members=[e for e in entities if e.get("device_id")==did
             and e.get("platform")=="tuya_local" and not e.get("disabled_by")]
    states={e["entity_id"]:state_lookup.get(e["entity_id"],"not_loaded") for e in members}
    healthy=sum(v not in ("unavailable","unknown","not_loaded") for v in states.values())
    counts["configured_local_devices"]+=1
    counts["enabled_local_entities"]+=len(members)
    counts["available_local_entities"]+=healthy
    counts["unknown_unavailable_or_unloaded_entities"]+=len(members)-healthy
    counts["devices_with_at_least_one_available_entity"]+=int(healthy>0)
    counts["devices_with_every_enabled_entity_available"]+=int(len(members)>0 and healthy==len(members))
    rows.append({"device_registry_id":did, "device_name":d.get("name_by_user") or d.get("name"),
                 "entity_states":states, "available_entities":healthy})
now=datetime.datetime.now(datetime.timezone.utc)
f=private/("live-health-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
fd=os.open(str(f),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,"w",encoding="utf-8") as target:
    json.dump({"schema":1,"collected_utc":now.isoformat(),
               "method":"authenticated_live_ha_state_read_only",
               "note":"State availability alone does not prove command function or Tuya cloud independence.",
               "devices":rows,"aggregate":dict(counts)},target,indent=2)
    target.write("\n")
    target.flush()
    os.fsync(target.fileno())
print(json.dumps({"status":"LIVE_READ_ONLY_OK","private_report_written":True,
                  "aggregate":dict(counts),
                  "WAN_OFFLINE_VALIDATION":"NOT_TESTED"},sort_keys=True))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("VM905 not running")
    arg="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    cmd=["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",arg]
    r=json.loads(ssh_host("nodeb",cmd))
    deadline=time.monotonic()+85
    while not r.get("exited"):
        if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:
            raise RuntimeError("HA guest-agent timeout")
        time.sleep(1)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
    if r.get("exitcode")!=0:
        raise RuntimeError("Live status query failed; no modifications")
    return json.loads(r.get("out-data",""))
if __name__=="__main__":
    try:
        print("JNS_TUYA_LIVE_HEALTH",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as exc:
        print("JNS_TUYA_LIVE_HEALTH_BLOCKED",type(exc).__name__,str(exc)[:100],flush=True)
        raise SystemExit(1)
